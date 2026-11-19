# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
"""Camera-independent relaxation on a connected local high-mesh patch."""
from __future__ import division, unicode_literals
import heapq
from collections import OrderedDict
import maya.api.OpenMaya as om
from .compat import touch
from .surface_query import create_intersector,filtered_intersector


class Surface(object):
    def __init__(self,mesh):
        # World-space mesh data avoids metric errors under non-uniform scaling.
        self.data=om.MFnMeshData().create()
        self.fn=om.MFnMesh()
        self.points=mesh.points()
        counts,vertices=mesh.fn.getVertices()
        self.object=self.fn.create(self.points,counts,vertices,parent=self.data)
        self.intersector=create_intersector(self.fn,self.points)
        self.faces=OrderedDict()
        self.iterator=om.MItMeshPolygon(self.object)
        self.patches=OrderedDict()

    def face(self,index):
        if index not in self.faces:
            ids=self.fn.getPolygonVertices(index)
            center=om.MVector()
            for i in ids:center+=om.MVector(self.points[i])
            center*=1.0/len(ids)
            self.iterator.setIndex(index)
            self.faces[index]=(om.MPoint(center),self.fn.getPolygonNormal(index),
                               list(self.iterator.getConnectedFaces()))
            if len(self.faces)>32768:self.faces.popitem(last=False)
        touch(self.faces,index)
        return self.faces[index]

    def patch(self,face,radius):
        key=(face,round(radius,6))
        if key in self.patches:
            touch(self.patches,key)
            return self.patches[key]
        normal=self.face(face)[1]
        distances={face:0.0}
        queue=[(0.0,face)]
        accepted=[]
        while queue and len(accepted)<2048:
            distance,index=heapq.heappop(queue)
            if distance!=distances[index]:continue
            accepted.append(index)
            center,unused,neighbors=self.face(index)
            for neighbor in neighbors:
                other,other_normal,unused=self.face(neighbor)
                length=distance+(other-center).length()
                if (length<=radius and normal*other_normal>0.05 and
                        length<distances.get(neighbor,float('inf'))):
                    distances[neighbor]=length
                    heapq.heappush(queue,(length,neighbor))
        inter=Patch(self,sorted(accepted))
        self.patches[key]=inter
        if len(self.patches)>128:self.patches.popitem(last=False)
        return inter


class Patch(object):
    """Retain a compact connected patch on APIs without the face-ID filter."""
    def __init__(self,surface,faces):
        self.intersector=filtered_intersector(surface.fn,surface.points,faces)
        if self.intersector is None:
            # Older Maya cannot restrict an intersector to a list of faces.
            # Construct only those faces in memory; never relax on the entire
            # layered mesh as a fallback, which would lose layer protection.
            ids={};points=[];counts=[];vertices=[]
            for face in faces:
                polygon=surface.fn.getPolygonVertices(face)
                counts.append(len(polygon))
                for index in polygon:
                    if index not in ids:
                        ids[index]=len(points)
                        points.append(surface.points[index])
                    vertices.append(ids[index])
            self.data=om.MFnMeshData().create()
            self.fn=om.MFnMesh()
            self.object=self.fn.create(points,counts,vertices,parent=self.data)
            self.intersector=create_intersector(self.fn,points)

    def getClosestPoint(self,point):
        return self.intersector.getClosestPoint(point)


class LocalRelax(object):
    def __init__(self,targets,original,neighbors):
        self.surfaces=targets.local_surfaces()
        self.original=om.MPointArray(original)
        self.neighbors=neighbors
        self.anchors={}

    def anchor(self,index):
        if index in self.anchors:return self.anchors[index]
        p=self.original[index]
        lengths=[(self.original[j]-p).length() for j in self.neighbors[index]]
        scale=sum(lengths)/len(lengths) if lengths else 0
        if scale<1e-8:
            self.anchors[index]=None
            return None
        best=None
        for n,surface in enumerate(self.surfaces):
            hit=surface.intersector.getClosestPoint(p)
            if hit is None:continue
            distance=(om.MPoint(hit.point)-p).length()
            if best is None or distance<best[0]:best=(distance,n,hit.face)
        # Do not pull a remote low-poly point to an unrelated part of the body.
        if best is None or best[0]>scale*0.75:
            self.anchors[index]=None
            return None
        surface=self.surfaces[best[1]]
        anchor=(surface.patch(best[2],scale*1.5),scale)
        self.anchors[index]=anchor
        return anchor

    def relax(self,points,weights,strength,locked=(),offset=0.0,neighbors=None):
        result={}
        neighbors=self.neighbors if neighbors is None else neighbors
        for i,weight in weights.items():
            if i in locked or not neighbors[i] or weight<=0:continue
            anchor=self.anchor(i)
            if anchor is None:continue
            patch,scale=anchor
            hit=patch.getClosestPoint(points[i])
            if hit is None:continue
            normal=om.MVector(hit.normal).normal()
            average=om.MVector()
            for j in neighbors[i]:average+=om.MVector(points[j])
            average*=1.0/len(neighbors[i])
            delta=average-om.MVector(points[i])
            # Tangential motion changes spacing without flattening the depth.
            tangent=points[i]+delta-normal*(delta*normal)
            hit=patch.getClosestPoint(tangent)
            if hit is None:continue
            target=om.MPoint(hit.point)+om.MVector(hit.normal).normal()*offset
            delta=(target-points[i])*min(1.0,max(0.0,strength*weight))
            limit=scale*0.25*min(1.0,weight)
            if delta.length()>limit:delta=delta.normal()*limit
            result[i]=points[i]+delta
        return result


class TriangleIndex(object):
    """Visit only triangles incident to vertices affected by this brush step."""
    def __init__(self,triangles):
        self.triangles=list(triangles)
        self.vertices={}
        for index,triangle in enumerate(self.triangles):
            for vertex in triangle:self.vertices.setdefault(vertex,[]).append(index)

    def affected(self,updates):
        indices=set()
        for vertex in updates:indices.update(self.vertices.get(vertex,()))
        return [self.triangles[i] for i in sorted(indices)]


def prevent_flips(points,updates,triangles):
    """Backtrack this simultaneous step if an affected triangle folds/collapses."""
    if not updates:return updates
    affected=(triangles.affected(updates) if isinstance(triangles,TriangleIndex) else
              [t for t in triangles if any(i in updates for i in t)])
    baseline=[]
    for a,b,c in affected:
        n=(points[b]-points[a])^(points[c]-points[a])
        if n.length()>1e-10:baseline.append(((a,b,c),n))
    for attempt in range(8):
        factor=0.5**attempt
        trial={i:points[i]+(p-points[i])*factor for i,p in updates.items()}
        valid=True
        for (a,b,c),normal in baseline:
            pa,pb,pc=(trial.get(i,points[i]) for i in (a,b,c))
            new=(pb-pa)^(pc-pa)
            if new.length()<normal.length()*0.2 or normal*new<=0:
                valid=False;break
        if valid:return trial
    return {}
