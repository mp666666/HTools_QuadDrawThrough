# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
"""Run using mayapy. Uses a fresh standalone scene only."""
from __future__ import division, unicode_literals
import os
import sys
import unittest
try:
    from unittest import mock
except ImportError:
    output=os.environ.get('HTOOLS_TEST_OUTPUT',os.path.join(os.path.dirname(__file__),'_output'))
    sys.path.insert(0,os.path.join(output,'vendor'))
    import mock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
APP = QtWidgets.QApplication([])
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import maya.api.OpenMaya as om
from qd_through.geometry import Mesh, Targets, connected_brush, relax_positions, relax_region
from qd_through import bridge, interaction, native, welding, soft_selection
from qd_through.symmetry import Symmetry
from qd_through.local_relax import LocalRelax,Surface,prevent_flips,TriangleIndex


class FakeView(object):
    """Orthographic view from +Z: 20 px/cm, 400x400 viewport."""
    def worldToView(self, p):
        return int(round(200+p.x*20)), int(round(200+p.y*20)), True

    def viewToWorld(self, x, y, origin, direction):
        origin.x, origin.y, origin.z = (x-200)/20, (y-200)/20, 10
        direction.x, direction.y, direction.z = 0, 0, -1
        return self

    def portWidth(self):
        return 400

    def portHeight(self):
        return 400

    def refresh(self, *args):
        pass


def plane(name, z, divisions=2):
    obj = cmds.polyPlane(name=name, axis=(0, 0, 1), width=8, height=8,
                         subdivisionsX=divisions, subdivisionsY=divisions,
                         constructionHistory=False)[0]
    cmds.move(0, 0, z, obj)
    return obj


class PluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        bridge.ensure_plugin()

    def setUp(self):
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.symmetricModelling(symmetry=False)
        cmds.softSelect(softSelectEnabled=False,softSelectFalloff=0)
        self.front = plane('front', 1)
        self.back = plane('back', -0.1)
        self.low = plane('low', 0)
        self.view = FakeView()
        self.widget = QtWidgets.QWidget()
        self.widget.resize(400, 400)

    def tearDown(self):
        interaction.disable()
        interaction.clear_cache()
        self.widget.deleteLater()

    def controller(self):
        c=interaction.Controller(self.low, [self.front, self.back])
        c.smooth_mode='view'  # Preserve explicit coverage of the legacy repair mode.
        return c

    def test_distant_camera_hits_accelerated_multilayer_high(self):
        front=plane('dense_front',1,20)
        back=plane('dense_back',-0.1,10)
        high=cmds.polyUnite(front,back,ch=False)[0]
        targets=Targets([high])
        hit=targets.hit(om.MPoint(0.6822529,0.1211477,1000),om.MVector(0,0,-1))
        self.assertIsNotNone(hit)
        self.assertAlmostEqual(hit[0].z,1,places=5)
        self.assertAlmostEqual(hit[1],999,places=4)
        self.assertIsNone(targets.hit(om.MPoint(12,12,1000),om.MVector(0,0,-1)))

    def test_distant_camera_keeps_rear_low_vertices_occluded(self):
        from qd_through.visibility import FrontSurface
        front=plane('dense_low_front',1,20)
        back=plane('dense_low_back',-0.1,20)
        low=Mesh(cmds.polyUnite(front,back,ch=False)[0])
        points=low.points()
        ray=lambda x,y:(om.MPoint((x-200)/20.0,(y-200)/20.0,1000),om.MVector(0,0,-1))
        surface=FrontSurface(low,points,ray)
        screen=interaction.Controller.projected(self.view,points)
        self.assertTrue(surface.visible(220,screen))
        self.assertFalse(surface.visible(441+220,screen))

    def test_relax_disabled_passes_shift_without_binding_but_drag_still_works(self):
        c=self.controller()
        c.relax_enabled=False
        self.assertFalse(c.begin(self.view,self.widget,200,200,1,True))
        self.assertIsNone(c.stroke)
        qt=QtCore.Qt
        point=QtCore.QPointF(200,199)
        glob=QtCore.QPointF(self.widget.mapToGlobal(point.toPoint()))
        shift=QtGui.QMouseEvent(QtCore.QEvent.Type.MouseButtonPress,point,glob,
            qt.MouseButton.LeftButton,qt.MouseButton.LeftButton,qt.KeyboardModifier.ShiftModifier)
        with mock.patch.object(interaction,'quad_active',return_value=True), \
             mock.patch.object(c,'refresh_binding') as binding:
            self.assertFalse(c.eventFilter(self.widget,shift))
            binding.assert_not_called()
        self.assertTrue(c.begin(self.view,self.widget,200,200,1,False))
        c.step(220,210,force=True);c.finish()
        self.assertAlmostEqual(c.low.points()[4].z,1,places=5)

    def test_relax_disable_mid_stroke_restores_preview_without_affecting_drag(self):
        c=self.controller()
        original=c.low.points()
        old_settings=dict(interaction.SETTINGS)
        interaction.ACTIVE=c
        try:
            self.assertTrue(c.begin(self.view,self.widget,200,200,1,True))
            c.step(204,202,force=True)
            self.assertGreater((c.low.points()[4]-original[4]).length(),0.1)
            interaction.configure(relax_enabled=False)
            self.assertIsNone(c.stroke)
            self.assertTrue(all((a-b).length()<1e-7 for a,b in zip(c.low.points(),original)))
            self.assertTrue(c.begin(self.view,self.widget,200,200,1,False))
            c.step(220,210,force=True)
            interaction.configure(relax_enabled=False)
            self.assertIsNotNone(c.stroke)
            c.finish()
        finally:
            interaction.SETTINGS.clear();interaction.SETTINGS.update(old_settings)

    def test_relax_release_does_not_add_iteration_but_flushes_pending_position(self):
        cmds.move(0.8,0.5,0,self.low+'.vtx[4]',relative=True)
        c=self.controller();c.smooth_mode='local'
        c.begin(self.view,self.widget,216,210,1,True)
        c.step(220,210,force=True)
        preview=c.low.points()
        c.step(220,210,force=True)
        self.assertTrue(all((a-b).length()<1e-9 for a,b in zip(c.low.points(),preview)))
        c.step(223,210,force=True)
        self.assertGreater((c.low.points()[4]-preview[4]).length(),0.001)
        c.cancel()

    def test_auto_lock_interior_and_border_follow_native_setting(self):
        mesh=Mesh(self.low);neighbors,border=mesh.adjacency()
        allowed,unused=relax_region(mesh,neighbors,border,4,3)
        self.assertEqual(allowed,{4})
        allowed,boundary_neighbors=relax_region(mesh,neighbors,border,1,3)
        self.assertEqual(allowed,border)
        self.assertNotIn(4,boundary_neighbors[1])
        # A straight boundary stays straight; internal neighbors must not pull
        # it into the surface as the old all-neighbor average did.
        points=mesh.points()
        boundary=relax_positions(points,boundary_neighbors,{1:1},0.22)
        all_points=relax_positions(points,neighbors,{1:1},0.22)
        self.assertLess((boundary[1]-points[1]).length(),1e-8)
        self.assertGreater((all_points[1]-points[1]).length(),0.1)
        with mock.patch.object(native,'relax_mode',return_value=3):
            c=self.controller()
            self.assertTrue(c.begin(self.view,self.widget,200,200,1,True))
            self.assertEqual(c.stroke['relax_allowed'],{4})
            c.cancel()

    def test_boundary_relax_stays_on_one_continuous_loop_and_manual_lock_wins(self):
        tube=cmds.polyCylinder(r=2,h=4,sx=12,sy=2,sz=1,ch=False)[0]
        mesh=Mesh(tube)
        # Removing both end caps leaves one surface with two disjoint borders.
        ids=[i for i in range(mesh.fn.numPolygons) if abs(mesh.fn.getPolygonNormal(i).y)>0.9]
        cmds.delete([tube+'.f[%d]'%i for i in ids])
        neighbors,border=mesh.adjacency();points=mesh.points()
        seed=min(border,key=lambda i:points[i].y)
        allowed,boundary=relax_region(mesh,neighbors,border,seed,2)
        self.assertTrue(allowed)
        self.assertLess(len(allowed),len(border))
        self.assertTrue(all(abs(points[i].y-points[seed].y)<1e-6 for i in allowed))
        interior,unused=relax_region(mesh,neighbors,border,seed,3,True)
        self.assertFalse(interior.intersection(border))
        self.assertTrue(interior)
        all_ids,unused=relax_region(mesh,neighbors,border,seed,0)
        self.assertEqual(len(all_ids),mesh.fn.numVertices)

    def test_multicut_handoff_restores_empty_build_selection_without_undo(self):
        c=self.controller();c.quad_mesh=c.low;c.last_context='nexQuadDrawCtx1'
        cmds.select(clear=True);cmds.flushUndo()
        with mock.patch.object(cmds,'currentCtx',return_value='nexMultiCutCtx1'):
            c.tool_changed()
        self.assertEqual(Mesh(cmds.ls(sl=True)[0]).name,c.low.name)
        self.assertTrue(cmds.undoInfo(q=True,undoQueueEmpty=True))
        self.assertIsNone(c.quad_mesh)

    def test_multicut_handoff_respects_other_selection_highlight_and_tools(self):
        c=self.controller();other=plane('another_low',0)
        for context,selection,hilite in [('nexMultiCutCtx1',[other],[]),
                ('nexMultiCutCtx1',[],[other]),('selectSuperContext',[],[])]:
            cmds.select(clear=True)
            if selection:cmds.select(selection)
            cmds.hilite(other,unHilite=True)
            if hilite:cmds.hilite(hilite)
            c.quad_mesh=c.low;c.last_context='nexQuadDrawCtx1'
            with mock.patch.object(cmds,'currentCtx',return_value=context):
                c.tool_changed()
            self.assertEqual(cmds.ls(sl=True),selection)
        c.quad_mesh=c.low;c.last_context='nexQuadDrawCtx1'
        cmds.delete(self.low)
        with mock.patch.object(cmds,'currentCtx',return_value='nexMultiCutCtx1'):
            c.tool_changed()
        self.assertFalse(cmds.ls(sl=True))

    def test_first_hit_not_nearest_layer(self):
        t = Targets([self.back, self.front])
        hit = t.hit(om.MPoint(0, 0, 10), om.MVector(0, 0, -1))
        self.assertAlmostEqual(hit[0].z, 1, places=5)
        # The same rule works when both shells belong to a single shape.
        combined = cmds.polyUnite(self.front, self.back, ch=False)[0]
        hit = Targets([combined]).hit(om.MPoint(0, 0, 10), om.MVector(0, 0, -1))
        self.assertAlmostEqual(hit[0].z, 1, places=5)

    def test_occluded_vertex_drag_and_one_step_undo_redo(self):
        c = self.controller()
        original = c.low.points(False)
        cmds.flushUndo()
        self.assertTrue(c.begin(self.view, self.widget, 200, 200, 1, False))
        c.step(220, 210, force=True)
        c.finish()
        moved = c.low.points()[4]
        self.assertAlmostEqual(moved.x, 1, places=5)
        self.assertAlmostEqual(moved.y, 0.5, places=5)
        self.assertAlmostEqual(moved.z, 1, places=5)
        self.assertEqual(cmds.undoInfo(q=True, undoName=True), 'HTools_QuadDrawThrough')
        cmds.undo()
        self.assertLess((c.low.points(False)[4]-original[4]).length(), 1e-8)
        cmds.redo()
        self.assertAlmostEqual(c.low.points()[4].z, 1, places=5)
        self.assertEqual(c.low.fn.numVertices, 9)

    def test_cancel_and_no_intersection(self):
        c = self.controller()
        before = c.low.points(False)
        c.begin(self.view, self.widget, 200, 200, 1, False)
        c.step(220, 200, force=True)
        c.cancel()
        self.assertLess((c.low.points(False)[4]-before[4]).length(), 1e-8)
        c.begin(self.view, self.widget, 200, 200, 1, False)
        c.step(399, 399, force=True)
        c.finish()
        self.assertLess((c.low.points(False)[4]-before[4]).length(), 1e-8)

    def test_smooth_occluded_center_keeps_boundary(self):
        cmds.move(0.8, 0.5, 0, self.low+'.vtx[4]', relative=True)
        c = self.controller()
        before = c.low.points()
        c.brush_radius = 110
        c.lock_border = True
        c.begin(self.view, self.widget, 216, 210, 1, True)
        c.step(220, 210, force=True)
        c.finish()
        after = c.low.points()
        self.assertLess(after[4].x, before[4].x)
        self.assertAlmostEqual(after[4].z, 1, places=5)
        for i in (0, 1, 2, 3, 5, 6, 7, 8):
            self.assertLess((after[i]-before[i]).length(), 1e-8)

    def test_graph_brush_does_not_cross_detached_shell(self):
        p = [om.MPoint(0,0,0), om.MPoint(1,0,0),
             om.MPoint(0,0,0.01), om.MPoint(1,0,0.01)]
        found = connected_brush(p, [[1], [0], [3], [2]], 0, 3)
        self.assertEqual(set(found), {0,1})

    def test_empty_space_passes_through_for_native_creation(self):
        c = self.controller()
        self.assertFalse(c.begin(self.view, self.widget, 390, 390, 1, False))
        self.assertFalse(c.begin(self.view, self.widget, 390, 390, 1, True))
        self.assertIsNone(c.stroke)

    def test_shift_in_small_hole_near_vertex_still_creates_native_face(self):
        cmds.delete(self.low+'.f[0]')
        c = self.controller()
        # Bottom-left face is absent. This point is within pick radius of its
        # remaining corner, but Shift must still reach native face creation.
        self.assertFalse(c.begin(self.view,self.widget,124,124,1,True))

    def test_transformed_low_and_topology_refresh(self):
        cmds.setAttr(self.low+'.scaleX', 1.5)
        cmds.setAttr(self.low+'.translateZ', 0.2)
        c = self.controller()
        c.begin(self.view, self.widget, 200, 200, 1, False)
        c.step(220, 200, force=True)
        c.finish()
        self.assertAlmostEqual(c.low.points()[4].x, 1, places=5)
        self.assertAlmostEqual(c.low.points()[4].z, 1, places=5)
        cmds.polySubdivideFacet(self.low+'.f[0]', divisions=1, ch=False)
        p = c.low.points()[0]
        x,y,_ = self.view.worldToView(p)
        self.assertTrue(c.begin(self.view, self.widget, x,y,1,False))
        c.cancel()

    def test_event_dispatch_preserves_native_modifiers(self):
        c = self.controller()
        c.viewport = lambda watched: (self.view, self.widget)
        real_quad = interaction.quad_active
        interaction.quad_active = lambda: True
        qt = QtCore.Qt
        def press(mods=qt.KeyboardModifier.NoModifier):
            local = QtCore.QPointF(200,199)
            glob = QtCore.QPointF(self.widget.mapToGlobal(local.toPoint()))
            return QtGui.QMouseEvent(QtCore.QEvent.Type.MouseButtonPress, local, glob,
                qt.MouseButton.LeftButton, qt.MouseButton.LeftButton, mods)
        try:
            for mod in (qt.KeyboardModifier.AltModifier, qt.KeyboardModifier.ControlModifier):
                self.assertFalse(c.eventFilter(self.widget, press(mod)))
            c.tab_down = True
            self.assertFalse(c.eventFilter(self.widget, press()))
            c.tab_down = False
            c.b_down = True
            self.assertFalse(c.eventFilter(self.widget, press()))
            c.b_down = False
            self.assertTrue(c.eventFilter(self.widget, press()))
            c.cancel()
            interaction.quad_active = lambda: False
            self.assertFalse(c.eventFilter(self.widget, press()))
        finally:
            interaction.quad_active = real_quad

    def test_high_mesh_unchanged(self):
        c = self.controller()
        high = Mesh(self.front)
        before = high.points(False)
        c.begin(self.view, self.widget, 200,200,1,False)
        c.step(220,200,force=True)
        c.finish()
        self.assertTrue(all((a-b).length() < 1e-8 for a,b in zip(before,high.points(False))))

    def test_failed_existing_vertex_press_does_not_create_native_dot(self):
        c=self.controller()
        c.viewport=lambda watched:(self.view,self.widget)
        qt=QtCore.Qt
        local=QtCore.QPointF(200,199)
        glob=QtCore.QPointF(self.widget.mapToGlobal(local.toPoint()))
        press=QtGui.QMouseEvent(QtCore.QEvent.Type.MouseButtonPress,local,glob,
            qt.MouseButton.LeftButton,qt.MouseButton.LeftButton,qt.KeyboardModifier.NoModifier)
        release=QtGui.QMouseEvent(QtCore.QEvent.Type.MouseButtonRelease,local,glob,
            qt.MouseButton.LeftButton,qt.MouseButton.NoButton,qt.KeyboardModifier.NoModifier)
        with mock.patch.object(interaction,'quad_active',return_value=True), \
             mock.patch.object(Symmetry,'read',side_effect=RuntimeError('injected failure')), \
             mock.patch.object(interaction.traceback,'print_exc'):
            self.assertTrue(c.eventFilter(self.widget,press))
            self.assertIsNone(c.stroke)
            self.assertTrue(c.eventFilter(self.widget,release))
            self.assertFalse(c.swallow_release)

    def test_cursor_restored_on_cancel_without_viewport_children(self):
        c=self.controller()
        before=len(self.widget.findChildren(QtWidgets.QWidget))
        previous=QtWidgets.QApplication.overrideCursor()
        c.begin(self.view,self.widget,200,200,1,False)
        c.step(220,210,force=True)
        self.assertTrue(c.cursor_active)
        self.assertEqual(len(self.widget.findChildren(QtWidgets.QWidget)),before)
        c.cancel()
        self.assertFalse(c.cursor_active)
        self.assertEqual(QtWidgets.QApplication.overrideCursor(),previous)

    def test_different_low_selection_does_not_edit_bound_low(self):
        c = self.controller()
        other = plane('other_low', 0)
        cmds.select(other)
        self.assertFalse(c.correct_selection())
        cmds.select(self.low)
        self.assertTrue(c.correct_selection())

    def test_low_with_construction_history_retains_edits(self):
        low = cmds.polyPlane(name='history_low', axis=(0,0,1), width=8,height=8,
            subdivisionsX=2,subdivisionsY=2,constructionHistory=True)[0]
        c = interaction.Controller(low,[self.front])
        c.begin(self.view,self.widget,200,200,1,False)
        c.step(220,200,force=True)
        c.finish()
        cmds.dgdirty(low)
        self.assertAlmostEqual(c.low.points()[4].z,1,places=5)
        cmds.undo()
        self.assertAlmostEqual(c.low.points()[4].z,0,places=5)


class FeatureTests(unittest.TestCase):
    setUpClass = PluginTests.__dict__['setUpClass']
    setUp = getattr(PluginTests.setUp,'im_func',PluginTests.setUp)
    tearDown = getattr(PluginTests.tearDown,'im_func',PluginTests.tearDown)
    controller = getattr(PluginTests.controller,'im_func',PluginTests.controller)

    def test_native_symmetry_drag_undo_and_redo(self):
        cmds.symmetricModelling(symmetry=True,about='world',axis='x',tolerance=0.01)
        c = self.controller()
        before = c.low.points()
        self.assertTrue(c.begin(self.view,self.widget,280,200,1,False))
        c.step(260,210,force=True)
        c.finish()
        after = c.low.points()
        self.assertAlmostEqual(after[5].x,3)
        self.assertAlmostEqual(after[3].x,-3)
        self.assertAlmostEqual(after[3].y,0.5)
        self.assertAlmostEqual(after[3].z,1)
        cmds.undo()
        self.assertTrue(all((a-b).length()<1e-6 for a,b in zip(before,c.low.points())))
        cmds.redo()
        self.assertAlmostEqual(c.low.points()[3].z,1)

    def test_native_world_and_object_xyz_pairing(self):
        cube=cmds.polyCube(ch=False)[0]
        mesh=Mesh(cube)
        for space in ('world','object'):
            if space=='object':
                cmds.setAttr(cube+'.translate',2,3,4)
                cmds.setAttr(cube+'.rotate',20,35,10)
                cmds.setAttr(cube+'.scale',2,1,0.8)
            for axis in 'xyz':
                cmds.select(cube)
                cmds.symmetricModelling(symmetry=True,about=space,axis=axis,tolerance=0.01)
                symmetry=Symmetry.read(mesh,mesh.points())
                self.assertEqual(len(symmetry.pairs),8,(space,axis))
                p=mesh.points()[0]+om.MVector(0.1,0.2,0.3)
                result=symmetry.apply({0:p},0)
                self.assertLess((result[symmetry.pairs[0]]-p*symmetry.matrix).length(),1e-6)

    def test_center_seam_stays_on_plane(self):
        cmds.symmetricModelling(symmetry=True,about='world',axis='x',preserveSeam=1)
        c=self.controller()
        c.begin(self.view,self.widget,200,200,1,False)
        c.step(220,210,force=True)
        c.finish()
        self.assertAlmostEqual(c.low.points()[4].x,0)
        self.assertAlmostEqual(c.low.points()[4].y,0.5)

    def test_symmetric_relax_updates_both_sides(self):
        low=cmds.polyPlane(axis=(0,0,1),w=6,h=6,sx=4,sy=4,ch=False)[0]
        cmds.move(0.3,0.2,0,low+'.vtx[13]',relative=True)
        cmds.move(-0.3,0.2,0,low+'.vtx[11]',relative=True)
        cmds.symmetricModelling(symmetry=True,about='world',axis='x',tolerance=0.01)
        c=interaction.Controller(low,[self.front])
        c.smooth_mode='view'
        c.begin(self.view,self.widget,236,204,1,True)
        c.step(240,204,force=True)
        c.finish()
        a,b=c.low.points()[11],c.low.points()[13]
        self.assertAlmostEqual(a.x,-b.x)
        self.assertAlmostEqual(a.y,b.y)
        self.assertAlmostEqual(a.z,b.z)
        self.assertAlmostEqual(a.z,1)

    def test_weld_and_undo_restore_topology_with_history(self):
        low=cmds.polyPlane(axis=(0,0,1),w=8,h=8,sx=2,sy=2,ch=True)[0]
        cmds.move(0,0,1,low)
        c=interaction.Controller(low,[self.front])
        before=c.low.points()
        with mock.patch.object(native,'weld_settings',return_value=(True,10)):
            c.begin(self.view,self.widget,280,200,1,False)
            c.step(280,277,force=True)
            self.assertEqual(c.stroke['weld_pairs'],[(5,8)])
            self.assertEqual(c.low.fn.numVertices,9)
            c.finish()
        self.assertEqual(c.low.fn.numVertices,8)
        self.assertTrue(cmds.listHistory(low))
        cmds.undo()
        self.assertEqual(c.low.fn.numVertices,9)
        self.assertTrue(all((a-b).length()<1e-6 for a,b in zip(before,c.low.points())))
        cmds.redo()
        self.assertEqual(c.low.fn.numVertices,8)
        self.assertTrue(c.low.fn.numUVs()>0)

    def test_symmetric_weld_commits_both_pairs_as_one_undo(self):
        cmds.move(0,0,1,self.low)
        cmds.symmetricModelling(symmetry=True,about='world',axis='x',tolerance=0.01)
        c=self.controller()
        with mock.patch.object(native,'weld_settings',return_value=(True,10)):
            c.begin(self.view,self.widget,280,200,1,False)
            c.step(280,277,force=True)
            self.assertEqual(set(c.stroke['weld_pairs']),{(5,8),(3,6)})
            c.finish()
        self.assertEqual(c.low.fn.numVertices,7)
        cmds.undo()
        self.assertEqual(c.low.fn.numVertices,9)
        cmds.redo()
        self.assertEqual(c.low.fn.numVertices,7)

    def test_screen_overlap_different_depth_does_not_weld(self):
        points=[om.MPoint(0,0,1),om.MPoint(0,0,-1)]
        result,pairs=welding.plan(points,{0:points[0]},0,self.view,10,0.5)
        self.assertEqual(pairs,[])

    def test_symmetric_center_weld_snaps_to_seam(self):
        matrix=om.MMatrix([-1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1])
        points=[om.MPoint(-1,0,1),om.MPoint(1,0,1)]
        symmetry=Symmetry(points,matrix,0.01)
        updates=symmetry.apply({1:om.MPoint(0.05,0,1)},1)
        result,pairs=welding.plan(points,updates,1,self.view,10,0.5,symmetry)
        self.assertEqual(len(pairs),1)
        self.assertAlmostEqual(result[0].x,0)
        self.assertAlmostEqual(result[1].x,0)

    def test_auto_binding_follows_live_and_selected_low(self):
        c=interaction.Controller()
        cmds.makeLive(self.front)
        cmds.select(self.low)
        self.assertTrue(c.refresh_binding())
        self.assertEqual(c.low.name,Mesh(self.low).name)
        other=plane('secondLow',0)
        cmds.makeLive(self.back)
        cmds.select(other)
        self.assertTrue(c.refresh_binding())
        self.assertEqual(c.low.name,Mesh(other).name)
        self.assertEqual(c.targets.meshes[0].name,Mesh(self.back).name)
        cmds.makeLive(none=True)
        self.assertFalse(c.refresh_binding())

    def test_soft_selection_disables_auto_weld(self):
        cmds.softSelect(softSelectEnabled=True)
        self.assertEqual(native.weld_settings(),(False,0.0))

    def test_weld_preview_cancel_preserves_vertex_count(self):
        cmds.move(0,0,1,self.low)
        c=self.controller()
        before=c.low.points()
        with mock.patch.object(native,'weld_settings',return_value=(True,10)):
            c.begin(self.view,self.widget,280,200,1,False)
            c.step(280,277,force=True)
            self.assertTrue(c.stroke['weld_pairs'])
            c.cancel()
        self.assertEqual(c.low.fn.numVertices,9)
        self.assertTrue(all((a-b).length()<1e-6 for a,b in zip(before,c.low.points())))

    def topology_low(self):
        self.low=plane('topoLow',0,4)
        mesh=Mesh(self.low)
        edge=om.MItMeshEdge(mesh.path)
        points=mesh.points()
        while not edge.isDone():
            if all(abs(points[edge.vertexId(k)].x)<1e-7 for k in (0,1)):
                break
            edge.next()
        cmds.select(self.low+'.e[%d]'%edge.index())
        cmds.symmetricModelling(about='topo',topoSymmetry=True,symmetry=True)
        cmds.select(self.low)
        return mesh

    def test_topology_native_pairs_preserve_selection_softselect_undo(self):
        mesh=self.topology_low()
        cmds.move(0.6,0.2,0.1,self.low+'.vtx[13]',relative=True)
        cmds.softSelect(softSelectEnabled=True)
        selected=cmds.ls(sl=True,long=True)
        undo=cmds.undoInfo(q=True,undoName=True)
        sym=Symmetry.read(mesh,mesh.points())
        self.assertEqual(sym.pairs,{i:(i//5)*5+4-i%5 for i in range(25)})
        self.assertEqual(sym.seams,{2,7,12,17,22})
        self.assertEqual(cmds.ls(sl=True,long=True),selected)
        self.assertEqual(cmds.undoInfo(q=True,undoName=True),undo)
        self.assertTrue(cmds.softSelect(q=True,softSelectEnabled=True))

    def test_topology_drag_preserves_asymmetric_offset_and_undo(self):
        mesh=self.topology_low()
        cmds.move(0.6,0.2,0.1,self.low+'.vtx[13]',relative=True)
        before=mesh.points()
        c=self.controller()
        self.assertTrue(c.begin(self.view,self.widget,252,204,1,False))
        sym=c.stroke['symmetry']
        c.step(256,208,force=True);c.finish()
        after=mesh.points()
        self.assertLess(((after[13]-before[13])*sym.matrix-(after[11]-before[11])).length(),1e-6)
        self.assertGreater(abs(after[13].x+after[11].x),0.5)
        cmds.undo()
        self.assertLess((mesh.points()[13]-before[13]).length(),1e-6)
        cmds.redo()
        self.assertLess((mesh.points()[11]-after[11]).length(),1e-6)

    def test_topology_relax_and_curved_seam(self):
        mesh=self.topology_low()
        cmds.move(0.3,0.2,0,self.low+'.vtx[12]',relative=True)
        cmds.move(0.6,0.2,0,self.low+'.vtx[13]',relative=True)
        before=mesh.points()
        sym=Symmetry.read(mesh,before)
        c=self.controller()
        self.assertTrue(c.begin(self.view,self.widget,252,204,1,True))
        c.step(254,204,force=True);c.finish()
        after=mesh.points()
        self.assertLess(((after[13]-before[13])*sym.matrix-(after[11]-before[11])).length(),1e-6)
        self.assertGreater((after[13]-before[13]).length(),0.01)
        result=sym.apply({12:before[12]+om.MVector(1,0,0)},12)
        self.assertAlmostEqual(result[12].x,before[12].x,places=5)

    def test_topology_weld_both_sides_and_rebuild_after_undo(self):
        mesh=self.topology_low()
        cmds.move(0,0,1,self.low)
        c=self.controller()
        with mock.patch.object(native,'weld_settings',return_value=(True,10)):
            c.begin(self.view,self.widget,240,200,1,False)
            c.step(240,237,force=True)
            self.assertEqual(set(c.stroke['weld_pairs']),{(13,18),(11,16)})
            c.finish()
        self.assertEqual(mesh.fn.numVertices,23)
        cmds.undo();self.assertEqual(mesh.fn.numVertices,25)
        self.assertEqual(len(Symmetry.read(mesh,mesh.points()).pairs),25)
        cmds.redo();self.assertEqual(mesh.fn.numVertices,23)
        self.assertEqual(len(Symmetry.read(mesh,mesh.points()).pairs),23)

    def test_topology_rejects_wrong_mesh(self):
        self.topology_low()
        other=Mesh(plane('unrelated',0))
        with self.assertRaises(ValueError):
            Symmetry.read(other,other.points())

    def test_empty_selection_object_world_symmetry_preserves_undo(self):
        mesh=Mesh(self.low)
        for mode in ('object','world'):
            cmds.symmetricModelling(symmetry=True,about=mode,axis='x')
            cmds.select(clear=True)
            undo=cmds.undoInfo(q=True,undoName=True)
            sym=Symmetry.read(mesh,mesh.points())
            self.assertEqual(sym.pairs[3],5)
            self.assertEqual(cmds.ls(sl=True),[])
            self.assertEqual(cmds.undoInfo(q=True,undoName=True),undo)
            c=self.controller()
            c.begin(self.view,self.widget,280,200,1,False)
            c.step(270,210,force=True);c.finish()
            self.assertAlmostEqual(mesh.points()[3].x,-mesh.points()[5].x,places=5)
            cmds.undo()

    def test_empty_selection_topology_symmetry(self):
        mesh=self.topology_low()
        cmds.select(clear=True)
        undo=cmds.undoInfo(q=True,undoName=True)
        sym=Symmetry.read(mesh,mesh.points())
        self.assertEqual(len(sym.pairs),25)
        self.assertEqual(cmds.ls(sl=True),[])
        self.assertEqual(cmds.undoInfo(q=True,undoName=True),undo)

    def test_rear_vertex_closer_on_screen_is_not_picked(self):
        rear=plane('rearLow',-0.1)
        cmds.move(0.4,0,0,self.low+'.vtx[4]',relative=True)
        self.low=cmds.polyUnite(self.low,rear,ch=False)[0]
        cmds.select(self.low)
        c=self.controller();before=c.low.points()
        self.assertTrue(c.begin(self.view,self.widget,200,200,1,False))
        self.assertEqual(c.stroke['seed'],4)
        c.step(220,210,force=True);c.finish()
        self.assertLess((c.low.points()[13]-before[13]).length(),1e-7)
        self.assertGreater((c.low.points()[4]-before[4]).length(),0.1)

    def test_closed_thin_mesh_relax_does_not_pull_back_to_front(self):
        self.low=cmds.polyCube(w=8,h=8,d=0.2,sx=4,sy=4,sz=1,ch=False)[0]
        c=self.controller();c.brush_radius=250
        before=c.low.points()
        rear={i for i,p in enumerate(before) if p.z<0}
        self.assertTrue(c.begin(self.view,self.widget,200,200,1,True))
        c.step(204,202,force=True);c.finish()
        after=c.low.points()
        self.assertTrue(all((after[i]-before[i]).length()<1e-7 for i in rear))
        self.assertTrue(any((a-b).length()>0.1 for a,b in zip(after,before)))

    def test_far_orthographic_camera_keeps_front_visible(self):
        class FarView(FakeView):
            def viewToWorld(self,x,y,origin,direction):
                super(FarView,self).viewToWorld(x,y,origin,direction)
                origin.z=1000
                return self
        self.view=FarView()
        cmds.move(0,0,1.9,self.low)
        c=self.controller()
        self.assertTrue(c.begin(self.view,self.widget,200,200,1,False))
        self.assertEqual(c.stroke['seed'],4)
        c.cancel()

    def test_weld_ignores_hidden_candidate(self):
        points=[om.MPoint(0,0,1),om.MPoint(0.01,0,1),om.MPoint(0.1,0,1)]
        result,pairs=welding.plan(points,{0:points[0]},0,self.view,10,0.5,visible=lambda i:i!=1)
        self.assertEqual(pairs,[(0,2)])

    def soft_low(self):
        self.low=plane('softLow',1,4)
        cmds.softSelect(softSelectEnabled=True,softSelectDistance=3,
            softSelectFalloff=0,softSelectCurve='1,0,1,0,1,1')
        cmds.select(clear=True)
        return Mesh(self.low)

    def test_native_soft_weights_and_selection_undo_preserved(self):
        mesh=self.soft_low()
        undo=cmds.undoInfo(q=True,undoName=True)
        weights=soft_selection.weights(mesh,12)
        self.assertAlmostEqual(weights[12],1)
        self.assertAlmostEqual(weights[13],1/3,places=4)
        self.assertNotIn(14,weights)
        self.assertEqual(cmds.ls(sl=True),[])
        self.assertEqual(cmds.undoInfo(q=True,undoName=True),undo)

    def test_soft_drag_uses_weights_and_full_stroke_undo(self):
        mesh=self.soft_low();before=mesh.points()
        c=self.controller()
        self.assertTrue(c.begin(self.view,self.widget,200,200,1,False))
        self.assertFalse(c.stroke['weld_enabled'])
        c.step(220,200,force=True);c.finish()
        after=mesh.points()
        self.assertAlmostEqual(after[12].x-before[12].x,1,places=4)
        self.assertAlmostEqual(after[13].x-before[13].x,1/3,delta=0.03)
        self.assertLess((after[14]-before[14]).length(),1e-7)
        cmds.undo()
        self.assertTrue(all((a-b).length()<1e-7 for a,b in zip(mesh.points(),before)))
        cmds.redo()
        self.assertAlmostEqual(mesh.points()[13].x,after[13].x,places=5)

    def test_soft_drag_and_relax_protect_back(self):
        self.low=cmds.polyCube(w=8,h=8,d=0.2,sx=4,sy=4,sz=1,ch=False)[0]
        cmds.softSelect(softSelectEnabled=True,softSelectDistance=5,softSelectFalloff=0)
        mesh=Mesh(self.low)
        for smooth in (False,True):
            before=mesh.points()
            rear={i for i,p in enumerate(before) if p.z<0}
            c=self.controller()
            self.assertTrue(c.begin(self.view,self.widget,200,200,1,smooth))
            self.assertFalse(rear.intersection(c.stroke['soft_weights']))
            c.step(210,205,force=True);c.finish()
            self.assertTrue(all((mesh.points()[i]-before[i]).length()<1e-7 for i in rear))
            cmds.undo()

    def test_soft_selection_respects_native_surface_and_global_modes(self):
        mesh=self.soft_low()
        cmds.softSelect(softSelectFalloff=1)
        surface=soft_selection.weights(mesh,12)
        self.assertIn(13,surface)
        self.assertNotIn(14,surface)
        cmds.softSelect(softSelectFalloff=2)
        global_weights=soft_selection.weights(mesh,12)
        self.assertEqual(global_weights[12],1)
        self.assertIn(13,global_weights)
        self.assertNotIn(14,global_weights)

    def test_topology_and_soft_selection_work_together(self):
        mesh=self.topology_low()
        cmds.move(0,0,1,self.low)
        cmds.move(0.4,0,0,self.low+'.vtx[13]',relative=True)
        cmds.softSelect(softSelectEnabled=True,softSelectDistance=3,
            softSelectFalloff=0,softSelectCurve='1,0,1,0,1,1')
        before=mesh.points()
        c=self.controller()
        self.assertTrue(c.begin(self.view,self.widget,248,200,1,False))
        sym=c.stroke['symmetry']
        self.assertGreater(len(c.stroke['soft_weights']),2)
        c.step(256,205,force=True);c.finish()
        after=mesh.points()
        self.assertGreater((after[13]-before[13]).length(),0.1)
        for a,b in sym.pairs.items():
            if a!=b:
                self.assertLess(((after[a]-before[a])*sym.matrix-(after[b]-before[b])).length(),1e-5)

    def test_local_relax_stays_near_existing_layer(self):
        mesh=Mesh(self.low)
        points=mesh.points();neighbors,border=mesh.adjacency()
        solver=LocalRelax(Targets([self.front,self.back]),points,neighbors)
        result=solver.relax(points,{4:1.0},0.22)
        self.assertAlmostEqual(result[4].z,-0.022,places=5)
        # The camera-front repair mode would instead snap to z=1.
        self.assertLess(abs(result[4].z-points[4].z),0.1)

    def test_local_relax_small_weights_do_not_snap_full_depth(self):
        cmds.move(0,0,1.2,self.low)
        mesh=Mesh(self.low);points=mesh.points();neighbors,border=mesh.adjacency()
        solver=LocalRelax(Targets([self.front]),points,neighbors)
        weak=solver.relax(points,{4:0.01},0.22)[4]
        strong=solver.relax(points,{4:1.0},0.22)[4]
        self.assertAlmostEqual((weak-points[4]).length()*100,(strong-points[4]).length(),places=5)
        self.assertGreater(weak.z,1.19)

    def test_local_connected_patch_does_not_jump_to_other_shell(self):
        combined=cmds.polyUnite(self.front,self.back,ch=False)[0]
        mesh=Mesh(combined)
        surface=Surface(mesh)
        patch=surface.patch(0,100)
        # Even near the back shell, a patch anchored to the front cannot switch.
        hit=patch.getClosestPoint(om.MPoint(0,0,-0.09))
        self.assertAlmostEqual(hit.point.z,1,places=5)

    def test_compact_patch_fallback_retains_layer_when_face_filter_is_unavailable(self):
        from qd_through import local_relax
        combined=cmds.polyUnite(self.front,self.back,ch=False)[0]
        surface=Surface(Mesh(combined))
        with mock.patch.object(local_relax,'filtered_intersector',return_value=None):
            patch=surface.patch(0,100)
        hit=patch.getClosestPoint(om.MPoint(0,0,-0.09))
        self.assertAlmostEqual(hit.point.z,1,places=5)

    def test_local_high_surface_world_transform(self):
        cmds.rotate(30,20,0,self.front)
        cmds.scale(2,0.5,1,self.front)
        cmds.move(5,2,-3,self.front)
        mesh=Mesh(self.front);surface=Surface(mesh)
        center=mesh.points()[4]
        normal=mesh.fn.getPolygonNormal(0,om.MSpace.kWorld).normal()
        hit=surface.intersector.getClosestPoint(center+normal)
        self.assertLess((om.MPoint(hit.point)-center).length(),1e-5)

    def test_local_relax_controller_undo_and_depth(self):
        cmds.move(0.8,0.5,0,self.low+'.vtx[4]',relative=True)
        mesh=Mesh(self.low);before=mesh.points()
        c=self.controller();c.smooth_mode='local'
        self.assertTrue(c.begin(self.view,self.widget,216,210,1,True))
        c.step(218,210,force=True);c.finish()
        after=mesh.points()
        self.assertGreater(after[4].z,-0.1)
        self.assertLess(after[4].z,0)
        self.assertLess(after[4].x,before[4].x)
        cmds.undo()
        self.assertTrue(all((a-b).length()<1e-6 for a,b in zip(mesh.points(),before)))
        cmds.redo()
        self.assertTrue(all((a-b).length()<1e-6 for a,b in zip(mesh.points(),after)))

    def test_local_step_backtracks_triangle_flip(self):
        points=[om.MPoint(0,0,0),om.MPoint(1,0,0),om.MPoint(0,1,0)]
        result=prevent_flips(points,{2:om.MPoint(0,-2,0)},[(0,1,2)])
        self.assertGreater(result[2].y,0.2)

    def test_runtime_commands_register_twice_and_execute(self):
        from qd_through import commands
        from maya import mel
        import qd_through
        commands.register();commands.register()
        self.assertTrue(cmds.runTimeCommand(commands.TOGGLE,exists=True))
        self.assertTrue(cmds.runTimeCommand(commands.TOGGLE,q=True,showInHotkeyEditor=True))
        self.assertFalse(cmds.runTimeCommand(commands.TOGGLE,q=True,default=True))
        with mock.patch.object(qd_through,'toggle') as toggle:
            mel.eval(commands.TOGGLE+';')
            toggle.assert_called_once()

    def test_local_high_cache_reuses_and_invalidates_geometry(self):
        targets=Targets([self.front])
        first=targets.local_surfaces()[0]
        self.assertIs(targets.local_surfaces()[0],first)
        cmds.move(0,0,0.2,self.front+'.vtx[4]',relative=True)
        changed=targets.local_surfaces()[0]
        self.assertIsNot(changed,first)
        self.assertAlmostEqual(changed.points[4].z,1.2,places=5)
        targets.close();self.assertEqual(targets._callbacks,[])

    def test_local_high_cache_invalidates_parent_transform(self):
        targets=Targets([self.front])
        first=targets.local_surfaces()[0]
        group=cmds.group(self.front)
        cmds.move(0,0,2,group)
        changed=targets.local_surfaces()[0]
        self.assertIsNot(changed,first)
        self.assertAlmostEqual(changed.points[4].z,3,places=5)
        targets.close()

    def test_local_patch_does_not_cross_connected_thickness(self):
        high=cmds.polyCube(w=8,h=8,d=0.2,sx=8,sy=8,sz=1,ch=False)[0]
        surface=Surface(Mesh(high))
        front=surface.intersector.getClosestPoint(om.MPoint(0,0,0.1))
        patch=surface.patch(front.face,100)
        hit=patch.getClosestPoint(om.MPoint(0,0,-0.1))
        self.assertAlmostEqual(hit.point.z,0.1,places=5)

    def test_local_relax_retains_curved_surface_profile(self):
        high=cmds.polySphere(r=4,sx=64,sy=32,ch=False)[0]
        low=cmds.polySphere(r=4,sx=12,sy=8,ch=False)[0]
        mesh=Mesh(low);points=mesh.points()
        seed=min(range(len(points)),key=lambda i:(points[i]-om.MPoint(2.8,0,2.8)).length())
        point=points[seed]+om.MVector(0,0.5,0)
        points[seed]=Mesh(high).fn.getClosestPoint(point,om.MSpace.kWorld)[0]
        neighbors,border=mesh.adjacency()
        targets=Targets([high]);solver=LocalRelax(targets,points,neighbors)
        original=om.MPoint(points[seed])
        for unused in range(20):
            result=solver.relax(points,{seed:1.0},0.22)
            points[seed]=result[seed]
        self.assertGreater((points[seed]-original).length(),0.01)
        self.assertGreater(om.MVector(points[seed]).length(),3.95)
        self.assertLess(om.MVector(points[seed]).length(),4.01)
        targets.close()

    def test_indexed_flip_guard_matches_full_mesh_guard(self):
        points=[om.MPoint(0,0,0),om.MPoint(1,0,0),om.MPoint(0,1,0),
                om.MPoint(4,0,0),om.MPoint(5,0,0),om.MPoint(4,1,0)]
        triangles=[(0,1,2),(3,4,5)]
        index=TriangleIndex(triangles)
        self.assertEqual(index.affected({2:om.MPoint()}),[(0,1,2)])
        updates={2:om.MPoint(0,-2,0)}
        full=prevent_flips(points,updates,triangles)
        local=prevent_flips(points,updates,index)
        self.assertEqual(set(full),set(local))
        self.assertLess((full[2]-local[2]).length(),1e-9)

    def test_projection_cache_tracks_edits_and_camera_zoom(self):
        class CameraView(FakeView):
            zoom=1.0
            def modelViewMatrix(self):return om.MMatrix()
            def projectionMatrix(self):
                return om.MMatrix([self.zoom,0,0,0,0,self.zoom,0,0,0,0,1,0,0,0,0,1])
            def worldToView(self,p):
                return int(round(200+p.x*20*self.zoom)),int(round(200+p.y*20*self.zoom)),True
            def viewToWorld(self,x,y,origin,direction):
                super(CameraView,self).viewToWorld(x,y,origin,direction)
                origin.x/=self.zoom;origin.y/=self.zoom
                return self
        view=CameraView();c=self.controller()
        self.assertTrue(c.begin(view,self.widget,200,200,1,False))
        self.assertEqual(c.stroke_screen()[5][0],280)
        view.zoom=2
        self.assertEqual(c.stroke_screen()[5][0],360)
        c.step(220,200,force=True)
        self.assertEqual(c.stroke_screen()[4][0],220)
        self.assertAlmostEqual(c.stroke['points'][4].x,0.5,places=5)
        c.cancel()

    def test_renamed_commands_keep_existing_legacy_alias(self):
        from qd_through import commands
        import qd_through
        from maya import mel
        old='QuadDrawThroughToggle'
        if not cmds.runTimeCommand(old,exists=True):
            cmds.runTimeCommand(old,commandLanguage='python',command='pass',default=False)
        commands.register()
        self.assertTrue(commands.TOGGLE.startswith('HTools_'))
        self.assertFalse(cmds.runTimeCommand(old,q=True,showInHotkeyEditor=True))
        with mock.patch.object(qd_through,'toggle') as toggle:
            mel.eval(old+';')
            mel.eval(commands.TOGGLE+';')
            self.assertEqual(toggle.call_count,2)

    def test_toggle_retains_high_cache_and_tracks_edits_while_disabled(self):
        cmds.makeLive(self.front);cmds.select(self.low)
        c=interaction.enable()
        high=c.targets;surface=high.local_surfaces()[0]
        interaction.disable()
        self.assertIs(interaction.CACHED_TARGETS,high)
        c=interaction.enable()
        self.assertIs(c.targets,high)
        self.assertIs(c.targets.local_surfaces()[0],surface)
        interaction.disable()
        cmds.move(0,0,0.2,self.front+'.vtx[4]',relative=True)
        c=interaction.enable()
        self.assertIsNot(c.targets.local_surfaces()[0],surface)
        self.assertAlmostEqual(c.targets.local_surfaces()[0].points[4].z,1.2,places=5)

    def test_cached_high_deleted_releases_snapshot_and_can_rebind(self):
        cmds.makeLive(self.front);cmds.select(self.low)
        c=interaction.enable();high=c.targets
        high.local_surfaces();interaction.disable()
        cmds.delete(self.front)
        # Deletion may remain undoable; invalid handles are never reused.
        cmds.makeLive(self.back);cmds.select(self.low)
        c=interaction.enable()
        self.assertIsNot(c.targets,high)
        self.assertEqual(c.targets.meshes[0].name,Mesh(self.back).name)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    maya.standalone.uninitialize()
    sys.exit(0 if result.wasSuccessful() else 1)
