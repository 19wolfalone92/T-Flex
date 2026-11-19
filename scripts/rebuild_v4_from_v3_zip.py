"""V4 release: audited continuation of V3 with real five-digit hands.

Uses an existing legitimately downloadable V3 ZIP from the same repo. Preserves
all other printable meshes byte-for-byte. Rebuilds BOTH hand STL/STEP files,
mobile GLB, full T-FLEX assembly STEP and SHA-256 checksums. No paid AI calls.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

import cadquery as cq
import numpy as np
import trimesh
from OCP.BRep import BRep_Builder
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader, STEPControl_AsIs, STEPControl_Writer
from OCP.TopoDS import TopoDS_Compound

from tflex_figurines.anatomical_hands import sculpt_hand
from scripts.figurine_release_builder import as_vtk, cad_proxy, cad_solid


COLOURS = {
    "01": (16, 20, 28), "02": (16, 20, 28),
    "03": (16, 20, 28), "04": (16, 20, 28),
    "05": (118, 163, 226), "06": (118, 163, 226),
    "07": (234, 238, 243), "08": (240, 184, 162),
    "09": (240, 184, 162), "10": (216, 220, 232),
    "11": (22, 124, 230), "12": (22, 124, 230),
    "13": (211, 34, 54), "14": (18, 22, 30),
}
HAND_NAMES = {
    "08": "08_LEFT_VISIBLE_HAND_SKIN",
    "09": "09_RIGHT_VISIBLE_HAND_SKIN",
}


def step_read(path: Path):
    reader = STEPControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone or reader.TransferRoots() <= 0:
        raise ValueError("Cannot read STEP geometry: " + path.name)
    shape = reader.OneShape()
    if not BRepCheck_Analyzer(shape).IsValid():
        raise ValueError("Part STEP invalid: " + path.name)
    return shape


def step_write(shape, path: Path):
    writer = STEPControl_Writer()
    if writer.Transfer(shape, STEPControl_AsIs) != IFSelect_RetDone:
        raise ValueError("STEP conversion failed")
    if writer.Write(str(path)) != IFSelect_RetDone:
        raise ValueError("STEP writing failed")
    step_read(path)


def main(source_zip: Path, directory: Path) -> Path:
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Output directory must be new and empty")
    directory.mkdir(parents=True, exist_ok=True)
    kit = directory / "kit"
    kit.mkdir()
    with zipfile.ZipFile(source_zip) as archive:
        if archive.testzip():
            raise ValueError("Corrupt V3 ZIP")
        # Never extract arbitrary paths from a ZIP: pinned release layout only.
        for entry in archive.infolist():
            path = Path(entry.filename)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Unsafe archive entry")
        archive.extractall(kit)
    manifest_path = kit / "QA_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("version") != "3.0" or len(manifest["parts"]) != 14 or len(manifest["joints"]) != 8:
        raise ValueError("Input is not expected V3 colour-split release")

    for code, name in HAND_NAMES.items():
        mesh = sculpt_hand(-1 if code == "08" else 1)
        # Both copies need independently verifiable manifold surfaces.
        for output in [
            kit / "STL_ASSEMBLY" / (name + ".stl"),
            kit / "STL_PRINT" / "INDIVIDUAL_SOLIDS" / (name + "_shell_01.stl"),
        ]:
            mesh.export(output)
        on_bed = mesh.copy()
        on_bed.apply_translation([0, 0, -float(on_bed.bounds[0, 2])])
        on_bed.export(kit / "STL_PRINT" / (name + "_on_bed.stl"))
        # The faceted STEP proxy simplifies curved surfaces, the print STL
        # preserves all >=29k sculpting triangles.
        reduced = cad_proxy(as_vtk(mesh))
        cad = cad_solid(reduced)
        step_path = kit / "STEP_TFLEX" / (name + "_FACETED_SOCKETS.step")
        step_write(cad, step_path)
        manifest["parts"][name] = {
            "triangles": len(mesh.faces),
            "closed": bool(mesh.is_watertight),
            "normals_consistent": bool(mesh.is_winding_consistent),
            "volume_mm3": round(float(mesh.volume), 3),
            "digit_count": 5,
            "revision": "anatomical fingers / tapered palm / separate thumb",
        }
        print("Verified V4 hand",name,len(mesh.faces),mesh.volume,flush=True)

    # Rebuild a fresh coloured assembly scene and discard the obsolete V3 GLB.
    old = kit / "COLOUR_FIGURINE_V3_WITH_PIN_SOCKETS_MOBILE.glb"
    if old.exists():
        old.unlink()
    scene = trimesh.Scene()
    for stl in sorted((kit / "STL_ASSEMBLY").glob("*.stl")):
        mesh = trimesh.load_mesh(stl,force="mesh")
        code = stl.name[:2]
        if not (mesh.is_watertight and mesh.is_winding_consistent and mesh.volume > 0):
            raise ValueError("Broken V4 colour part "+stl.name)
        rgba = np.array([*COLOURS[code],255],dtype=np.uint8)
        mesh.visual.vertex_colors = np.tile(rgba, (len(mesh.vertices), 1))
        scene.add_geometry(mesh, geom_name=stl.stem)
    scene.export(str(kit / "COLOUR_FIGURINE_V4_ANATOMICAL_HANDS_MOBILE.glb"))

    # Rebuild complete T-FLEX compound with revised hands and the SAME pin
    # coordinates as original STL sockets (no mismatched drawing dimensions).
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for path in sorted((kit / "STEP_TFLEX").glob("*.step")):
        builder.Add(compound, step_read(path))
    for joint in manifest["joints"]:
        centre = list(map(float,joint["centre_mm"]))
        axis = int(joint["axis"])
        length = float(joint["pin_length_mm"])
        radius = float(joint["pin_diameter_mm"])/2
        centre[axis] -= length/2
        normal = [0, 0, 0]
        normal[axis] = 1
        peg = cq.Solid.makeCylinder(
            radius, length, cq.Vector(*centre), cq.Vector(*normal)
        )
        builder.Add(compound,peg.wrapped)
    if not BRepCheck_Analyzer(compound).IsValid():
        raise ValueError("Final CAD compound failed BRep validation")
    old_step = kit / "T-FLEX_18_V3_COLOUR_PARTS_WITH_HOLES.step"
    if old_step.exists():
        old_step.unlink()
    new_step = kit / "T-FLEX_18_V4_ANATOMICAL_HANDS_STEP_ASSEMBLY.step"
    step_write(compound, new_step)

    manifest["version"] = "4.0"
    manifest["v4_finger_sculpting"] = True
    manifest["hands_replaced"] = ["08", "09"]
    manifest["full_sleeves_unchanged_from_v3"] = True
    manifest["wing_geometry_unchanged_from_v3"] = True
    manifest["joinery_unchanged_from_v3"] = True
    manifest["hands_attach_inside_cuffs_with_glue_not_pins"] = True
    manifest["minimum_finger_diameter_mm_before_slicing"] = 1.56
    manifest["print_ready_certified"] = False
    manifest["critical_fidelity_limitations"] = [
        "Existing head, mask and hair are not separated into their actual original colour regions",
        "Original source is a stylized AI reconstruction, not exact original game geometry",
        "Fingers require printer-specific support and strength verification",
        "Hand-to-sleeve glued joints need a physical dry-fit; not a keyed pin",
        "Wing pin rotation and load strength have not been measured",
    ]
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    (kit / "V4_ПРОЧИТАТЬ_ПЕРЕД_ПЕЧАТЬЮ.txt").write_text(
        "V4: обе кисти переработаны — ладонь, 4 пальца и отдельный большой палец. "
        "Оба длинных рукава и крылья сохранены без изменений от версии V3.\\n"
        "14 цветовых сегментов, 8 штифтов с парными отверстиями (V3), "
        "калибровочные образцы.\\n"
        "Кисти соединяются под манжетами на клей, НЕ штифтами. "
        "Пробную печать пальцев выполнить до печати всей фигурки.\\n"
        "Цвет волос и маски ещё не разделён достоверно; внешний вид не "
        "тождествен игровому персонажу. Это не сертифицированный файл для печати.\\n"
        "Перед изготовлением проверить толщины, опоры, размер стола, "
        "посадку штифтов и прочность крыльев в слайсере и на принтере.\\n",
        encoding="utf-8",
    )

    # Integrity checks: keep an independent sha256 manifest in the release.
    hashes = {}
    for f in sorted(kit.rglob("*")):
        if f.is_file():
            hashes[str(f.relative_to(kit))] = hashlib.sha256(f.read_bytes()).hexdigest()
    (directory / "SHA256.json").write_text(json.dumps(hashes,indent=2),encoding="utf-8")
    archive_path = directory / "Winged_Character_V4_HighDetail_Hands_STL_STEP.zip"
    with zipfile.ZipFile(archive_path,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        for file in sorted(kit.rglob("*")):
            if file.is_file():
                z.write(file,arcname=str(file.relative_to(kit)))
        z.write(directory/"SHA256.json",arcname="SHA256.json")
    with zipfile.ZipFile(archive_path) as z:
        if z.testzip():
            raise ValueError("Generated V4 ZIP failed CRC")
    print("V4_RELEASE_READY", archive_path, archive_path.stat().st_size,flush=True)
    return archive_path


if __name__ == "__main__":
    main(Path(sys.argv[1]),Path(sys.argv[2]))
