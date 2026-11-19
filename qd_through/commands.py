# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
"""Register user-bindable Maya commands; never assign a keyboard shortcut."""
from __future__ import division, unicode_literals
import os
from maya import cmds

TOGGLE='HTools_QuadDrawThroughToggle'
SETTINGS='HTools_QuadDrawThroughSettings'


def command_prefix(root=None):
    if root is None:
        location=('import os\nfrom maya import cmds\n'
            "p = os.path.join(cmds.internalVar(userScriptDir=True), 'HTools_QuadDrawThrough')\n")
    else:
        location='p = %r\n'%root
    return ('import sys\n'+location+
            'if p not in sys.path: sys.path.insert(0, p)\nimport qd_through\n')


def register(root=None):
    prefix=command_prefix(root)
    for name,call,description in (
            (TOGGLE,'toggle','HTools_QuadDrawThrough 开关'),
            (SETTINGS,'show','HTools_QuadDrawThrough 设置')):
        options=dict(annotation=description,category='HTools',
            commandLanguage='python',command=prefix+'qd_through.'+call+'()',
            showInHotkeyEditor=True)
        if cmds.runTimeCommand(name,exists=True):
            cmds.runTimeCommand(name,edit=True,**options)
        else:
            cmds.runTimeCommand(name,default=False,**options)
        cmds.nameCommand(name+'NameCommand',annotation=description,sourceType='mel',command=name)
    # Keep existing key bindings to previous names working, without duplicate
    # entries in the Hotkey Editor or changing any keyboard assignment.
    for old,call in (('QuadDrawThroughToggle','toggle'),('QuadDrawThroughSettings','show')):
        if cmds.runTimeCommand(old,exists=True):
            cmds.runTimeCommand(old,edit=True,category='HTools',
                annotation='HTools_QuadDrawThrough (legacy alias)',
                commandLanguage='python',command=prefix+'qd_through.'+call+'()',
                showInHotkeyEditor=False)
    cmds.runTimeCommand(TOGGLE,edit=True,save=True)
