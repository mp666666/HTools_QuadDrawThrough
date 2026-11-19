# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
"""Viewport event filter; native Quad Draw still owns creation and other gestures."""
from __future__ import division, unicode_literals
import math
import traceback
from maya import cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
from .compat import QtCore, QtGui, QtWidgets, wrapInstance, isValid
from .compat import monotonic, global_position, as_text
from .geometry import Mesh, Targets, connected_brush, relax_positions, relax_region
from . import bridge, native, welding, soft_selection
from .visibility import FrontSurface
from .local_relax import LocalRelax,prevent_flips,TriangleIndex
from .symmetry import Symmetry

ACTIVE = None
CACHED_TARGETS = None
SETTINGS = dict(pick_radius=12.0,brush_radius=60.0,strength=0.22,lock_border=False,offset=0.0,
                smooth_mode='local',relax_enabled=True)
Qt = QtCore.Qt
Event = QtCore.QEvent.Type


def configure(**settings):
    """Change session settings without leaving a half-finished relax stroke."""
    SETTINGS.update(settings)
    if ACTIVE:
        if not SETTINGS['relax_enabled'] and ACTIVE.stroke and ACTIVE.stroke['smooth']:
            ACTIVE.cancel()
        for key,value in settings.items():
            setattr(ACTIVE,key,value)


def clear_cache():
    global CACHED_TARGETS
    if CACHED_TARGETS is not None:CACHED_TARGETS.close()
    CACHED_TARGETS=None


def matching_targets(targets,names):
    if targets is None:return False
    try:return [m.name for m in targets.meshes]==[Mesh(n).name for n in names]
    except (RuntimeError,ValueError):return False


def take_cached_targets(names):
    global CACHED_TARGETS
    if matching_targets(CACHED_TARGETS,names):
        targets=CACHED_TARGETS;CACHED_TARGETS=None
        return targets
    clear_cache()
    return Targets(names)


def view_ray(view, x, y):
    origin, direction = om.MPoint(), om.MVector()
    view.viewToWorld(int(round(x)), int(round(y)), origin, direction)
    return origin, direction.normal()


def quad_active():
    context = cmds.currentCtx() or ''
    return bool(context) and ('quaddraw' in context.lower() or
            'quaddraw' in (cmds.contextInfo(context, c=True) or '').lower())


class Controller(QtCore.QObject):
    def __init__(self, low=None, targets=None, status=None):
        super(Controller,self).__init__()
        self.auto_bind = low is None
        self.low = self.targets = None
        if low is not None:
            self.bind_meshes(low,targets)
        for key,value in SETTINGS.items():
            setattr(self,key,value)
        self.status_callback = status
        self.stroke = None
        self.tab_down = False
        self.b_down = False
        self.cursor_active = False
        self.cursor_mode = None
        self.jobs = []
        self.tool_callback = None
        self.busy = False
        self.swallow_release = False
        self.intercepting = False
        self.last_context = cmds.currentCtx() or ''
        self.quad_mesh = None

    def bind_meshes(self, low, targets):
        mesh=Mesh(low)
        if matching_targets(self.targets,targets):high=self.targets
        elif self.auto_bind:high=take_cached_targets(targets)
        else:high=Targets(targets)
        if any(m.handle == mesh.handle for m in high.meshes):
            raise ValueError('High and low meshes must be different.')
        if cmds.referenceQuery(mesh.name, isNodeReferenced=True):
            raise ValueError('Use a local editable low-poly mesh, not a referenced mesh.')
        if cmds.listConnections(mesh.name+'.inMesh',source=True,destination=False,type='geometryFilter'):
            raise ValueError('Deformed low-poly meshes are not supported.')
        if self.targets is not None and self.targets is not high:self.targets.close()
        self.low,self.targets = mesh,high

    def refresh_binding(self):
        if not self.auto_bind:
            return True
        low,high = native.current_meshes()
        if low is None or not high:
            self.low = self.targets = None
            self.status('开关已开启，等待 Live 高模和当前 Quad Draw 低模。')
            return False
        old_low = old_high = None
        try:
            if self.low:
                old_low,old_high = self.low.name,[m.name for m in self.targets.meshes]
        except RuntimeError:
            pass
        if low != old_low or high != old_high:
            self.bind_meshes(low,high)
            self.status('已自动识别低模：'+low.split('|')[-1]+'；Live 高模：'+str(len(high))+' 个。')
        return True

    def status(self, message):
        if self.status_callback:
            self.status_callback(message)

    def install(self):
        bridge.ensure_plugin()
        QtWidgets.QApplication.instance().installEventFilter(self)
        self.jobs = [cmds.scriptJob(event=[e, self.scene_changed], protected=True)
                     for e in ('SceneOpened', 'NewSceneOpened')]
        # API callbacks also run for scripted/marking-menu tool changes;
        # PostToolChanged waits until the new native context has initialized.
        self.tool_callback=om.MEventMessage.addEventCallback('PostToolChanged',self.tool_changed)
        self.jobs = [job for job in self.jobs if job is not None]
        self.status('已开启：自动跟随 Live 高模和 Quad Draw 低模。')
        if self.auto_bind:
            self.refresh_binding()
        self.remember_quad_mesh()

    def remember_quad_mesh(self):
        if not quad_active():
            return
        self.last_context=cmds.currentCtx() or ''
        name=native.quad_mesh()
        self.quad_mesh=Mesh(name) if name else None

    def scene_changed(self,*unused):
        self.cancel()
        self.quad_mesh=None
        self.last_context=cmds.currentCtx() or ''
        self.tab_down=self.b_down=False

    def tool_changed(self,*unused):
        previous=self.last_context
        current=cmds.currentCtx() or ''
        self.last_context=current
        self.cancel()
        self.tab_down=self.b_down=False
        if 'quaddraw' in current.lower():
            self.remember_quad_mesh()
        elif 'quaddraw' in previous.lower() and 'multicut' in current.lower():
            # Quad Draw owns appendMesh separately from active selection.
            # Multi-Cut cannot inherit that empty-selection editing state.
            if self.quad_mesh and not cmds.ls(selection=True) and not cmds.ls(hilite=True):
                try:
                    native.select_for_tool(self.quad_mesh)
                except (RuntimeError,ValueError):
                    pass  # Deleted/replaced mesh: never select a stale object.
            self.quad_mesh=None
        else:
            self.quad_mesh=None

    def correct_selection(self):
        """Do not edit the bound mesh after the user selects another build mesh."""
        selected = cmds.ls(selection=True, objectsOnly=True, long=True) or []
        target_names = {m.name for m in self.targets.meshes}
        for node in selected:
            try:
                mesh = Mesh(node)
            except (ValueError, RuntimeError):
                continue
            if mesh.name not in target_names and mesh.name != self.low.name:
                self.status('当前选择了其他低模，请重新绑定后再使用辅助编辑。')
                return False
        return True

    def stop(self,preserve_cache=False):
        global CACHED_TARGETS
        self.cancel()
        if self.targets:
            if preserve_cache and self.auto_bind and self.targets._surfaces is not None:
                clear_cache()
                CACHED_TARGETS=self.targets
            else:self.targets.close()
            self.targets=None
        QtWidgets.QApplication.instance().removeEventFilter(self)
        for job in self.jobs:
            if cmds.scriptJob(exists=job):
                cmds.scriptJob(kill=job, force=True)
        self.jobs = []
        if self.tool_callback is not None:
            om.MMessage.removeCallback(self.tool_callback)
            self.tool_callback=None
        self.status('已停用，全部鼠标操作交还原生 Quad Draw。')

    def cancel(self, *unused):
        stroke, self.stroke = self.stroke, None
        if stroke:
            self.swallow_release = True
            try:
                self.low.set_points(stroke['before'])
                stroke['view'].refresh(False, True)
            except RuntimeError:
                pass  # Mesh may have been deleted while opening a different scene.
        self.restore_cursor()

    def restore_cursor(self):
        if self.cursor_active:
            QtWidgets.QApplication.restoreOverrideCursor()
        self.cursor_active = False
        self.cursor_mode = None

    def viewport(self, watched):
        if not isinstance(watched, QtWidgets.QWidget):
            return None
        for panel in cmds.getPanel(type='modelPanel') or []:
            try:
                view = omui.M3dView.getM3dViewFromModelPanel(panel)
                widget = wrapInstance(int(view.widget()), QtWidgets.QWidget)
                if watched == widget or widget.isAncestorOf(watched):
                    return view, widget
            except (RuntimeError, ValueError):
                continue
        return None

    @staticmethod
    def coordinates(event, view, widget):
        point = widget.mapFromGlobal(global_position(event))
        sx = view.portWidth() / max(widget.width(), 1)
        sy = view.portHeight() / max(widget.height(), 1)
        return point.x() * sx, view.portHeight() - 1 - point.y() * sy, sx

    @staticmethod
    def projected(view, points):
        return [view.worldToView(p) for p in points]

    @staticmethod
    def view_signature(view):
        if not hasattr(view,'modelViewMatrix'):return None
        return (view.portWidth(),view.portHeight(),tuple(view.modelViewMatrix()),
                tuple(view.projectionMatrix()))

    def stroke_screen(self):
        s=self.stroke
        signature=self.view_signature(s['view'])
        if signature is None or signature!=s['view_signature']:
            s['screen']=self.projected(s['view'],s['points'])
            s['visibility_screen'][:]=self.projected(s['view'],s['surface'].points)
            s['surface'].cache.clear()
            s['view_signature']=signature
        return s['screen']

    @staticmethod
    def nearest(points, screen, view, x, y, radius, allowed=None,visible=None):
        origin, direction = view_ray(view, x, y)
        candidates = []
        indices = range(len(points)) if allowed is None else allowed
        for i in indices:
            px, py, shown = screen[i]
            if not shown:
                continue
            distance2 = (px - x) ** 2 + (py - y) ** 2
            if distance2 > radius*radius:continue
            depth = (points[i] - origin) * direction
            if distance2 <= radius * radius and depth >= 0:
                if visible is not None and not visible(i):
                    continue
                candidates.append((distance2, depth, i))
        return min(candidates)[2] if candidates else None

    def begin(self, view, widget, x, y, scale, smooth):
        if smooth and not self.relax_enabled:
            return False
        if not cmds.undoInfo(query=True, state=True):
            self.status('请先开启 Maya Undo；插件不会进行无法撤销的编辑。')
            return False
        points = self.low.points()
        screen = self.projected(view, points)
        visibility_screen=list(screen)
        surface=FrontSurface(self.low,points,lambda px,py:view_ray(view,px,py))
        visible=lambda i:surface.visible(i,visibility_screen)
        seed = self.nearest(points, screen, view, x, y, self.pick_radius * scale,visible=visible)
        if smooth:
            origin, direction = view_ray(view, x, y)
            # Shift over an existing low-poly face means relax. Empty space is
            # still native Quad Draw's create-face gesture, even near the brush.
            hit = surface.hit(x,y)
            if hit is None:
                return False
            face = list(self.low.fn.getPolygonVertices(hit[2]))
            seed = self.nearest(points, screen, view, x, y,
                                self.brush_radius * scale, face,visible)
        if seed is None:
            return False
        self.intercepting = True
        neighbors, border = self.low.adjacency()
        connected, todo = {seed}, [seed]
        while todo:
            for j in neighbors[todo.pop()]:
                if j not in connected:
                    connected.add(j)
                    todo.append(j)
        relax_allowed,relax_neighbors=connected,neighbors
        if smooth:
            relax_allowed,relax_neighbors=relax_region(self.low,neighbors,border,seed,
                native.relax_mode(),self.lock_border)
            relax_allowed=connected.intersection(relax_allowed)
        origin, normal = view_ray(view, x, y)
        before = self.low.points(False)
        symmetry = Symmetry.read(self.low,points)
        if symmetry and seed not in symmetry.pairs:
            raise ValueError('该点没有可确认的对称点，请检查低模对称性或 Maya 对称容差。')
        weld_enabled,weld_tolerance = native.weld_settings()
        soft_weights=soft_selection.weights(self.low,seed)
        if soft_weights is not None:
            soft_weights={i:w for i,w in soft_weights.items() if visible(i)}
        self.swallow_release = False
        self.stroke = dict(view=view, widget=widget, scale=scale, before=before,
            surface=surface,visible=visible,soft_weights=soft_weights,
            screen=screen,visibility_screen=visibility_screen,view_signature=self.view_signature(view),
            smooth_mode=self.smooth_mode,local_relax=None,
            relax_allowed=relax_allowed,relax_neighbors=relax_neighbors,
            symmetry=symmetry,weld_enabled=weld_enabled,weld_tolerance=weld_tolerance,weld_pairs=[],
            points=points, object_points=om.MPointArray(before), seed=seed,
            neighbors=neighbors, border=border, connected=connected,
            inverse=self.low.path.inclusiveMatrixInverse(), smooth=smooth,
            start=(x, y), last_time=0.0, last_applied=None, changed=False, moved=False,
            drag_offset=(screen[seed][0] - x, screen[seed][1] - y),
            plane_point=om.MPoint(points[seed]), plane_normal=om.MVector(normal))
        return True

    def surface_point(self, view, x, y):
        origin, direction = view_ray(view, x, y)
        hit = self.targets.hit(origin, direction)
        if hit is None:
            return None
        point = hit[0]
        if self.offset:
            normal = hit[2].fn.getPolygonNormal(hit[3], om.MSpace.kWorld)
            point += normal * self.offset
        return point

    @staticmethod
    def plane_point(view, x, y, point, normal):
        origin, ray = view_ray(view, x, y)
        denom = ray * normal
        if abs(denom) < 1.0e-10:
            return point
        return origin + ray * (((point - origin) * normal) / denom)

    def step(self, x, y, force=False):
        s = self.stroke
        if s is None:
            return
        if s['smooth'] and not self.relax_enabled:
            self.cancel()
            return
        # Mouse release normally repeats the last mouse-move coordinate. It
        # must commit the preview, not apply an extra relaxation iteration.
        if s['smooth'] and s['last_applied']==(x,y):
            return
        if not s['moved'] and math.hypot(x-s['start'][0], y-s['start'][1]) < 2*s['scale']:
            return
        s['moved'] = True
        now = monotonic()
        if not force and now - s['last_time'] < 1.0/60:
            return
        s['last_time'] = now
        view, points = s['view'], s['points']
        screen = self.stroke_screen()
        updates = {}
        if not s['smooth']:
            dx, dy = s['drag_offset']
            point = self.surface_point(view, x + dx, y + dy)
            if point is not None:
                updates[s['seed']] = point
                if s['soft_weights'] is not None:
                    original=s['surface'].points
                    delta=point-original[s['seed']]
                    for i,weight in s['soft_weights'].items():
                        if i==s['seed']:continue
                        moved=original[i]+delta*weight
                        px,py,shown=view.worldToView(moved)
                        if shown:
                            hit=self.surface_point(view,px,py)
                            if hit is not None:updates[i]=hit
        else:
            radius = self.brush_radius * s['scale']
            seed = self.nearest(points, screen, view, x, y, radius, s['relax_allowed'],s['visible'])
            if seed is None:
                return
            center = self.plane_point(view, x, y, points[seed], s['plane_normal'])
            side = self.plane_point(view, x+radius, y, points[seed], s['plane_normal'])
            world_radius = (center-side).length()
            distances = connected_brush(points, s['relax_neighbors'], seed, world_radius)
            weights = {}
            for i, distance in distances.items():
                px, py, visible = screen[i]
                t = max(math.hypot(px-x, py-y) / radius,
                        distance/max(world_radius, 1.0e-10))
                if i in s['relax_allowed'] and visible and t < 1 and s['visible'](i):
                    weights[i] = (1-t*t)**2
            if s['soft_weights'] is not None:
                weights={i:w for i,w in s['soft_weights'].items() if i in s['relax_allowed']}
            if not weights:
                return
            if s['smooth_mode']=='local':
                if s['local_relax'] is None:
                    s['local_relax']=LocalRelax(self.targets,s['surface'].points,s['neighbors'])
                    unused,ids=s['surface'].fn.getTriangles()
                    s['triangles']=TriangleIndex(tuple(ids[i:i+3]) for i in range(0,len(ids),3))
                updates=s['local_relax'].relax(points,weights,self.strength,
                    offset=self.offset,neighbors=s['relax_neighbors'])
            else:
                relaxed = relax_positions(points, s['relax_neighbors'], weights, self.strength)
                for i, point in relaxed.items():
                    px, py, visible = view.worldToView(point)
                    if visible:
                        hit = self.surface_point(view, px, py)
                        if hit is not None:
                            updates[i] = hit
        s['last_applied']=(x,y)
        if updates and s['symmetry']:
            updates = s['symmetry'].apply(updates,s['seed'])
        if updates and s['smooth'] and s['smooth_mode']=='local':
            updates=prevent_flips(points,updates,s['triangles'])
        s['weld_pairs'] = []
        if not s['smooth'] and s['seed'] in updates and s['weld_enabled']:
            radius = s['weld_tolerance'] * s['scale']
            p = updates[s['seed']]
            px,py,_ = view.worldToView(p)
            a = self.plane_point(view,px,py,p,s['plane_normal'])
            b = self.plane_point(view,px+radius,py,p,s['plane_normal'])
            updates,s['weld_pairs'] = welding.plan(points,updates,s['seed'],view,
                radius,(a-b).length(),s['symmetry'],s['visible'])
        if updates:
            for i, point in updates.items():
                s['points'][i] = point
                s['object_points'][i] = point * s['inverse']
                s['screen'][i]=view.worldToView(point)
            self.low.set_points(s['object_points'])
            s['changed'] = True
            view.refresh(False, True)
        self.update_cursor()

    def update_cursor(self):
        s = self.stroke
        if not s:
            return
        mode = bool(s['weld_pairs'])
        if self.cursor_active and mode == self.cursor_mode:
            return
        # An OS cursor does not add a QWidget over Maya's native GL viewport.
        # Transparent child overlays caused grey frames and accumulated rings.
        pixmap = QtGui.QPixmap(32,32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtGui.QPen(QtGui.QColor('#ffcc55' if mode else '#53e3e8'),2))
        painter.drawEllipse(QtCore.QPointF(16,16),11,11)
        painter.drawLine(13,16,19,16)
        painter.drawLine(16,13,16,19)
        painter.end()
        cursor = QtGui.QCursor(pixmap,16,16)
        if self.cursor_active:
            QtWidgets.QApplication.changeOverrideCursor(cursor)
        else:
            QtWidgets.QApplication.setOverrideCursor(cursor)
        self.cursor_active = True
        self.cursor_mode = mode

    def finish(self):
        s, self.stroke = self.stroke, None
        self.restore_cursor()
        if s and s['changed']:
            bridge.commit(self.low, s['before'], s['object_points'],s['weld_pairs'])
            s['view'].refresh(False, True)

    def eventFilter(self, watched, event):
        if self.busy:
            return False
        kind = event.type()
        if kind not in (Event.KeyPress, Event.KeyRelease, Event.MouseButtonPress,
                        Event.MouseButtonRelease, Event.MouseMove,
                        Event.ApplicationDeactivate):
            return False
        was_stroking = self.stroke is not None
        self.intercepting = False
        self.busy = True
        try:
            if kind == Event.ApplicationDeactivate:
                self.tab_down = False
                self.b_down = False
                self.cancel()
                return False
            # Remember the actual native mesh before a marking-menu or tool
            # button command runs, including meshes created since last stroke.
            if kind in (Event.KeyPress,Event.MouseButtonPress):
                self.remember_quad_mesh()
            if kind in (Event.KeyPress, Event.KeyRelease):
                if event.key() == Qt.Key.Key_Tab:
                    self.tab_down = kind == Event.KeyPress
                if event.key() == Qt.Key.Key_B:
                    self.b_down = kind == Event.KeyPress
                if self.stroke and kind == Event.KeyPress:
                    if event.key() == Qt.Key.Key_Escape:
                        self.cancel()
                        return True
                    if event.key() not in (Qt.Key.Key_Shift, Qt.Key.Key_Control,
                                           Qt.Key.Key_Alt):
                        self.cancel()
                return False
            if self.stroke:
                s = self.stroke
                x, y, unused = self.coordinates(event, s['view'], s['widget'])
                if kind == Event.MouseMove:
                    self.step(x, y)
                    return True
                if kind == Event.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                    self.step(x, y, force=True)
                    self.finish()
                    return True
                return True
            if self.swallow_release:
                if kind == Event.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                    self.swallow_release = False
                    return True
                if kind == Event.MouseMove:
                    return bool(event.buttons() & Qt.MouseButton.LeftButton)
                if kind == Event.MouseButtonPress:
                    self.swallow_release = False
            if kind != Event.MouseButtonPress or event.button() != Qt.MouseButton.LeftButton:
                return False
            if not quad_active() or self.tab_down or self.b_down:
                return False
            modifiers = event.modifiers()
            if modifiers & (Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ControlModifier
                            | Qt.KeyboardModifier.MetaModifier):
                return False
            smooth=bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
            if smooth and not self.relax_enabled:
                return False
            viewport = self.viewport(watched)
            if viewport is None:
                return False
            if not self.refresh_binding():
                return False
            if not self.correct_selection():
                return False
            view, widget = viewport
            x, y, scale = self.coordinates(event, view, widget)
            return self.begin(view, widget, x, y, scale,smooth)
        except Exception as exc:
            self.cancel()
            self.status('已取消本次操作：' + as_text(exc))
            cmds.warning('HTools_QuadDrawThrough: ' + as_text(exc))
            traceback.print_exc()
            # Never pass a partially consumed drag into native Quad Draw.
            consumed = was_stroking or self.intercepting
            if consumed:
                self.swallow_release = True
            return consumed
        finally:
            self.busy = False


def enable(low=None, targets=None, status=None):
    global ACTIVE
    disable()
    controller = Controller(low, targets, status)
    try:
        controller.install()
    except Exception:
        controller.stop()
        raise
    ACTIVE = controller
    return controller


def disable(preserve_cache=True):
    global ACTIVE
    if ACTIVE:
        ACTIVE.stop(preserve_cache=preserve_cache)
    ACTIVE = None
