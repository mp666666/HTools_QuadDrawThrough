# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
"""One undoable command per completed stroke; no scene nodes added."""
from __future__ import division, unicode_literals
import maya.api.OpenMaya as om


def maya_useNewAPI():
    pass


class ApplyStroke(om.MPxCommand):
    def doIt(self, args):
        from qd_through import bridge
        self.commandString = 'qdtApplyStroke'
        self.mesh, self.before, self.after = bridge.PENDING.pop(args.asString(0))
        self.redoIt()

    def redoIt(self):
        self.mesh.set_points(self.after)

    def undoIt(self):
        self.mesh.set_points(self.before)

    def isUndoable(self):
        return True


def initializePlugin(obj):
    om.MFnPlugin(obj, 'HTools_QuadDrawThrough', '1.0.0', 'Any').registerCommand(
        'qdtApplyStroke', ApplyStroke)


def uninitializePlugin(obj):
    om.MFnPlugin(obj).deregisterCommand('qdtApplyStroke')
