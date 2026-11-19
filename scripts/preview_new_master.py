"""Visualize actual new master STL from five angles; no image-based beautification."""
import sys
from pathlib import Path
import numpy as np
import trimesh
import vtk
from vtk.util.numpy_support import numpy_to_vtk
from PIL import Image, ImageDraw

src = Path(sys.argv[1]); dst = Path(sys.argv[2])
mesh = trimesh.load(src, force="mesh")
if not isinstance(mesh,trimesh.Trimesh) or len(mesh.faces)<10000:
    raise ValueError("No real 3D geometry to inspect")
poly = vtk.vtkPolyData()
points=vtk.vtkPoints()
points.SetData(numpy_to_vtk(np.asarray(mesh.vertices,dtype=np.float32),deep=True))
poly.SetPoints(points)
cells=vtk.vtkCellArray()
for face in mesh.faces:
    cells.InsertNextCell(3)
    for j in face:
        cells.InsertCellPoint(int(j))
poly.SetPolys(cells)
normals=vtk.vtkPolyDataNormals()
normals.SetInputData(poly)
normals.SetConsistency(True)
normals.SetAutoOrientNormals(True)
normals.SetSplitting(False)
mapper=vtk.vtkPolyDataMapper()
mapper.SetInputConnection(normals.GetOutputPort())
actor=vtk.vtkActor()
actor.SetMapper(mapper)
actor.GetProperty().SetColor(.85,.86,.91)
actor.GetProperty().SetInterpolationToPhong()
actor.GetProperty().SetSpecular(.15)
actor.GetProperty().SetSpecularPower(24)
renderer=vtk.vtkRenderer()
renderer.SetBackground(.91,.93,.97)
renderer.AddActor(actor)
ambient=vtk.vtkLight()
ambient.SetPosition(120,-150,250)
ambient.SetFocalPoint(0,0,75)
ambient.SetIntensity(1.1)
renderer.AddLight(ambient)
window=vtk.vtkRenderWindow()
window.SetOffScreenRendering(True)
window.SetSize(700,850)
window.AddRenderer(renderer)
mosaic=Image.new("RGB",(700*3,900*2),(235,240,245))
draw=ImageDraw.Draw(mosaic)
views=[
    ("FRONT",(0,-360,90)),
    ("LEFT",(-360,0,90)),
    ("BACK",(0,360,90)),
    ("RIGHT",(360,0,90)),
    ("3/4",(290,-310,130)),
]
for n,(label,pos) in enumerate(views):
    camera=renderer.GetActiveCamera()
    camera.SetPosition(*pos)
    camera.SetFocalPoint(0,0,75)
    camera.SetViewUp(0,0,1)
    camera.ParallelProjectionOn()
    camera.SetParallelScale(93)
    renderer.ResetCameraClippingRange()
    window.Render()
    grab=vtk.vtkWindowToImageFilter()
    grab.SetInput(window)
    grab.Update()
    w=vtk.vtkPNGWriter()
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as d:
        path=Path(d)/"view.png"
        w.SetFileName(str(path))
        w.SetInputConnection(grab.GetOutputPort())
        w.Write()
        im=Image.open(path).convert("RGB")
        x=n%3*700;y=n//3*900
        mosaic.paste(im,(x,y))
        draw.text((x+28,y+862),label,fill=(12,16,26))
dst.parent.mkdir(parents=True,exist_ok=True)
mosaic.save(dst,optimize=True)
print("NEW_MASTER_FIVE_VIEWS",dst,flush=True)
