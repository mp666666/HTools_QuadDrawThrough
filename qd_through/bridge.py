# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
from __future__ import division, unicode_literals
import os
import uuid
from maya import cmds

PENDING = {}


def ensure_plugin():
    if not hasattr(cmds, 'qdtApplyStroke'):
        cmds.loadPlugin(os.path.join(os.path.dirname(__file__), 'undo_plugin.py'), quiet=True)


def commit(mesh, before, after, weld_pairs=()):
    ensure_plugin()
    token = uuid.uuid4().hex
    PENDING[token] = (mesh, before, after)
    cmds.undoInfo(openChunk=True, chunkName='HTools_QuadDrawThrough')
    applied = False
    error = None
    try:
        cmds.qdtApplyStroke(token)
        applied = True
        if weld_pairs:
            from .welding import vertex_ids
            indices = vertex_ids(weld_pairs)
            components = [mesh.name+'.vtx[%d]'%i for i in indices]
            cmds.polyMergeVertex(components, distance=1e-8,
                alwaysMergeTwoVertices=len(indices)==2, constructionHistory=True,
                texture=False, worldSpace=True)
    except Exception as exc:
        error = exc
    finally:
        PENDING.pop(token, None)
        cmds.undoInfo(closeChunk=True)
    if error is not None:
        if applied:
            cmds.undo()
        else:
            mesh.set_points(before)
        raise error
