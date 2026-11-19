# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
"""Run only in a new, dedicated Maya GUI process via launch_maya_tests.py."""
from __future__ import division, unicode_literals
import io
import json
import os
import sys
import shutil
import tempfile
import time
import zipfile
import traceback
from maya import cmds, mel
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
try:
    from PySide6 import QtCore, QtGui, QtWidgets, QtTest
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets, QtTest
    from shiboken2 import wrapInstance

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
YEAR=int(cmds.about(apiVersion=True))//10000
OUTPUT = os.environ.get('HTOOLS_TEST_OUTPUT',os.path.join(ROOT,'tests','_output'))
if not os.path.isdir(OUTPUT):os.makedirs(OUTPUT)
REPORT = os.path.join(OUTPUT, 'gui_result_%s_v10.json'%YEAR)


def qwait(milliseconds):
    loop=QtCore.QEventLoop()
    QtCore.QTimer.singleShot(milliseconds,loop.quit)
    loop.exec_()


def mouse_move(widget,point,delay=0):
    if YEAR>=2025:
        return QtTest.QTest.mouseMove(widget,point,delay)
    # Qt 5.6 QTest.mouseMove only moves the OS cursor and queues a native event.
    # Send the same mouse event directly so this dedicated, occluded test
    # window receives the move, just as it receives QTest press/release.
    if delay:time.sleep(delay/1000.0)
    event=QtGui.QMouseEvent(QtCore.QEvent.MouseMove,QtCore.QPointF(point),
        QtCore.QPointF(widget.mapToGlobal(point)),QtCore.Qt.NoButton,
        QtCore.Qt.LeftButton,QtWidgets.QApplication.keyboardModifiers())
    QtWidgets.QApplication.sendEvent(widget,event)


def schedule():
    QtCore.QTimer.singleShot(5000, run)


def run():
    result = {'ok': False, 'checks': [], 'ui_language':cmds.about(uiLanguage=True),
              'requested_language':os.environ.get('MAYA_UI_LANGUAGE','')}
    try:
        from qd_through import interaction, ui
        from qd_through.geometry import Mesh
        cmds.file(new=True, force=True)
        high = cmds.polyPlane(name='qdt_test_high', axis=(0,0,1), width=8, height=8,
            subdivisionsX=20, subdivisionsY=20, constructionHistory=False)[0]
        cmds.move(0,0,1, high)
        back = cmds.polyPlane(name='qdt_test_inner', axis=(0,0,1), width=8, height=8,
            subdivisionsX=10, subdivisionsY=10, constructionHistory=False)[0]
        cmds.move(0,0,-0.1, back)
        high = cmds.polyUnite(high, back, ch=False, name='qdt_test_multilayer')[0]
        low = cmds.polyPlane(name='qdt_test_low', axis=(0,0,1), width=6, height=6,
            subdivisionsX=4, subdivisionsY=4, constructionHistory=False)[0]
        cmds.move(0.3,0.25,0,low+'.vtx[12]', relative=True)
        cmds.makeLive(high)
        cmds.select(low, replace=True)
        cmds.symmetricModelling(symmetry=False)
        cmds.softSelect(softSelectEnabled=False)
        mel.eval('nexOpt -e useAutoWeld 0; nexOpt -e relaxAffects 3;')
        panel = 'modelPanel4'
        cmds.modelPanel(panel, edit=True, camera='front')
        cmds.setAttr('frontShape.orthographicWidth', 12)
        cmds.setFocus(panel)
        window = ui.show()
        window.relax_mode.setCurrentIndex(1)
        mel.eval('dR_quadDrawTool;')
        window.switch.setChecked(True)
        window.move(30,30)
        cmds.setFocus(panel)
        cmds.refresh(force=True)
        QtWidgets.QApplication.processEvents()
        controller = interaction.ACTIVE
        assert controller is not None, window.status.text()
        assert interaction.quad_active(), cmds.currentCtx()
        result['context'] = cmds.currentCtx()
        result['checks'].append('Single toggle detects native Quad Draw build mesh and Live target')
        view = omui.M3dView.getM3dViewFromModelPanel(panel)
        widget = wrapInstance(int(view.widget()), QtWidgets.QWidget)
        result['viewport'] = [view.portWidth(), view.portHeight(), widget.width(), widget.height()]
        target = controller.viewport(widget)
        assert target is not None
        mesh = Mesh(low)
        def local(point):
            x,y,visible = view.worldToView(point)
            assert visible
            return QtCore.QPoint(int(round(x*widget.width()/view.portWidth())),
                int(round((view.portHeight()-1-y)*widget.height()/view.portHeight())))
        point = local(mesh.points()[12])
        result['debug_before_press'] = dict(local=[point.x(),point.y()],
            projected=list(view.worldToView(mesh.points()[12])),
            selected=cmds.ls(sl=True,long=True),
            correct_selection=controller.correct_selection(),
            low=controller.low.name, widget_class=widget.metaObject().className())
        original_filter = interaction.Controller.eventFilter
        def traced(self, watched, event):
            answer = original_filter(self,watched,event)
            if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                result.setdefault('press_events', []).append(dict(
                    watched=watched.metaObject().className(), result=answer,
                    context=cmds.currentCtx(), status=window.status.text(),
                    coords=list(self.coordinates(event,view,widget))))
            return answer
        interaction.Controller.eventFilter = traced
        original = mesh.points(False)
        QtTest.QTest.mousePress(widget, QtCore.Qt.MouseButton.LeftButton,
                              QtCore.Qt.KeyboardModifier.NoModifier, point)
        assert controller.stroke is not None, 'Press was not intercepted'
        end = point + QtCore.QPoint(30,10)
        mouse_move(widget, end, 30)
        from qd_through.interaction import view_ray
        origin,direction=view_ray(view,end.x(),view.portHeight()-1-end.y())
        hit=controller.targets.hit(origin,direction)
        result['first_move']=dict(stroke=controller.stroke is not None,
            changed=controller.stroke['changed'] if controller.stroke else None,
            seed=controller.stroke['seed'] if controller.stroke else None,
            point=list(mesh.points()[12]),origin=list(origin),direction=list(direction),
            hit=list(hit[0]) if hit else None,status=window.status.text())
        assert controller.cursor_active
        assert QtWidgets.QApplication.overrideCursor() is not None
        assert not any(type(w).__module__=='qd_through.interaction' for w in widget.findChildren(QtWidgets.QWidget))
        QtTest.QTest.mouseRelease(widget, QtCore.Qt.MouseButton.LeftButton,
                                QtCore.Qt.KeyboardModifier.NoModifier,end)
        QtWidgets.QApplication.processEvents()
        assert controller.stroke is None
        assert not controller.cursor_active
        assert QtWidgets.QApplication.overrideCursor() is None
        result['checks'].append('Stroke uses a cursor without a viewport overlay and restores it on release')
        assert abs(mesh.points()[12].z-1) < 1e-4, str(mesh.points()[12])
        assert mesh.fn.numVertices == 25
        result['checks'].append('Occluded vertex drag intercepted; no new vertices')
        cmds.undo()
        assert (mesh.points(False)[12]-original[12]).length() < 1e-6
        cmds.redo()
        assert abs(mesh.points()[12].z-1) < 1e-4
        result['checks'].append('GUI undo/redo restores full stroke')
        # Repeat Shift on a still-occluded adjacent vertex.
        before = mesh.points(False)
        point = local(mesh.points()[13])
        QtTest.QTest.mousePress(widget, QtCore.Qt.MouseButton.LeftButton,
                              QtCore.Qt.KeyboardModifier.ShiftModifier, point)
        assert controller.stroke and controller.stroke['smooth']
        end = point + QtCore.QPoint(5,2)
        mouse_move(widget,end,30)
        QtTest.QTest.mouseRelease(widget, QtCore.Qt.MouseButton.LeftButton,
                                QtCore.Qt.KeyboardModifier.ShiftModifier,end)
        assert abs(mesh.points()[13].z-1) < 1e-4, str(mesh.points()[13])
        assert mesh.fn.numVertices == 25
        result['checks'].append('Shift relax moves occluded low vertices onto front surface')
        # Native creation path: a click away from existing low vertices is not consumed.
        point = local(om.MPoint(3.7,1,1))
        QtTest.QTest.mousePress(widget, QtCore.Qt.MouseButton.LeftButton,
                              QtCore.Qt.KeyboardModifier.NoModifier, point)
        assert controller.stroke is None
        QtTest.QTest.mouseRelease(widget, QtCore.Qt.MouseButton.LeftButton,
                                QtCore.Qt.KeyboardModifier.NoModifier,point)
        result['checks'].append('Empty-space click passed to native Quad Draw')
        # Switch to a new symmetric mesh without touching the plugin toggle.
        cmds.setToolTo('selectSuperContext')
        low2=cmds.polyPlane(n='qdt_second_low',axis=(0,0,1),w=6,h=6,sx=4,sy=4,ch=False)[0]
        cmds.move(0,0,1,low2)
        cmds.select(low2)
        cmds.symmetricModelling(symmetry=True,about='world',axis='x',tolerance=0.01)
        mel.eval('dR_quadDrawTool;')
        cmds.setFocus(panel);cmds.refresh(force=True)
        mesh2=Mesh(low2)
        def drag(index,end,shift=False):
            start=local(mesh2.points()[index])
            mods=QtCore.Qt.KeyboardModifier.ShiftModifier if shift else QtCore.Qt.KeyboardModifier.NoModifier
            QtTest.QTest.mousePress(widget,QtCore.Qt.MouseButton.LeftButton,mods,start)
            assert controller.stroke is not None,window.status.text()
            if shift:
                stroke=controller.stroke
                if stroke['seed'] in stroke['border']:
                    assert stroke['relax_allowed'].issubset(stroke['border'])
                else:
                    assert not stroke['relax_allowed'].intersection(stroke['border'])
            mouse_move(widget,end,30)
            preview=mesh2.points()
            result.setdefault('stroke_previews',[]).append(dict(
                seed=controller.stroke['seed'],weld=controller.stroke['weld_pairs'],
                enabled=controller.stroke['weld_enabled'],
                points=[list(p) for p in mesh2.points()],
                symmetry=controller.stroke['symmetry'].pairs if controller.stroke['symmetry'] else {}))
            QtTest.QTest.mouseRelease(widget,QtCore.Qt.MouseButton.LeftButton,mods,end)
            if shift:
                assert all((a-b).length()<1e-8 for a,b in zip(mesh2.points(),preview)), 'Release added a relax step'
        end=local(om.MPoint(1.7,0.1,1))
        drag(13,end)
        assert controller.low.name==mesh2.name
        a,b=mesh2.points()[11],mesh2.points()[13]
        assert abs(a.x+b.x)<1e-5 and abs(a.y-b.y)<1e-5
        assert b.x>1.6
        result['checks'].append('Auto-switch low mesh; native World X symmetry drag')
        start=local(mesh2.points()[13])
        drag(13,start+QtCore.QPoint(5,2),shift=True)
        a,b=mesh2.points()[11],mesh2.points()[13]
        assert abs(a.x+b.x)<1e-5 and abs(a.y-b.y)<1e-5
        result['checks'].append('Native symmetry setting also mirrors Shift relax')
        result['checks'].append('Auxiliary Shift reads the actual native Auto-Lock setting and locks the opposite vertex group')
        cmds.symmetricModelling(about='object',axis='x',symmetry=True)
        cmds.select(clear=True)
        assert Mesh(mel.eval('nexCtx -q -appendMesh')).name==mesh2.name
        before=mesh2.points()
        drag(13,local(before[13])+QtCore.QPoint(8,3))
        after=mesh2.points()
        assert abs(after[13].x+after[11].x)<1e-5
        assert (after[13]-before[13]).length()>0.01
        assert not cmds.ls(sl=True)
        start=local(after[13])
        drag(13,start+QtCore.QPoint(2,2),shift=True)
        assert not cmds.ls(sl=True)
        result['checks'].append('Empty active selection: Object X drag and Shift relax retain Quad Draw build mesh')
        mel.eval('nexOpt -e useAutoWeld 1; nexOpt -e autoWeldTolerance 14;')
        target=local(mesh2.points()[18])+QtCore.QPoint(0,4)
        drag(13,target)
        assert mesh2.fn.numVertices==23,mesh2.fn.numVertices
        cmds.undo();assert mesh2.fn.numVertices==25
        cmds.redo();assert mesh2.fn.numVertices==23
        result['checks'].append('Native Auto-weld settings merge both sides; topology undo/redo')
        # Changing Make Live also updates the next auxiliary stroke.
        cmds.setToolTo('selectSuperContext')
        new_high=cmds.polyPlane(n='qdt_new_high',axis=(0,0,1),w=10,h=10,ch=False)[0]
        cmds.move(0,0,2,new_high);cmds.makeLive(new_high);cmds.select(low2)
        mel.eval('dR_quadDrawTool;')
        mel.eval('nexOpt -e useAutoWeld 0;')
        cmds.refresh(force=True)
        start=local(mesh2.points()[0])
        drag(0,start+QtCore.QPoint(5,-5))
        assert controller.targets.meshes[0].name==Mesh(new_high).name
        assert abs(mesh2.points()[0].z-2)<1e-5
        result['checks'].append('Make Live target changes are followed automatically')
        # Native topology pairing on an asymmetrically posed low mesh.
        cmds.setToolTo('selectSuperContext')
        low3=cmds.polyPlane(n='qdt_topo_low',axis=(0,0,1),w=6,h=6,sx=4,sy=4,ch=False)[0]
        mesh2=Mesh(low3)
        edges=om.MItMeshEdge(mesh2.path)
        pts=mesh2.points()
        while not edges.isDone():
            if all(abs(pts[edges.vertexId(k)].x)<1e-7 for k in (0,1)):
                break
            edges.next()
        cmds.select(low3+'.e[%d]'%edges.index())
        cmds.symmetricModelling(about='topo',topoSymmetry=True,symmetry=True)
        cmds.move(0.4,0.2,0.1,low3+'.vtx[13]',relative=True)
        cmds.select(low3)
        mel.eval('dR_quadDrawTool;')
        cmds.setFocus(panel);cmds.refresh(force=True)
        before=mesh2.points()
        cmds.select(clear=True)
        drag(13,local(before[13])+QtCore.QPoint(20,5))
        after=mesh2.points()
        assert abs((after[13].x-before[13].x)+(after[11].x-before[11].x))<1e-5
        assert abs(after[13].x+after[11].x-0.4)<1e-5
        assert abs(after[13].z-2)<1e-5
        assert mesh2.fn.numVertices==25
        assert controller.low.name==mesh2.name
        assert Mesh(mel.eval('nexCtx -q -appendMesh')).name==mesh2.name
        assert not cmds.ls(sl=True)
        result['checks'].append('Topology symmetry drag retains asymmetric shape and native Quad Draw build mesh')
        before=mesh2.points()
        drag(13,local(before[13])+QtCore.QPoint(3,2),shift=True)
        after=mesh2.points()
        assert abs((after[13].x-before[13].x)+(after[11].x-before[11].x))<1e-5
        assert (after[13]-before[13]).length()>0.001
        result['checks'].append('Topology symmetry Shift relax mirrors displacement')
        mel.eval('nexOpt -e useAutoWeld 1;')
        # Bring the next target pair to the reference depth for the weld.
        for index in (16,18):
            p=mesh2.points()[index]
            cmds.xform(low3+'.vtx[%d]'%index,worldSpace=True,translation=(p.x,p.y,2))
        drag(13,local(mesh2.points()[18])+QtCore.QPoint(0,3))
        assert mesh2.fn.numVertices==23,mesh2.fn.numVertices
        cmds.undo();assert mesh2.fn.numVertices==25
        cmds.redo();assert mesh2.fn.numVertices==23
        result['checks'].append('Topology symmetry weld merges both pairs with one undo/redo')
        cmds.setToolTo('selectSuperContext')
        cmds.symmetricModelling(symmetry=False)
        low4=cmds.polyCube(n='qdt_thin_soft',w=6,h=6,d=0.2,sx=4,sy=4,sz=1,ch=False)[0]
        cmds.move(0,0,1.8,low4)
        mesh2=Mesh(low4)
        seed=min(range(mesh2.fn.numVertices),key=lambda i:
            abs(mesh2.points()[i].x)+abs(mesh2.points()[i].y)+abs(mesh2.points()[i].z-1.9)*20)
        cmds.move(0.04,0,0,low4+'.vtx[%d]'%seed,relative=True)
        cmds.select(low4);mel.eval('dR_quadDrawTool;')
        cmds.setFocus(panel);cmds.refresh(force=True)
        before=mesh2.points();rear={i for i,p in enumerate(before) if p.z<1.8}
        drag(seed,local(before[seed])+QtCore.QPoint(10,3))
        assert all((mesh2.points()[i]-before[i]).length()<1e-6 for i in rear)
        assert (mesh2.points()[seed]-before[seed]).length()>0.05
        result['checks'].append('Thin shell rear vertices do not get dragged through the front')
        cmds.softSelect(softSelectEnabled=True,softSelectDistance=4,
            softSelectFalloff=0,softSelectCurve='1,0,1,0,1,1')
        before=mesh2.points()
        drag(seed,local(before[seed])+QtCore.QPoint(18,4))
        after=mesh2.points()
        assert all((after[i]-before[i]).length()<1e-6 for i in rear)
        assert sum((a-b).length()>0.005 for a,b in zip(after,before))>2
        cmds.undo()
        assert all((a-b).length()<1e-5 for a,b in zip(mesh2.points(),before))
        cmds.redo()
        assert all((a-b).length()<1e-5 for a,b in zip(mesh2.points(),after))
        result['checks'].append('Native soft selection moves multiple front vertices, protects back and supports undo/redo')
        before=mesh2.points()
        drag(seed,local(before[seed])+QtCore.QPoint(3,2),shift=True)
        assert all((mesh2.points()[i]-before[i]).length()<1e-6 for i in rear)
        assert any((a-b).length()>0.005 for a,b in zip(mesh2.points(),before))
        result['checks'].append('Shift soft relax also protects thin-shell back vertices')
        cmds.softSelect(softSelectEnabled=False)
        # Default local relax preserves depth instead of snapping to front high.
        window.relax_mode.setCurrentIndex(0)
        p=mesh2.points()[seed]
        cmds.xform(low4+'.vtx[%d]'%seed,worldSpace=True,translation=(p.x+0.1,p.y,1.8))
        before=mesh2.points()
        drag(seed,local(before[seed])+QtCore.QPoint(3,2),shift=True)
        after=mesh2.points()
        assert 1.8<after[seed].z<1.99,after[seed].z
        assert all((after[i]-before[i]).length()<1e-6 for i in rear)
        cmds.undo()
        assert all((a-b).length()<1e-5 for a,b in zip(mesh2.points(),before))
        cmds.redo()
        result['checks'].append('Default local Shift relax changes depth gradually and supports whole-stroke undo')
        result['checks'].append('Shift mouse release commits the displayed preview without an extra relax iteration')
        window.relax_enabled.setChecked(False)
        assert interaction.ACTIVE is controller and not controller.relax_enabled
        assert not window.radius.isEnabled() and not window.strength.isEnabled()
        assert window.pick.isEnabled() and window.offset.isEnabled()
        point=local(mesh2.points()[seed])
        QtTest.QTest.mousePress(widget,QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.ShiftModifier,point)
        assert controller.stroke is None
        mouse_move(widget,point+QtCore.QPoint(4,2),30)
        QtTest.QTest.mouseRelease(widget,QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.ShiftModifier,point+QtCore.QPoint(4,2))
        assert not result['press_events'][-1]['result']
        point=local(mesh2.points()[seed])
        drag(seed,point+QtCore.QPoint(6,2))
        assert controller.stroke is None
        result['checks'].append('Independent relax checkbox passes Shift to native Quad Draw while auxiliary dragging remains enabled')
        window.relax_enabled.setChecked(True)
        assert controller.relax_enabled and window.radius.isEnabled()
        before=mesh2.points()
        point=local(before[seed])
        QtTest.QTest.mousePress(widget,QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.ShiftModifier,point)
        assert controller.stroke and controller.stroke['smooth']
        mouse_move(widget,point+QtCore.QPoint(4,2),30)
        window.relax_enabled.setChecked(False)
        assert controller.stroke is None and not controller.cursor_active
        assert all((a-b).length()<1e-6 for a,b in zip(mesh2.points(),before))
        QtTest.QTest.mouseRelease(widget,QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.ShiftModifier,point+QtCore.QPoint(4,2))
        window.relax_enabled.setChecked(True)
        result['checks'].append('Disabling auxiliary relax during a stroke cancels preview and safely consumes its release')
        # The tool switch must inherit the native build mesh even with an empty
        # normal selection. It must also leave no helper stroke in Multi-Cut.
        cmds.select(clear=True)
        controller.remember_quad_mesh()
        mel.eval('dR_multiCutTool;')
        QtWidgets.QApplication.processEvents()
        import maya.utils
        maya.utils.processIdleEvents()
        assert 'multicut' in cmds.currentCtx().lower()
        assert cmds.ls(sl=True), 'Multi-Cut lost the build selection'
        assert Mesh(cmds.ls(sl=True)[0]).name==mesh2.name
        assert Mesh(mel.eval('nexCtx -q -appendMesh')).name==mesh2.name
        assert controller.stroke is None
        result['checks'].append('Quad Draw to native Multi-Cut restores the current low mesh when active selection is empty')
        mel.eval('dR_quadDrawTool;')
        QtWidgets.QApplication.processEvents()
        window.close()
        assert interaction.ACTIVE is controller
        result['checks'].append('Closing settings preserves the enabled toggle')
        import qd_through
        warmed_targets=controller.targets
        warmed_surfaces=warmed_targets.local_surfaces()
        qd_through.toggle()
        assert interaction.ACTIVE is None
        qd_through.toggle()
        assert interaction.ACTIVE is not None
        assert interaction.ACTIVE.targets is warmed_targets
        assert interaction.ACTIVE.targets.local_surfaces() is warmed_surfaces
        result['checks'].append('Toggling off/on preserves the warmed high-mesh cache')
        qd_through.disable()
        result['checks'].append('Public one-click toggle enables/disables filtering')
        # Exercise Maya's real Python-drop loader with a stale generic install module.
        import types
        from maya.app.general.executeDroppedPythonFile import executeDroppedPythonFile
        # Ensure an older shelf entry is migrated, not duplicated.
        parent_shelf=cmds.tabLayout(mel.eval('$tmp=$gShelfTopLevel'),q=True,selectTab=True)
        owned=[b for b in cmds.shelfLayout(parent_shelf,q=True,childArray=True) or []
               if cmds.objectTypeUI(b)=='shelfButton' and
               cmds.shelfButton(b,q=True,annotation=True).startswith(('Quad Draw Through','HTools_QuadDrawThrough'))]
        if not owned:
            owned=[cmds.shelfButton(parent=parent_shelf,label='Old QD',annotation='Quad Draw Through 0.5')]
        else:
            cmds.shelfButton(owned[0],e=True,annotation='Quad Draw Through 0.5')
        old_button=owned[0]
        if not cmds.runTimeCommand('QuadDrawThroughToggle',exists=True):
            cmds.runTimeCommand('QuadDrawThroughToggle',commandLanguage='python',command='pass',default=False)
        stale=sys.modules.get('install')
        sys.modules['install']=types.ModuleType(str('install'))
        original_dialog=cmds.confirmDialog
        dialogs=[]
        portable=tempfile.mkdtemp(prefix='portable_%s_'%YEAR,dir=OUTPUT)
        source=os.path.join(portable,'安装 包')
        release=os.environ.get('HTOOLS_TEST_PACKAGE')
        if release:
            with zipfile.ZipFile(release) as archive:
                assert all(n.startswith('HTools_QuadDrawThrough/') and '..' not in n.split('/')
                           for n in archive.namelist())
                archive.extractall(portable)
            extracted=os.path.join(portable,'HTools_QuadDrawThrough')
            assert os.path.dirname(os.path.realpath(extracted))==os.path.realpath(portable)
            assert os.path.dirname(os.path.realpath(source))==os.path.realpath(portable)
            os.rename(extracted,source)
        else:
            os.makedirs(source)
            shutil.copytree(os.path.join(ROOT,'qd_through'),os.path.join(source,'qd_through'))
            for name in ('install.py','package_manifest.json','HTools_QuadDrawThrough_Install_v10.py','LICENSE'):
                shutil.copy2(os.path.join(ROOT,name),os.path.join(source,name))
        def capture_dialog(**kwargs):
            dialogs.append(kwargs)
            return '确定'
        cmds.confirmDialog=capture_dialog
        try:
            loaded=executeDroppedPythonFile(os.path.join(source,'HTools_QuadDrawThrough_Install_v10.py'),'')
        finally:
            cmds.confirmDialog=original_dialog
            if stale is None:
                sys.modules.pop('install',None)
            else:
                sys.modules['install']=stale
        assert loaded is True,(loaded,dialogs)
        assert dialogs and '安装成功' in dialogs[-1]['title'],dialogs
        import qd_through as updated
        assert updated.__version__=='1.0.0'
        installed=os.path.join(cmds.internalVar(userScriptDir=True),'HTools_QuadDrawThrough')
        assert os.path.realpath(updated.__file__).startswith(os.path.realpath(installed)+os.sep)
        result['installed']=installed
        assert updated.ui.WINDOW.windowTitle().startswith('HTools_')
        QtWidgets.QApplication.processEvents()
        updated.ui.WINDOW.grab().save(os.path.join(OUTPUT,'settings_%s_v10.png'%YEAR))
        assert cmds.shelfButton(old_button,q=True,label=True)=='HTools_QuadDrawThrough'
        buttons=[b for b in cmds.lsUI(type='shelfButton') or [] if cmds.shelfButton(b,q=True,annotation=True).startswith('HTools_QuadDrawThrough 1.0')]
        assert buttons
        ptr=omui.MQtUtil.findControl(buttons[-1]) if hasattr(omui,'MQtUtil') else None
        if ptr is None:
            import maya.OpenMayaUI as legacy_ui
            ptr=legacy_ui.MQtUtil.findControl(buttons[-1])
        button_widget=wrapInstance(int(ptr),QtWidgets.QWidget)
        result['shelf_debug']=dict(buttons=buttons,widget_class=button_widget.metaObject().className(),
            visible=button_widget.isVisible(),enabled=button_widget.isEnabled(),
            size=[button_widget.width(),button_widget.height()])
        original_click=updated.toggle
        def traced_click():
            result['shelf_debug']['click_called']=True
            return original_click()
        updated.toggle=traced_click
        QtTest.QTest.mouseClick(button_widget,QtCore.Qt.MouseButton.LeftButton)
        qwait(QtWidgets.QApplication.doubleClickInterval()+100)
        from qd_through import interaction as new_interaction
        assert new_interaction.ACTIVE is not None,result['shelf_debug']
        updated.ui.WINDOW.close()
        active=new_interaction.ACTIVE
        QtTest.QTest.mouseClick(button_widget,QtCore.Qt.MouseButton.LeftButton)
        QtTest.QTest.mouseDClick(button_widget,QtCore.Qt.MouseButton.LeftButton)
        QtTest.QTest.mouseRelease(button_widget,QtCore.Qt.MouseButton.LeftButton)
        qwait(QtWidgets.QApplication.doubleClickInterval()+100)
        assert updated.ui.WINDOW.isVisible()
        assert new_interaction.ACTIVE is active
        result['checks'].append('Real shelf single click toggles; double click opens settings without changing enabled state')
        updated.disable()
        assert cmds.runTimeCommand('HTools_QuadDrawThroughToggle',exists=True)
        assert cmds.runTimeCommand('HTools_QuadDrawThroughToggle',q=True,showInHotkeyEditor=True)
        mel.eval('HTools_QuadDrawThroughToggle;')
        assert new_interaction.ACTIVE is not None
        mel.eval('HTools_QuadDrawThroughToggle;')
        assert new_interaction.ACTIVE is None
        updated.ui.WINDOW.close()
        mel.eval('HTools_QuadDrawThroughSettings;')
        assert updated.ui.WINDOW.isVisible()
        result['checks'].append('Unbound runtime commands appear in Hotkey Editor and toggle/open settings correctly')
        assert not cmds.runTimeCommand('QuadDrawThroughToggle',q=True,showInHotkeyEditor=True)
        mel.eval('QuadDrawThroughToggle;')
        assert new_interaction.ACTIVE is not None
        mel.eval('QuadDrawThroughToggle;')
        assert new_interaction.ACTIVE is None
        result['checks'].append('HTools naming migrates old shelf button; previously bound legacy command still toggles')
        result['checks'].append('Actual Maya drop loader bypasses stale install module and reports success; shelf toggle works')
        result['checks'].append('Installer copies the package from a Unicode/space path into this Maya user script directory')
        # Preserve user-added files in the previous installation on upgrade.
        note=os.path.join(installed,'keep_user_note.txt')
        with io.open(note,'w',encoding='utf-8') as stream:stream.write('test note')
        cmds.confirmDialog=capture_dialog
        try:
            assert executeDroppedPythonFile(os.path.join(source,'HTools_QuadDrawThrough_Install_v10.py'),'')
        finally:
            cmds.confirmDialog=original_dialog
        import qd_through as reinstalled
        script_dir=os.path.dirname(os.path.normpath(installed))
        assert any(os.path.isfile(os.path.join(script_dir,name,'keep_user_note.txt'))
            for name in os.listdir(script_dir) if name.startswith('.HTools_QuadDrawThrough-backup-'))
        result['checks'].append('Reinstall preserves the previous installation and user-added files in a backup')
        reinstalled.disable()
        reinstalled.interaction.clear_cache()
        reinstalled.ui.WINDOW.close()
        reinstalled.ui.WINDOW.deleteLater()
        moved=source+' moved'
        assert os.path.dirname(os.path.realpath(source))==os.path.realpath(portable)
        assert os.path.dirname(os.path.realpath(moved))==os.path.realpath(portable)
        os.rename(source,moved)
        for name in list(sys.modules):
            if name=='qd_through' or name.startswith('qd_through.'):
                sys.modules.pop(name,None)
        for folder in (ROOT,source,moved,installed):
            while folder in sys.path:sys.path.remove(folder)
        command=cmds.shelfButton(old_button,q=True,command=True)
        assert ROOT not in command and source not in command and 'userScriptDir' in command
        eval(compile(command,'<portable shelf>','exec'),{})
        import qd_through as portable_module
        assert portable_module.interaction.ACTIVE is not None
        assert os.path.realpath(portable_module.__file__).startswith(os.path.realpath(installed)+os.sep)
        portable_module.disable()
        result['checks'].append('After moving the unpacked source and clearing Python modules/paths, shelf command imports the installed copy')
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    finally:
        with io.open(REPORT, 'w', encoding='utf-8') as stream:
            stream.write(json.dumps(result, ensure_ascii=False, indent=2))
        cmds.quit(force=True)
