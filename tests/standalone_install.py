# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
from __future__ import division, unicode_literals
import io
import json
import os
import shutil
import tempfile
import traceback
from maya import cmds, mel
import maya.api.OpenMayaUI as omui
try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YEAR=int(cmds.about(apiVersion=True))//10000
OUTPUT=os.environ.get('HTOOLS_TEST_OUTPUT',os.path.join(ROOT,'tests','_output'))
if not os.path.isdir(OUTPUT):os.makedirs(OUTPUT)


def schedule():QtCore.QTimer.singleShot(5000,run)


def run():
    result={'ok':False,'dialogs':[],'drop':[], 'ui_language':cmds.about(uiLanguage=True),
            'requested_language':os.environ.get('MAYA_UI_LANGUAGE','')}
    original=cmds.confirmDialog
    cmds.confirmDialog=lambda **kwargs:result['dialogs'].append(kwargs) or 'OK'
    try:
        folder=tempfile.mkdtemp(prefix='standalone_drop_%s_'%YEAR,dir=OUTPUT)
        source=os.path.join(folder,'中文 安装包')
        os.makedirs(source)
        installer='HTools_QuadDrawThrough_v1.0_Install.mel'
        shutil.copy2(os.path.join(ROOT,installer),os.path.join(source,installer))
        assert os.listdir(source)==[installer]
        view=omui.M3dView.getM3dViewFromModelPanel('modelPanel4')
        widget=wrapInstance(int(view.widget()),QtWidgets.QWidget)
        cmds.setFocus('modelPanel4');cmds.refresh(force=True)
        QtWidgets.QApplication.processEvents()
        result['widget']=widget.metaObject().className()
        result['acceptsDrops']=widget.acceptDrops()
        point=QtCore.QPoint(widget.width()//2,widget.height()//2)
        for extension in ('mel',):
            path=os.path.join(source,installer)
            mime=QtCore.QMimeData()
            mime.setUrls([QtCore.QUrl.fromLocalFile(path)])
            enter=QtGui.QDragEnterEvent(point,QtCore.Qt.CopyAction,mime,QtCore.Qt.LeftButton,QtCore.Qt.NoModifier)
            drop=QtGui.QDropEvent(QtCore.QPointF(point),QtCore.Qt.CopyAction,mime,QtCore.Qt.LeftButton,QtCore.Qt.NoModifier)
            before=len(result['dialogs'])
            QtWidgets.QApplication.sendEvent(widget,enter)
            QtWidgets.QApplication.sendEvent(widget,drop)
            QtWidgets.QApplication.processEvents()
            result['drop'].append(dict(extension=extension,enter=enter.isAccepted(),drop=drop.isAccepted(),dialogs=len(result['dialogs'])-before))
        assert result['dialogs'] and '安装成功' in result['dialogs'][-1]['title'],result
        # Execute the text as Script Editor does, without any source filename.
        path=os.path.join(source,installer)
        with io.open(path,'r',encoding='ascii') as stream:mel.eval(stream.read())
        import qd_through
        assert qd_through.__version__=='1.0.0'
        assert qd_through.ui.WINDOW.isVisible()
        assert result['dialogs'] and '安装成功' in result['dialogs'][-1]['title'],result['dialogs']
        qd_through.toggle()
        assert qd_through.interaction.ACTIVE is not None
        qd_through.disable()
        assert len(result['dialogs'])==2
        result['installed']=os.path.dirname(os.path.dirname(qd_through.__file__))
        with open(os.path.join(ROOT,'LICENSE'),'rb') as expected:
            with open(os.path.join(result['installed'],'LICENSE'),'rb') as installed:
                assert installed.read()==expected.read()
        result['ok']=True
    except Exception:result['error']=traceback.format_exc()
    finally:
        cmds.confirmDialog=original
        with io.open(os.path.join(OUTPUT,'standalone_drop_%s_result.json'%YEAR),'w',encoding='utf-8') as stream:
            stream.write(json.dumps(result,ensure_ascii=False,indent=2))
        cmds.quit(force=True)
