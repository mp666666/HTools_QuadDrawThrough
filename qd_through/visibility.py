# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
"""Frozen low-mesh visibility, deliberately ignoring Live high-mesh occlusion."""
from __future__ import division, unicode_literals
import maya.api.OpenMaya as om
from .geometry import closest_intersection


class FrontSurface(object):
    def __init__(self,mesh,points,ray):
        self.points=om.MPointArray(points)
        self.ray=ray
        counts,vertices=mesh.fn.getVertices()
        self.data=om.MFnMeshData().create()
        self.fn=om.MFnMesh()
        self.fn.create(self.points,counts,vertices,parent=self.data)
        self.normals=self.fn.getVertexNormals(True,om.MSpace.kObject)
        self.accel=self.fn.autoUniformGridParams()
        self.cache={}
        bounds=om.MBoundingBox()
        for p in points:bounds.expand(p)
        self.bounds=bounds
        self.epsilon=max((bounds.max-bounds.min).length()*1e-7,1e-5)

    def hit(self,x,y):
        origin,direction=self.ray(x,y)
        return closest_intersection(self.fn,om.MFloatPoint(origin),om.MFloatVector(direction),
            om.MSpace.kObject,1e12,False,accelParams=self.accel,ray_bounds=self.bounds)

    def visible(self,index,screen):
        if index in self.cache:return self.cache[index]
        x,y,shown=screen[index]
        if not shown:return False
        origin,direction=self.ray(x,y)
        p=self.points[index]
        depth=(p-origin)*direction
        # Reject faces pointing away, including a rear face seen through a hole.
        if depth<=0 or om.MVector(self.normals[index])*direction>1e-5:
            self.cache[index]=False
            return False
        # Aim exactly through the vertex, avoiding rounded-pixel edge misses.
        origin=p-direction*depth
        epsilon=max(self.epsilon,abs(depth)*5e-7,
                    max(abs(p[k]) for k in range(3))*5e-7)
        hit=closest_intersection(self.fn,om.MFloatPoint(origin),om.MFloatVector(direction),
            om.MSpace.kObject,depth+epsilon*4,False,accelParams=self.accel,ray_bounds=self.bounds)
        visible=hit is None or hit[1]>=depth-epsilon
        self.cache[index]=visible
        return visible
