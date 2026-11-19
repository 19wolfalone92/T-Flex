"""Topology-preserving blind connector sockets in triangulated planar split faces.

Only NEW vertices are snapped to the STL float32 grid. Existing vertices and
cross-shell contacts are never welded; avoids losing sleeves/feathers.
"""
from __future__ import annotations
import numpy as np
import trimesh
import vtk
from scipy.spatial import cKDTree
from shapely.geometry import Point, Polygon, LineString
from shapely.ops import triangulate, unary_union
from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray, vtk_to_numpy


def to_vtk(m):
    data = vtk.vtkPolyData()
    points = vtk.vtkPoints()
    points.SetData(numpy_to_vtk(np.asarray(m.vertices), deep=True))
    data.SetPoints(points)
    cells = vtk.vtkCellArray()
    triangles = np.column_stack((np.full(len(m.faces), 3), m.faces)).astype(np.int64)
    cells.SetCells(len(m.faces), numpy_to_vtkIdTypeArray(triangles.ravel(), deep=True))
    data.SetPolys(cells)
    return data


def from_vtk(p):
    triangle = vtk.vtkTriangleFilter()
    triangle.SetInputData(p)
    triangle.Update()
    m = triangle.GetOutput()
    if m.GetNumberOfCells() == 0:
        raise ValueError("No triangles after socket repair")
    vertices = vtk_to_numpy(m.GetPoints().GetData())
    faces = vtk_to_numpy(m.GetPolys().GetData()).reshape(-1,4)[:,1:]
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


def contains_cap(shell, centre, axis, radius):
    axes = [x for x in range(3) if x != axis]
    verts, faces = shell.vertices, shell.faces
    on_face = np.all(np.abs(verts[faces][:,:,axis] - centre[axis]) < 2e-4, axis=1)
    if not np.any(on_face):
        return False
    polygon = unary_union([Polygon(verts[f][:,axes]) for f in faces[on_face]])
    disk = Point(*np.asarray(centre)[axes]).buffer(radius, resolution=16)
    return polygon.buffer(-0.02).contains(disk)


def cut_one_shell(mesh, centre, axis, positive_in, radius, depth):
    axes = [x for x in range(3) if x != axis]
    original = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    level = float(centre[axis])
    middle = np.asarray(centre)[axes]
    cap = np.all(np.abs(original[faces][:,:,axis] - level) < 2e-4, axis=1)
    cap_faces, untouched = faces[cap], faces[~cap]
    if not len(cap_faces):
        raise ValueError("Socket is not on planar cut interface")
    circle = Point(*middle).buffer(radius, resolution=16)
    border = LineString(circle.exterior.coords)
    if not unary_union([Polygon(original[f][:,axes]) for f in cap_faces]).buffer(-0.02).contains(circle):
        raise ValueError("Hole intersects thin edge of mating face")
    kept, added = [], []
    ring_points = {tuple(np.round(q,7)) for q in np.asarray(circle.exterior.coords)[:-1]}
    for face in cap_faces:
        shape = Polygon(original[face][:,axes])
        if not shape.intersects(circle):
            kept.append(face)
            continue
        difference = shape.difference(circle)
        if difference.is_empty:
            continue
        polygons = []
        if difference.geom_type == "Polygon":
            polygons = [difference]
        elif difference.geom_type == "MultiPolygon":
            polygons = list(difference.geoms)
        elif difference.geom_type == "GeometryCollection":
            polygons = [g for g in difference.geoms if g.geom_type == "Polygon"]
        for area in polygons:
            for triangle in triangulate(area):
                if not area.covers(triangle):
                    continue
                coords = np.asarray(triangle.exterior.coords)[:3]
                added.append(coords)
                for point in coords:
                    if border.distance(Point(*point)) < 1e-5:
                        ring_points.add(tuple(np.round(point,7)))
    ring = np.array(sorted(ring_points, key=lambda p: np.arctan2(p[1]-middle[1],p[0]-middle[0])))
    def lift(xy, offset):
        point = np.empty(3)
        point[axis] = level + positive_in*offset
        point[axes] = xy
        return point
    original_normal = np.mean(np.cross(
        original[cap_faces[:,1]] - original[cap_faces[:,0]],
        original[cap_faces[:,2]] - original[cap_faces[:,0]]), axis=0)
    original_normal /= np.linalg.norm(original_normal)
    vertices = list(original)
    new_faces = list(untouched) + list(kept)
    for xy in added:
        coords = np.array([lift(p,0) for p in xy])
        if np.dot(np.cross(coords[1]-coords[0],coords[2]-coords[0]),original_normal)<0:
            coords[[1,2]] = coords[[2,1]]
        start = len(vertices)
        vertices.extend(coords)
        new_faces.append([start,start+1,start+2])
    for i in range(len(ring)):
        a,b = ring[i],ring[(i+1)%len(ring)]
        coords = np.array([lift(a,0),lift(b,0),lift(a,depth),lift(b,depth)])
        start=len(vertices)
        vertices.extend(coords)
        first=[start,start+1,start+2]
        second=[start+2,start+1,start+3]
        n=np.cross(coords[1]-coords[0],coords[2]-coords[0])[axes]
        if np.dot(n,middle-(a+b)/2)<0:
            first=[start,start+2,start+1]
            second=[start+2,start+3,start+1]
        new_faces.extend([first,second])
    for i in range(len(ring)):
        a,b=ring[i],ring[(i+1)%len(ring)]
        coords=np.array([lift(middle,depth),lift(a,depth),lift(b,depth)])
        if np.dot(np.cross(coords[1]-coords[0],coords[2]-coords[0]),original_normal)<0:
            coords[[1,2]]=coords[[2,1]]
        start=len(vertices)
        vertices.extend(coords)
        new_faces.append([start,start+1,start+2])
    # Deduplicate NEW cap and socket vertices only; preserve nearby original
    # edges, otherwise the STL can turn from manifold to non-manifold.
    all_vertices = np.asarray(vertices,dtype=float)
    old_count=len(original)
    remap=np.arange(len(all_vertices),dtype=np.int64)
    tree=cKDTree(original)
    newmap={}
    for i in range(old_count,len(all_vertices)):
        point=all_vertices[i].astype(np.float32).astype(np.float64)
        all_vertices[i]=point
        distance,nearest=tree.query(point)
        if distance<=1e-5:
            remap[i]=int(nearest)
            continue
        key=tuple(np.round(point,5))
        if key in newmap:
            remap[i]=newmap[key]
        else:
            newmap[key]=i
    result=trimesh.Trimesh(vertices=all_vertices,faces=remap[np.asarray(new_faces,dtype=np.int64)],process=False)
    result.remove_unreferenced_vertices()
    return result


def socket(mesh, centre, axis, direction, radius, depth):
    shells=mesh.split(only_watertight=False)
    changed=0
    out=[]
    for shell in shells:
        if not contains_cap(shell, centre, axis, radius):
            out.append(shell)
            continue
        changed+=1
        local=cut_one_shell(shell,centre,axis,direction,radius,depth)
        close=vtk.vtkFillHolesFilter()
        close.SetInputData(to_vtk(local))
        close.SetHoleSize(0.5)
        close.Update()
        normal=vtk.vtkPolyDataNormals()
        normal.SetInputConnection(close.GetOutputPort())
        normal.SetAutoOrientNormals(True)
        normal.SetConsistency(True)
        normal.SetSplitting(False)
        normal.Update()
        patched=from_vtk(normal.GetOutput())
        removed=shell.volume-patched.volume
        expected=np.pi*radius**2*depth
        if not (patched.is_watertight and patched.is_winding_consistent and 0.975*expected<removed<1.025*expected):
            raise ValueError("Invalid socket after reconstruction")
        out.append(patched)
    if changed!=1:
        raise ValueError("Socket must intersect exactly one closed shell")
    joined=trimesh.util.concatenate(out)
    if not (joined.is_watertight and joined.is_winding_consistent and joined.volume>0):
        raise ValueError("Socket join altered original mesh topology")
    return joined
