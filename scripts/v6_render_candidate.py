#!/usr/bin/env python3
"""Actual multiview rasterization of the generated draft GLB: no 2D invented picture."""
import os
import numpy as np
import trimesh
import vtk
from vtk.util.numpy_support import numpy_to_vtk

out=os.environ.get("V6_OUT","/mnt/data/V6_PROCEDURAL_CANDIDATE")
mesh_file=os.path.join(out,"WINGED_CHARACTER_V6_NEW_SCULPT_CANDIDATE.glb")
scene=trimesh.load(mesh_file,force="scene")
window=vtk.vtkRenderWindow()
window.SetSize(1000,1200)
window.SetOffScreenRendering(1)
renderer=vtk.vtkRenderer()
renderer.SetBackground(.83,.85,.89)
window.AddRenderer(renderer)
for name,g in scene.geometry.items():
    if not isinstance(g,trimesh.Trimesh): continue
    points=vtk.vtkPoints()
    points.SetData(numpy_to_vtk(g.vertices.astype(np.float32)))
    triangles=np.column_stack([np.full(len(g.faces),3),g.faces]).astype(np.int64)
    polys=vtk.vtkCellArray()
    polys.SetCells(len(triangles),numpy_to_vtk(triangles.flatten(),deep=True,array_type=vtk.VTK_ID_TYPE))
    poly=vtk.vtkPolyData()
    poly.SetPoints(points)
    poly.SetPolys(polys)
    normals=vtk.vtkPolyDataNormals()
    normals.SetInputData(poly)
    normals.ComputePointNormalsOn()
    normals.ComputeCellNormalsOff()
    normals.Update()
    mapper=vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(normals.GetOutputPort())
    actor=vtk.vtkActor()
    actor.SetMapper(mapper)
    if hasattr(g.visual,"vertex_colors") and len(g.visual.vertex_colors):
        color=np.mean(g.visual.vertex_colors[:,:3],axis=0)/255
        actor.GetProperty().SetColor(*color)
    actor.GetProperty().SetAmbient(.4)
    actor.GetProperty().SetDiffuse(.7)
    actor.GetProperty().SetSpecular(.3)
    actor.GetProperty().SetSpecularPower(20)
    renderer.AddActor(actor)
camera=renderer.GetActiveCamera()
camera.ParallelProjectionOn()
camera.SetParallelScale(95)
views=[
 ("FRONT",(0,-310,90)),
 ("BACK",(0,310,90)),
 ("LEFT",(-300,0,90)),
 ("RIGHT",(300,0,90)),
 ("3Q",(-205,-235,118)),
]
for name,pos in views:
    camera.SetFocalPoint(0,0,77)
    camera.SetPosition(*pos)
    camera.SetViewUp(0,0,1)
    renderer.ResetCameraClippingRange()
    window.Render()
    f=vtk.vtkWindowToImageFilter()
    f.SetInput(window)
    f.SetInputBufferTypeToRGB()
    f.ReadFrontBufferOff()
    f.Update()
    writer=vtk.vtkPNGWriter()
    writer.SetFileName(os.path.join(out,"V6_"+name+"_RENDER.png"))
    writer.SetInputConnection(f.GetOutputPort())
    writer.Write()
    print("rendered:",name)
