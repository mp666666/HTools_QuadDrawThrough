# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
"""Read existing Maya controls; never change modelling preferences implicitly."""
from __future__ import division, unicode_literals
import json
from maya import cmds, mel
import maya.OpenMaya as legacy
import maya.api.OpenMaya as om
from .geometry import mesh_path
from .compat import string_types


def symmetry_matrix(mesh):
    if not cmds.symmetricModelling(query=True, symmetry=True):
        return None
    # The legacy bridge is needed: Maya 2027's API 2 rich-selection accessor
    # rejects API 2 MDagPath arguments. Let Maya supply its actual reflection.
    selection = legacy.MSelectionList()
    selection.add(mesh.name)
    path = legacy.MDagPath()
    selection.getDagPath(0, path)
    rich = legacy.MRichSelection()
    try:
        legacy.MGlobal.getRichSelection(rich)
    except RuntimeError:
        # Quad Draw can retain appendMesh after clearing the active selection.
        # Maya raises kFailure for getRichSelection in that valid tool state.
        previous = legacy.MSelectionList()
        legacy.MGlobal.getActiveSelectionList(previous)
        if previous.length():
            raise
        try:
            legacy.MGlobal.setActiveSelectionList(selection)
            legacy.MGlobal.getRichSelection(rich)
        finally:
            legacy.MGlobal.setActiveSelectionList(previous)
    matrix = legacy.MMatrix()
    rich.getSymmetryMatrix(path, legacy.MSpace.kWorld, matrix)
    return om.MMatrix([matrix(r,c) for r in range(4) for c in range(4)])


def weld_settings():
    if cmds.softSelect(query=True, softSelectEnabled=True):
        return False, 0.0
    if not mel.eval('exists nexOpt'):
        return False, 0.0
    return bool(mel.eval('nexOpt -q useAutoWeld')), float(mel.eval('nexOpt -q autoWeldTolerance'))


def relax_mode():
    """Maya relaxAffects: all=0, interior=1, border=2, auto-lock=3."""
    if not mel.eval('exists nexOpt'):
        return 0
    return int(mel.eval('nexOpt -q relaxAffects'))


def _shapes(nodes):
    result = []
    for node in nodes:
        try:
            name = mesh_path(node).fullPathName()
            if name not in result:
                result.append(name)
        except (RuntimeError, ValueError):
            continue
    return result


def quad_mesh():
    """The native build mesh can exist even when active selection is empty."""
    if 'quaddraw' not in (cmds.currentCtx() or '').lower() or not mel.eval('exists nexCtx'):
        return None
    current=mel.eval('nexCtx -q -appendMesh')
    build=_shapes([current] if isinstance(current,string_types) and current else [])
    return build[0] if len(build)==1 else None


def current_meshes():
    live = cmds.ls(live=True, long=True) or []
    high = _shapes(live)
    if not high:
        return None, []
    build=quad_mesh()
    if build and build not in high:
        return build,high
    # Selection / highlight are fallbacks before Quad Draw has a build mesh.
    low = [p for p in _shapes(cmds.ls(selection=True, objectsOnly=True, long=True) or [])
           if p not in high]
    if not low:
        low = [p for p in _shapes(cmds.ls(hilite=True, long=True) or []) if p not in high]
    return (low[0] if len(low) == 1 else None), high


def select_for_tool(mesh):
    """Restore the build object without adding a selection-only undo entry."""
    path=mesh.path
    path.pop()
    selected=legacy.MSelectionList()
    selected.add(path.fullPathName())
    legacy.MGlobal.setActiveSelectionList(selected)
    # The tool's internal build object is separate from active selection.
    # PostToolChanged has already initialized Multi-Cut with an empty object;
    # provide the same native build mesh it receives from a normal selection.
    if mel.eval('exists nexCtx'):
        legacy.MGlobal.executeCommand('nexCtx -e -appendMesh '+
            json.dumps(mesh.name,ensure_ascii=False)+';',False,False)
