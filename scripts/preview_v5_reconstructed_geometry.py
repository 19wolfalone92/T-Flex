"""Render real colour-separated 3D geometry in five orthographic views.

No illustration AI, no texture tricks; shows exactly the STL surfaces in the
new release. Intended for human geometry QA, not print certification.
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
import trimesh
import vtk
from vtk.util.numpy_support import numpy_to_vtk


COLORS = {
    1: (.16, .16, .20), 2: (.13, .14, .18),
    3: (.17, .17, .19), 4: (.17, .17, .19),
    5: (.46, .67, .91), 6: (.46, .67, .91),
    7: (.91, .92, .95), 8: (.95, .75, .67),
    9: (.95, .75, .67), 10: (.85, .88, .93),
    11: (.11, .49, .88), 12: (.11, .49, .88),
    13: (.9, .15, .23), 14: (.13, .13, .17), 15: (.07, .07, .10),
}
VIEWPOINTS = {
    "FRONT": (0,-300,110),
    "LEFT": (-300,0,110),
    "BACK": (0,300,110),
    "RIGHT": (300,0,110),
    "3/4 VIEW": (240,-280,145),
}


def render(input_folder: Path, output_file: Path) -> None:
    r=vtk.vtkRenderer()
    r.SetBackground(.92,.94,.98)
    window=vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(820,940)
    window.SetMultiSamples(4)
    window.AddRenderer(r)
    files=sorted(input_folder.glob("*.stl"))
    if len(files)!=15:
        raise ValueError("Need fifteen separately coloured STL parts")
    for stl in files:
        number=int(stl.name[:2])
        mesh=trimesh.load_mesh(stl,force="mesh")
        if not (mesh.is_watertight and mesh.volume>0):
            raise ValueError("Invalid STL before preview "+stl.name)
        pd=vtk.vtkPolyData()
        points=vtk.vtkPoints()
        points.SetData(numpy_to_vtk(np.asarray(mesh.vertices,dtype=np.float32),deep=True))
        pd.SetPoints(points)
        cells=vtk.vtkCellArray()
        for a,b,c in mesh.faces:
            cells.InsertNextCell(3)
            cells.InsertCellPoint(int(a))
            cells.InsertCellPoint(int(b))
            cells.InsertCellPoint(int(c))
        pd.SetPolys(cells)
        mapper=vtk.vtkPolyDataMapper()
        mapper.SetInputData(pd)
        actor=vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(*COLORS[number])
        actor.GetProperty().SetInterpolationToPhong()
        actor.GetProperty().SetSpecular(.15)
        actor.GetProperty().SetSpecularPower(15)
        r.AddActor(actor)
    mosaic=Image.new("RGB",(820*3,990*2),(245,246,249))
    draw=ImageDraw.Draw(mosaic)
    for index,(name,position) in enumerate(VIEWPOINTS.items()):
        camera=r.GetActiveCamera()
        camera.SetPosition(*position)
        camera.SetFocalPoint(0,0,75)
        camera.SetViewUp(0,0,1)
        camera.ParallelProjectionOn()
        camera.SetParallelScale(97)
        r.ResetCameraClippingRange()
        window.Render()
        grab=vtk.vtkWindowToImageFilter()
        grab.SetInput(window)
        grab.Update()
        data=vtk.vtkPNGWriter()
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/"angle.png"
            data.SetFileName(str(file))
            data.SetInputConnection(grab.GetOutputPort())
            data.Write()
            frame=Image.open(file).convert("RGB")
            x=index%3*820
            y=index//3*990
            mosaic.paste(frame,(x,y))
            draw.text((x+30,y+950),name,fill=(10,10,20))
    output_file.parent.mkdir(parents=True,exist_ok=True)
    mosaic.save(output_file,optimize=True)
    print("V5_PREVIEW_RENDERED",output_file,flush=True)


if __name__=="__main__":
    render(Path(sys.argv[1]),Path(sys.argv[2]))
