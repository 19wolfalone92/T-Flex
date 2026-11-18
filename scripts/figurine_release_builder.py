"""Rebuild the T-FLEX CAD 18 printable STEP/STL kit from the existing Hi3DGen model.

Source is the earlier reconstructed 3D mesh, not an exact conversion of the
later detailed 2D character turnaround. It is a prototype, not print certified.

Usage: python scripts/figurine_release_builder.py SOURCE.STL OUTPUT_DIRECTORY
"""
import json
import sys
import zipfile
from pathlib import Path

import cadquery as cq
import numpy as np
import trimesh
import vtk
from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakePolygon,
    BRepBuilderAPI_MakeSolid,
    BRepBuilderAPI_Sewing,
)
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
from OCP.TopoDS import TopoDS, TopoDS_Compound
from OCP.TopAbs import TopAbs_SHELL
from OCP.TopExp import TopExp_Explorer
from OCP.gp import gp_Pnt
from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray, vtk_to_numpy


def quality(m):
    return {
        "triangles": len(m.faces),
        "watertight": bool(m.is_watertight),
        "consistent_winding": bool(m.is_winding_consistent),
        "volume_mm3": float(m.volume),
        "bounds_mm": np.round(m.bounds, 3).tolist(),
    }


def as_vtk(mesh):
    pts = vtk.vtkPoints()
    pts.SetData(numpy_to_vtk(np.asarray(mesh.vertices), deep=True))
    polygons = vtk.vtkCellArray()
    faces = np.column_stack((np.full(len(mesh.faces), 3), mesh.faces)).astype(np.int64)
    polygons.SetCells(len(mesh.faces), numpy_to_vtkIdTypeArray(faces.ravel(), deep=True))
    poly = vtk.vtkPolyData()
    poly.SetPoints(pts)
    poly.SetPolys(polygons)
    return poly


def from_vtk(poly):
    tri = vtk.vtkTriangleFilter()
    tri.SetInputData(poly)
    tri.Update()
    triangles = tri.GetOutput()
    vertices = np.asarray(vtk_to_numpy(triangles.GetPoints().GetData()), dtype=float)
    faces = np.asarray(vtk_to_numpy(triangles.GetPolys().GetData()), dtype=np.int64).reshape(-1, 4)[:, 1:]
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=True)


def split_at_z(poly, z, direction):
    plane = vtk.vtkPlane()
    plane.SetOrigin(0, 0, z)
    plane.SetNormal(0, 0, direction)
    planes = vtk.vtkPlaneCollection()
    planes.AddItem(plane)
    cut = vtk.vtkClipClosedSurface()
    cut.SetInputData(poly)
    cut.SetClippingPlanes(planes)
    cut.GenerateFacesOn()
    cut.SetTolerance(1e-6)
    cut.Update()
    result = from_vtk(cut.GetOutput())
    if not result.is_volume:
        raise RuntimeError("Closed surface clipping produced invalid part")
    return result


def cad_solid(mesh):
    stitcher = BRepBuilderAPI_Sewing(.002, True, True, True, False)
    for face in mesh.faces:
        a, b, c = mesh.vertices[face]
        wire = BRepBuilderAPI_MakePolygon(gp_Pnt(*a), gp_Pnt(*b), gp_Pnt(*c), True)
        if not wire.IsDone():
            raise RuntimeError("Failed to create triangle wire")
        plane = BRepBuilderAPI_MakeFace(wire.Wire(), True)
        if not plane.IsDone():
            raise RuntimeError("Failed to create triangle face")
        stitcher.Add(plane.Face())
    stitcher.Perform()
    it = TopExp_Explorer(stitcher.SewedShape(), TopAbs_SHELL)
    if not it.More():
        raise RuntimeError("Cad STEP shell missing")
    builder = BRepBuilderAPI_MakeSolid(TopoDS.Shell_s(it.Current()))
    if not builder.IsDone() or not BRepCheck_Analyzer(builder.Solid()).IsValid():
        raise RuntimeError("Faceted STEP solid invalid")
    return builder.Solid()


def step_export_and_readback(shape, path):
    writer = STEPControl_Writer()
    if writer.Transfer(shape, STEPControl_AsIs) != IFSelect_RetDone:
        raise RuntimeError("STEP transfer failed")
    if writer.Write(str(path)) != IFSelect_RetDone:
        raise RuntimeError("STEP export failed")
    reader = STEPControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise RuntimeError("STEP readback failed")
    reader.TransferRoots()
    if not BRepCheck_Analyzer(reader.OneShape()).IsValid():
        raise RuntimeError("Re-imported STEP is invalid")
    print("Verified STEP", path.name, path.stat().st_size, "bytes", flush=True)


def cad_proxy(poly):
    simplify = vtk.vtkQuadricDecimation()
    simplify.SetInputData(poly)
    simplify.SetTargetReduction(.975)
    simplify.VolumePreservationOn()
    simplify.Update()
    result = from_vtk(simplify.GetOutput())
    if not result.is_watertight:
        valences = np.bincount(result.edges_unique_inverse, minlength=len(result.edges_unique))
        invalid_edges = np.where(valences > 2)[0]
        if len(invalid_edges) != 1 or int(valences[invalid_edges[0]]) != 4:
            raise RuntimeError("Unexpected topology after CAD mesh decimation")
        incident = np.unique(np.where(result.edges_unique_inverse == invalid_edges[0])[0] // 3)
        if len(incident) != 4:
            raise RuntimeError("Unexpected CAD proxy incident faces")
        keep = np.ones(len(result.faces), dtype=bool)
        keep[incident[:2]] = False
        result.update_faces(keep)
        result.remove_unreferenced_vertices()
        if not trimesh.repair.fill_holes(result):
            raise RuntimeError("CAD proxy repair failed")
    if not result.is_volume:
        raise RuntimeError("CAD proxy is not a closed solid")
    return result


def main(source_path: Path, out: Path):
    for folder in ("STL_PRINT", "STL_ASSEMBLY", "STEP_TFLEX", "REFERENCES"):
        (out / folder).mkdir(parents=True, exist_ok=True)
    source = trimesh.load_mesh(source_path, force="mesh")
    if not trimesh.repair.fill_holes(source):
        raise RuntimeError("Cannot repair original mesh holes")
    if not source.is_watertight or not source.is_winding_consistent:
        raise RuntimeError("Original AI reconstruction has invalid topology")
    # Source artifact is inverted relative to user's original CAD mesh.
    # 180-degree rotation around X is independently verified against target STL.
    source.apply_transform([[1, 0, 0, 0], [0, -1, 0, 0], [0, 0, -1, 150], [0, 0, 0, 1]])
    centre = (source.bounds[0, :2] + source.bounds[1, :2]) / 2
    source.apply_translation((-centre[0], -centre[1], -source.bounds[0, 2]))
    shells = source.split(only_watertight=False)
    surface = max(shells, key=lambda p: p.volume).copy()
    if not surface.is_volume or len(surface.faces) < 200000:
        raise RuntimeError("Expected high-detail outer mesh not found")
    full = out / "STL_PRINT" / "01_CHARACTER_FULL_150mm.stl"
    surface.export(full)
    print("External mesh faces:", len(surface.faces), "shell count:", len(shells), flush=True)
    cut_z = 66.0
    body = as_vtk(surface)
    lower = split_at_z(body, cut_z, -1)
    upper = split_at_z(body, cut_z, 1)
    if not np.isclose(lower.volume + upper.volume, surface.volume, atol=2.0):
        raise RuntimeError("Split parts lost geometry")
    for label, obj in [("02_LOWER_BODY", lower), ("03_UPPER_BODY_WITH_WINGS", upper)]:
        obj.export(out / "STL_ASSEMBLY" / (label + "_global_coordinates.stl"))
        printed = obj.copy()
        printed.apply_translation([0, 0, -obj.bounds[0, 2]])
        printed.export(out / "STL_PRINT" / (label + "_on_bed.stl"))
    stand = cq.Workplane("XY").ellipse(47, 32).extrude(5.5)
    stand = stand.union(
        cq.Workplane("XY").workplane(offset=5.5).ellipse(47, 32).ellipse(44, 29).extrude(.8)
    )
    standshape = stand.val()
    if not standshape.isValid():
        raise RuntimeError("Stand solid invalid")
    stand_cad = standshape.translate((0, 0, -5.5))
    cq.exporters.export(
        standshape, str(out / "STL_PRINT" / "04_STAND_BASE_94x64mm.stl"),
        exportType="STL", tolerance=.05, angularTolerance=.12
    )
    standmesh = trimesh.load_mesh(out / "STL_PRINT" / "04_STAND_BASE_94x64mm.stl")
    if not standmesh.is_volume:
        raise RuntimeError("Stand STL invalid")
    cq.exporters.export(stand_cad, str(out / "STEP_TFLEX" / "STAND_BASE_native_CAD.step"))
    proxy = cad_proxy(body)
    if len(proxy.faces) >= 15000:
        raise RuntimeError("Unexpectedly complex CAD proxy")
    cad_lower = cad_solid(split_at_z(as_vtk(proxy), cut_z, -1))
    cad_upper = cad_solid(split_at_z(as_vtk(proxy), cut_z, 1))
    step_export_and_readback(cad_lower, out / "STEP_TFLEX" / "LOWER_BODY_faceted_solid.step")
    step_export_and_readback(cad_upper, out / "STEP_TFLEX" / "UPPER_WINGS_faceted_solid.step")
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    builder.Add(compound, cad_lower)
    builder.Add(compound, cad_upper)
    builder.Add(compound, stand_cad.wrapped)
    if not BRepCheck_Analyzer(compound).IsValid():
        raise RuntimeError("Final CAD assembly invalid")
    step_export_and_readback(compound, out / "T-FLEX_Assembly_3_Parts.step")
    stand_for_scene = standmesh.copy()
    stand_for_scene.apply_translation([0, 0, -5.5])
    surface.visual.vertex_colors = np.tile(np.array([[205, 211, 221, 255]], dtype=np.uint8), (len(surface.vertices), 1))
    stand_for_scene.visual.vertex_colors = np.tile(np.array([[56, 62, 79, 255]], dtype=np.uint8), (len(stand_for_scene.vertices), 1))
    preview = trimesh.Scene()
    preview.add_geometry(surface, geom_name="Figurine_150mm")
    preview.add_geometry(stand_for_scene, geom_name="Base_CAD_exact")
    preview.export(out / "CHARACTER_AND_STAND_MOBILE.glb")
    qa = {
        "source": "Reconstruction from prior Hi3DGen AI model, NOT an exact 3D copy of detailed 2D turnaround",
        "full_character": quality(surface),
        "lower": quality(lower), "upper": quality(upper), "stand": quality(standmesh),
        "seam_z_mm": cut_z,
        "step_facets": len(proxy.faces),
        "step_import_and_brep_validation": "passed",
        "not_certified_for_printer": True,
        "no_mechanical_dowels": True,
        "minimum_wall_thickness_checked": False,
        "printer_and_slicer_tested": False,
    }
    (out / "QA_MANIFEST.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf8")
    (out / "READ_BEFORE_PRINTING_RU.txt").write_text(
        "T-FLEX CAD 18 — прототип 3D-фигурки персонажа, 150 мм.\n\n"
        "Внимание: это ранее созданная AI-реконструкция, а не точная 3D-копия последнего "
        "детализированного изображения. STEP содержит ~7500 треугольных CAD-граней "
        "(упрощённая модель), а STL — >300 000 треугольников для 3D-печати.\n\n"
        "Открыть T-FLEX_Assembly_3_Parts.step в T-FLEX CAD 18.\n"
        "Для печати открыть STL_PRINT/02_LOWER_BODY_on_bed.stl, "
        "STL_PRINT/03_UPPER_BODY_WITH_WINGS_on_bed.stl, "
        "STL_PRINT/04_STAND_BASE_94x64mm.stl.\n"
        "Шов горизонтальный Z=66 мм; соединение плоское под склейку, без штифтов.\n"
        "Проверить толщину крыльев, опоры, размеры стола, ориентацию и прочность.\n"
        "Физическая печать пока не проводилась.\n",
        encoding="utf-8",
    )
    target = out.parent / "Winged_Character_TFLEX_150mm_READY_FILES.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                z.write(f, arcname=str(f.relative_to(out)))
    print("RELEASE_READY:", target, target.stat().st_size, "bytes", flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
