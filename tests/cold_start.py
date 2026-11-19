# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
from __future__ import division, unicode_literals
import io
import json
import os
import sys
import traceback
from maya import cmds,mel
try:
    from PySide6 import QtCore
except ImportError:
    from PySide2 import QtCore


def schedule():QtCore.QTimer.singleShot(5000,run)


def run():
    result={'ok':False,'ui_language':cmds.about(uiLanguage=True),
            'requested_language':os.environ.get('MAYA_UI_LANGUAGE','')}
    try:
        assert 'qd_through' not in sys.modules
        assert cmds.runTimeCommand('HTools_QuadDrawThroughToggle',exists=True)
        mel.eval('HTools_QuadDrawThroughToggle;')
        import qd_through
        installed=os.path.join(cmds.internalVar(userScriptDir=True),'HTools_QuadDrawThrough')
        assert os.path.realpath(qd_through.__file__).startswith(os.path.realpath(installed)+os.sep)
        assert qd_through.__version__=='1.0.0'
        assert qd_through.interaction.ACTIVE is not None
        mel.eval('HTools_QuadDrawThroughSettings;')
        assert qd_through.ui.WINDOW.isVisible()
        qd_through.disable()
        result.update(ok=True,installed=installed)
    except Exception:result['error']=traceback.format_exc()
    finally:
        year=int(cmds.about(apiVersion=True))//10000
        output=os.environ.get('HTOOLS_TEST_OUTPUT',os.path.join(os.path.dirname(__file__),'_output'))
        if not os.path.isdir(output):os.makedirs(output)
        report=os.path.join(output,'cold_start_%s_v10.json'%year)
        with io.open(report,'w',encoding='utf-8') as stream:
            stream.write(json.dumps(result,ensure_ascii=False,indent=2))
        cmds.quit(force=True)
