# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
"""Closest-surface queries for Maya API 2 and older API 1 bindings."""
from __future__ import division, unicode_literals
import maya.api.OpenMaya as om
import maya.OpenMaya as legacy

_API2_CREATE = None


class Hit(object):
    def __init__(self,hit):
        point,normal=hit.getPoint(),hit.getNormal()
        self.point=om.MPoint(point.x,point.y,point.z)
        self.normal=om.MVector(normal.x,normal.y,normal.z)
        self.face=hit.faceIndex()


class LegacyIntersector(object):
    def __init__(self,points,counts,vertices):
        self.data=legacy.MFnMeshData().create()
        self.fn=legacy.MFnMesh()
        positions=legacy.MPointArray()
        for p in points:positions.append(legacy.MPoint(p.x,p.y,p.z))
        polygon_counts,polygon_vertices=legacy.MIntArray(),legacy.MIntArray()
        for count in counts:polygon_counts.append(int(count))
        for index in vertices:polygon_vertices.append(int(index))
        self.object=self.fn.create(len(points),len(counts),positions,
            polygon_counts,polygon_vertices,self.data)
        self.intersector=legacy.MMeshIntersector()
        self.intersector.create(self.object,legacy.MMatrix())

    def getClosestPoint(self,point):
        hit=legacy.MPointOnMesh()
        try:
            self.intersector.getClosestPoint(legacy.MPoint(point.x,point.y,point.z),hit)
        except RuntimeError:
            return None
        return Hit(hit)


def create_intersector(fn,points):
    global _API2_CREATE
    if _API2_CREATE is not False:
        intersector=om.MMeshIntersector()
        try:
            intersector.create(fn.object(),om.MMatrix())
            _API2_CREATE=True
            return intersector
        except (TypeError,RuntimeError):
            # Maya 2018's API 2 binding reports an invalid keyword-list size.
            # Its API 1 implementation is usable and preserves the same data.
            _API2_CREATE=False
    counts,vertices=fn.getVertices()
    return LegacyIntersector(points,counts,vertices)


def filtered_intersector(fn,points,faces):
    if _API2_CREATE is False:
        return None
    intersector=om.MMeshIntersector()
    try:
        intersector.create(fn.object(),om.MMatrix(),faces)
        return intersector
    except (TypeError,RuntimeError):
        return None
