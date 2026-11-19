# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
"""Read Maya's actual soft-selection weights without changing user settings."""
from __future__ import division, unicode_literals
import json
from maya import cmds
import maya.OpenMaya as om


def weights(mesh,seed):
    if not cmds.softSelect(query=True,softSelectEnabled=True):return None
    saved=om.MSelectionList()
    om.MGlobal.getActiveSelectionList(saved)
    old_rich=om.MRichSelection()
    has_rich=True
    try:
        om.MGlobal.getRichSelection(old_rich)
    except RuntimeError:
        if saved.length():raise
        has_rich=False
    try:
        name=mesh.name+'.vtx[%d]'%seed
        om.MGlobal.executeCommand('select -r '+json.dumps(name,ensure_ascii=False)+';',False,False)
        rich=om.MRichSelection()
        om.MGlobal.getRichSelection(rich)
        result={}
        for accessor in (rich.getSelection,rich.getSymmetry):
            selection=om.MSelectionList();accessor(selection)
            for n in range(selection.length()):
                path=om.MDagPath();component=om.MObject()
                selection.getDagPath(n,path,component)
                if path.fullPathName()!=mesh.name or component.isNull():continue
                if not component.hasFn(om.MFn.kMeshVertComponent):continue
                fn=om.MFnSingleIndexedComponent(component)
                for k in range(fn.elementCount()):
                    weight=fn.weight(k).influence() if fn.hasWeights() else 1.0
                    if weight>1e-8:
                        i=fn.element(k)
                        result[i]=max(result.get(i,0),weight)
        result[seed]=1.0
        return result
    finally:
        om.MGlobal.setActiveSelectionList(saved)
        if has_rich:om.MGlobal.setRichSelection(old_rich)
