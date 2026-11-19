# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
"""Maya API geometry operations. No UI dependencies."""
from __future__ import division, unicode_literals
import heapq
import weakref
import maya.api.OpenMaya as om
from maya import cmds
from .compat import finalize, MAYA_YEAR


def closest_intersection(fn,*args,**kwargs):
    bounds=kwargs.pop('ray_bounds',None)
    result=fn.closestIntersection(*args,**kwargs)
    # Maya 2018 returns a tuple with face=-1 on a miss; newer Maya returns None.
    # Passing that sentinel into getPolygonVertices can crash older Maya.
    if result is not None and result[2]>=0:
        return result
    # Old uniform-grid intersections can miss a small mesh viewed from Maya's
    # distant default orthographic camera. Keep acceleration, but retry from
    # just before the bounding box instead of the camera. Preserve the original
    # ray distance for layer ordering and low-mesh occlusion comparisons.
    if MAYA_YEAR>=2025 or kwargs.get('accelParams') is None or args[4]:
        return None
    if bounds is None:
        bounds=fn.boundingBox
        bounds=om.MBoundingBox(bounds.min,bounds.max)
        if args[2]==om.MSpace.kWorld:
            bounds.transformUsing(fn.dagPath().inclusiveMatrix())
    origin,direction=om.MPoint(args[0]),om.MVector(args[1])
    near,far=0.0,float(args[3])
    for axis in range(3):
        if abs(direction[axis])<1e-15:
            if origin[axis]<bounds.min[axis] or origin[axis]>bounds.max[axis]:
                return None
            continue
        a=(bounds.min[axis]-origin[axis])/direction[axis]
        b=(bounds.max[axis]-origin[axis])/direction[axis]
        near,far=max(near,min(a,b)),min(far,max(a,b))
        if near>far:
            return None
    padding=max((bounds.max-bounds.min).length()*1e-4,1e-4)
    shift=max(0.0,near-padding)
    if shift<=0:
        return None
    retry=list(args)
    retry[0]=om.MFloatPoint(origin+direction*shift)
    retry[3]=min(float(args[3])-shift,far-shift+padding)
    result=fn.closestIntersection(*retry,**kwargs)
    if result is not None and result[2]>=0:
        return (result[0],result[1]+shift)+tuple(result[2:])
    return None


def mesh_path(node):
    selection = om.MSelectionList()
    selection.add(node)
    path = selection.getDagPath(0)
    if path.apiType() == om.MFn.kTransform:
        shapes = cmds.listRelatives(path.fullPathName(), shapes=True,
                                    noIntermediate=True, fullPath=True) or []
        shapes = [s for s in shapes if cmds.nodeType(s) == 'mesh']
        if len(shapes) != 1:
            raise ValueError('Select a transform containing exactly one polygon mesh.')
        selection = om.MSelectionList()
        selection.add(shapes[0])
        path = selection.getDagPath(0)
    if path.apiType() != om.MFn.kMesh:
        raise ValueError('Only polygon mesh targets are supported (no GPU cache / NURBS).')
    if path.isInstanced():
        raise ValueError('Instanced meshes are not supported. Use a unique mesh.')
    return path


class Mesh(object):
    def __init__(self, node):
        path = mesh_path(node)
        self.handle = om.MObjectHandle(path.node())

    @property
    def path(self):
        if not self.handle.isValid() or not self.handle.isAlive():
            raise RuntimeError('Bound mesh no longer exists. Bind meshes again.')
        return om.MDagPath.getAPathTo(self.handle.object())

    @property
    def fn(self):
        return om.MFnMesh(self.path)

    @property
    def name(self):
        return self.path.fullPathName()

    def points(self, world=True):
        return self.fn.getPoints(om.MSpace.kWorld if world else om.MSpace.kObject)

    def set_points(self, points):
        fn = self.fn
        if fn.numVertices != len(points):
            raise RuntimeError('Topology changed during a stroke; edit cancelled.')
        fn.setPoints(points, om.MSpace.kObject)
        fn.updateSurface()

    def adjacency(self):
        neighbors = [[] for _ in range(self.fn.numVertices)]
        boundary = set()
        iterator = om.MItMeshVertex(self.path)
        while not iterator.isDone():
            i = iterator.index()
            neighbors[i] = list(iterator.getConnectedVertices())
            if iterator.onBoundary():
                boundary.add(i)
            iterator.next()
        return neighbors, boundary


    def boundary_adjacency(self):
        """Only true boundary edges, excluding chords between border vertices."""
        neighbors=[[] for _ in range(self.fn.numVertices)]
        iterator=om.MItMeshEdge(self.path)
        while not iterator.isDone():
            if iterator.onBoundary():
                a,b=iterator.vertexId(0),iterator.vertexId(1)
                neighbors[a].append(b)
                neighbors[b].append(a)
            iterator.next()
        return neighbors


def relax_region(mesh,neighbors,border,seed,mode,lock_border=False):
    """Freeze the native lock policy at the start of a brush stroke."""
    if lock_border:
        mode=1
    elif mode==3:
        mode=2 if seed in border else 1
    if mode==1:
        return set(range(len(neighbors)))-border,neighbors
    if mode==2:
        boundary_neighbors=mesh.boundary_adjacency()
        if seed not in border:
            return set(),boundary_neighbors
        connected,todo={seed},[seed]
        while todo:
            for j in boundary_neighbors[todo.pop()]:
                if j not in connected:
                    connected.add(j)
                    todo.append(j)
        return connected,boundary_neighbors
    return set(range(len(neighbors))),neighbors


class Targets(object):
    def __init__(self, names):
        self.meshes = [Mesh(n) for n in names]
        self.accelerators = [m.fn.autoUniformGridParams() for m in self.meshes]
        self._surfaces=None
        self._surface_key=None
        self._dirty=True
        self._callbacks=[]
        self._cleanup=finalize(self,_remove_callbacks,self._callbacks)

    def local_surfaces(self):
        from .local_relax import Surface
        if not self._callbacks:
            reference=weakref.ref(self)
            def dirty(*unused):
                target=reference()
                if target is not None:target._dirty=True
            def destroyed(*unused):
                target=reference()
                if target is not None:
                    target._surfaces=None
                    target._surface_key=None
                    target._dirty=True
            for mesh in self.meshes:
                self._callbacks.append(om.MNodeMessage.addNodeDirtyCallback(mesh.handle.object(),dirty))
                self._callbacks.append(om.MNodeMessage.addNodeDestroyedCallback(mesh.handle.object(),destroyed))
        key=tuple((m.handle.hashCode(),m.fn.numVertices,m.fn.numPolygons,
                   tuple(m.path.inclusiveMatrix())) for m in self.meshes)
        if self._dirty or key!=self._surface_key or self._surfaces is None:
            self._surfaces=[Surface(m) for m in self.meshes]
            self._surface_key=key
            self._dirty=False
        return self._surfaces

    def close(self):
        _remove_callbacks(self._callbacks)
        self._surfaces=None
        self._dirty=True

    def hit(self, origin, direction):
        """First forward ray hit across bound targets; no closest-point fallback."""
        direction = om.MVector(direction).normal()
        best = None
        for mesh, accel in zip(self.meshes, self.accelerators):
            fn = mesh.fn
            result = closest_intersection(fn,
                om.MFloatPoint(origin), om.MFloatVector(direction),
                om.MSpace.kWorld, 1.0e12, False, accelParams=accel)
            if result is not None and (best is None or result[1] < best[1]):
                best = (om.MPoint(result[0]), result[1], mesh, result[2])
        return best


def _remove_callbacks(callbacks):
    for callback in callbacks:
        try:om.MMessage.removeCallback(callback)
        except RuntimeError:pass
    del callbacks[:]


def connected_brush(points, neighbors, seed, radius):
    """Geodesic radius: do not smooth a separate overlapping low-poly shell."""
    distances = {seed: 0.0}
    queue = [(0.0, seed)]
    while queue:
        distance, i = heapq.heappop(queue)
        if distance != distances[i]:
            continue
        for j in neighbors[i]:
            candidate = distance + (points[i] - points[j]).length()
            if candidate <= radius and candidate < distances.get(j, float('inf')):
                distances[j] = candidate
                heapq.heappush(queue, (candidate, j))
    return distances


def relax_positions(points, neighbors, weights, strength, locked=()):
    """Simultaneous Laplacian step; caller handles surface constraint."""
    result = {}
    for i, weight in weights.items():
        if i in locked or not neighbors[i]:
            continue
        center = om.MVector()
        for j in neighbors[i]:
            center += om.MVector(points[j])
        center *= 1.0/len(neighbors[i])
        result[i] = points[i] + (center - om.MVector(points[i])) * (strength * weight)
    return result
