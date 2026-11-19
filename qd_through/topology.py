# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
"""Read Maya's established topology symmetry by encoded selection queries.

Two queries per vertex-ID bit recover the involution in O(log V) selections,
without a spatial guess or a slow query per vertex. Selection and soft-select
state are restored; helper commands do not enter Maya's undo queue.
"""
from __future__ import division, unicode_literals
import json
from maya import cmds
import maya.OpenMaya as legacy
import maya.api.OpenMaya as om
from .geometry import mesh_path


def native_map(mesh):
    active = cmds.symmetricModelling(query=True,topoSymmetry=True)
    if not active or mesh_path(active).node() != mesh.path.node():
        raise ValueError('请先在当前低模上选择中线边，启用 Maya Topology 对称。')
    count = mesh.fn.numVertices
    selected = legacy.MSelectionList()
    legacy.MGlobal.getActiveSelectionList(selected)
    old_rich = legacy.MRichSelection()
    has_rich=True
    try:
        legacy.MGlobal.getRichSelection(old_rich)
    except RuntimeError:
        if selected.length():
            raise
        has_rich=False
    soft = cmds.softSelect(query=True,softSelectEnabled=True)
    path_selection = legacy.MSelectionList()
    path_selection.add(mesh.name)
    path = legacy.MDagPath()
    path_selection.getDagPath(0,path)

    def query(indices):
        if not indices:
            return set(),{},set(),None
        # Compact contiguous ranges keep MEL command size manageable.
        runs=[]
        start=end=indices[0]
        for i in indices[1:]:
            if i==end+1:
                end=i
            else:
                runs.append((start,end));start=end=i
        runs.append((start,end))
        args=[json.dumps(mesh.name+'.vtx[%d:%d]'%(a,b),ensure_ascii=False) for a,b in runs]
        legacy.MGlobal.executeCommand('select -r -sym '+ ' '.join(args)+';',False,False)
        rich=legacy.MRichSelection()
        legacy.MGlobal.getRichSelection(rich)
        found,sides,seams=set(),{},set()
        for side,accessor in enumerate((rich.getSelection,rich.getSymmetry)):
            items=legacy.MSelectionList();accessor(items)
            for n in range(items.length()):
                dp=legacy.MDagPath();comp=legacy.MObject()
                items.getDagPath(n,dp,comp)
                if comp.isNull() or dp.fullPathName()!=mesh.name:
                    continue
                fn=legacy.MFnSingleIndexedComponent(comp)
                for k in range(fn.elementCount()):
                    i=fn.element(k)
                    found.add(i);sides[i]=side
                    if fn.hasWeights() and fn.weight(k).seam()>0.999:
                        seams.add(i)
        mat=legacy.MMatrix()
        rich.getSymmetryMatrix(path,legacy.MSpace.kWorld,mat)
        matrix=om.MMatrix([mat(r,c) for r in range(4) for c in range(4)])
        return found,sides,seams,matrix

    try:
        if soft:
            legacy.MGlobal.executeCommand('softSelect -softSelectEnabled 0;',False,False)
        all_ids=list(range(count))
        unused,sides,seams,matrix=query(all_ids)
        partner=[0]*count
        for bit in range(max(1,(count-1).bit_length())):
            mask=1<<bit
            ones=query([i for i in all_ids if i&mask])[0]
            zeros=query([i for i in all_ids if not i&mask])[0]
            for i in all_ids:
                if ((i&mask) and i not in zeros) or (not(i&mask) and i in ones):
                    partner[i]|=mask
        pairs={i:j for i,j in enumerate(partner) if j<count and partner[j]==i
               and (j!=i or i in seams)}
        return pairs,sides,seams,matrix
    finally:
        if soft:
            legacy.MGlobal.executeCommand('softSelect -softSelectEnabled 1;',False,False)
        legacy.MGlobal.setActiveSelectionList(selected)
        if has_rich:
            legacy.MGlobal.setRichSelection(old_rich)
