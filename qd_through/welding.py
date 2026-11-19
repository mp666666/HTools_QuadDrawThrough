# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
"""Screen-space vertex weld preview; topology is changed only on release."""
from __future__ import division, unicode_literals
import math
import maya.api.OpenMaya as om


def plan(points, updates, source, view, radius, world_radius, symmetry=None,visible=None):
    proposed = om.MPointArray(points)
    for i,p in updates.items():
        proposed[i] = p
    origin = proposed[source]
    x,y,shown_origin = view.worldToView(origin)
    if not shown_origin or radius <= 0:
        return updates, []
    candidates = []
    for j,p in enumerate(proposed):
        if j == source:
            continue
        px,py,shown = view.worldToView(p)
        distance = math.hypot(px-x,py-y)
        if shown and distance <= radius and (origin-p).length() <= world_radius:
            if visible is not None and not visible(j):
                continue
            if symmetry and j not in symmetry.pairs:
                continue
            candidates.append((distance,(origin-p).length(),j))
    if not candidates:
        return updates, []
    target = min(candidates)[2]
    pairs = symmetry.weld_pairs(source,target) if symmetry else [(source,target)]
    if not pairs:
        return updates, []
    result = dict(updates)
    if symmetry and symmetry.pairs.get(source) == target:
        point = symmetry.merge_center(source,target,proposed)
        result[source] = result[target] = point
    else:
        for a,b in pairs:
            result[a] = om.MPoint(proposed[b])
    return result, pairs


def vertex_ids(pairs):
    return sorted({i for pair in pairs for i in pair})
