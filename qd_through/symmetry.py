# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
"""Reciprocal spatial pairing with Maya's reflection matrix."""
from __future__ import division, unicode_literals
import itertools
import math
import maya.api.OpenMaya as om
from maya import cmds
from . import native


class Symmetry(object):
    def __init__(self, points, matrix, tolerance, preserve_seam=True):
        self.matrix = matrix
        self.preserve_seam = preserve_seam
        self.original = om.MPointArray(points)
        self.pairs = {}
        size = max(tolerance, 1e-7)
        def cell(p): return tuple(int(math.floor(p[k]/size)) for k in range(3))
        grid = {}
        for i,p in enumerate(points):
            grid.setdefault(cell(p), []).append(i)
        proposals = {}
        for i,p in enumerate(points):
            reflected = p*matrix
            # An exact seam point maps to itself even with coincident seam
            # vertices, which may intentionally be waiting for a weld.
            if (p-reflected).length() < 1e-7:
                proposals[i] = i
                continue
            base = cell(reflected)
            candidates = []
            for offset in itertools.product((-1,0,1), repeat=3):
                key = tuple(base[k]+offset[k] for k in range(3))
                for j in grid.get(key, ()):
                    distance = (points[j]-reflected).length()
                    if distance <= size:
                        candidates.append((distance,j))
            candidates.sort()
            # Ambiguous coincident sheets must not be paired at random.
            if candidates and (len(candidates)==1 or candidates[1][0]-candidates[0][0]>1e-8):
                proposals[i] = candidates[0][1]
        self.pairs = {i:j for i,j in proposals.items() if proposals.get(j)==i}

    @classmethod
    def read(cls, mesh, points):
        if (cmds.symmetricModelling(query=True,symmetry=True) and
                cmds.symmetricModelling(query=True,about=True)=='topo'):
            return TopologySymmetry(mesh,points)
        matrix = native.symmetry_matrix(mesh)
        if matrix is None:
            return None
        return cls(points, matrix, cmds.symmetricModelling(query=True,tolerance=True),
                   bool(cmds.symmetricModelling(query=True,preserveSeam=True)))

    def apply(self, updates, seed):
        result, visited = {}, set()
        preferred = self.original[seed] - self.original[seed]*self.matrix
        for i in sorted(updates):
            if i in visited or i not in self.pairs:
                continue
            j = self.pairs[i]
            visited.update((i,j))
            source = i
            if j != i and j in updates:
                side_i = (self.original[i]-self.original[i]*self.matrix)*preferred
                side_j = (self.original[j]-self.original[j]*self.matrix)*preferred
                source = i if side_i >= side_j else j
            target = self.pairs[source]
            point = om.MPoint(updates[source])
            if source == target:
                if self.preserve_seam:
                    point += (point*self.matrix-point)*0.5
                result[source] = point
            else:
                result[source] = point
                result[target] = point*self.matrix
        return result

    def weld_pairs(self, source, target):
        a,b = self.pairs.get(source),self.pairs.get(target)
        if a is None or b is None:
            return []
        pairs = [(source,target)]
        if {a,b} != {source,target}:
            pairs.append((a,b))
        return pairs

    def merge_center(self,source,target,points):
        point=points[source]
        return point+(point*self.matrix-point)*0.5


class TopologySymmetry(Symmetry):
    def __init__(self,mesh,points):
        from .topology import native_map
        self.pairs,self.sides,self.seams,self.matrix=native_map(mesh)
        self.original=om.MPointArray(points)
        self.preserve_seam=bool(cmds.symmetricModelling(query=True,preserveSeam=True))

    def apply(self,updates,seed):
        result,visited={},set()
        for i in sorted(updates):
            if i in visited or i not in self.pairs:
                continue
            j=self.pairs[i]
            visited.update((i,j))
            source=i
            if j!=i and j in updates and self.sides.get(j)==self.sides.get(seed):
                source=j
            target=self.pairs[source]
            delta=updates[source]-self.original[source]
            if source==target:
                if self.preserve_seam:
                    delta=(delta+delta*self.matrix)*0.5
                result[source]=self.original[source]+delta
            else:
                result[source]=updates[source]
                # Reflect displacement, not absolute position: posed or
                # asymmetric topology must not snap into a spatial mirror.
                result[target]=self.original[target]+delta*self.matrix
        return result

    def merge_center(self,source,target,points):
        return points[source]+(points[target]-points[source])*0.5
