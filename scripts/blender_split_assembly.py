"""Cut one watertight mm-sized figurine into TWO keyed FDM-printable halves.

Blender 4.x, geometry only. Generates an assembly-aligned pair, individual
bed-oriented STLs, two *separate* dowel STLs, a tolerance test coupon and BOM.
All "ready" claims are withheld pending real printer/slicer checks.
Use *prepared* mm STL from tflex-pipeline, not arbitrary unitless AI GLB.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path


def run():
    import bpy
    import bmesh
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--cut-ratio", type=float, default=0.50)
    p.add_argument("--pin-diameter-mm", type=float, default=3.0)
    p.add_argument("--radial-clearance-mm", type=float, default=0.20)
    p.add_argument("--hole-depth-mm", type=float, default=5.5)
    args = p.parse_args(argv)
    if not 0.15 <= args.cut_ratio <= 0.85:
        raise ValueError("cut-ratio must be 0.15..0.85")
    if not 2 <= args.pin_diameter_mm <= 8:
        raise ValueError("pin diameter must be 2..8 mm")
    if not 0.05 <= args.radial_clearance_mm <= 0.60:
        raise ValueError("clearance must be 0.05..0.60 mm per side")
    if not 3 <= args.hole_depth_mm <= 15:
        raise ValueError("hole depth must be 3..15 mm")
    source = args.input.resolve()
    if not source.is_file() or source.suffix.lower() != ".stl":
        raise ValueError("Please provide a prepared STL with mm coordinates from tflex-pipeline")
    out = args.output_dir.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("Output directory must be empty; no overwrite of previous results")
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.wm.stl_import(filepath=str(source))
    obj = next((o for o in bpy.context.scene.objects if o.type == "MESH"), None)
    if obj is None:
        raise ValueError("STL did not contain mesh")
    obj.name = "Original unchanged source"
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    # Blender's STL importer can share mesh datablocks with other imported objects;
    # transform_apply refuses to mutate multi-user data. Detach first.
    if obj.data.users > 1:
        obj.data = obj.data.copy()
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    original = bmesh.new()
    original.from_mesh(obj.data)
    original.normal_update()
    try:
        if any(not e.is_manifold for e in original.edges):
            raise ValueError("Source STL is not manifold; repair before splitting")
        if abs(original.calc_volume(signed=True)) < 1e-5:
            raise ValueError("Source mesh has no enclosed solid volume")
        bvh = BVHTree.FromBMesh(original)
    finally:
        original.free()
    vertices = [obj.matrix_world @ v.co for v in obj.data.vertices]
    x_min, x_max = min(v.x for v in vertices), max(v.x for v in vertices)
    y_min, y_max = min(v.y for v in vertices), max(v.y for v in vertices)
    z_min, z_max = min(v.z for v in vertices), max(v.z for v in vertices)
    height = z_max - z_min
    if not 20 <= height <= 1000:
        raise ValueError("Prepared source must be 20..1000 mm tall")
    cut = z_min + height * args.cut_ratio
    depth = args.hole_depth_mm
    if min(cut-z_min, z_max-cut) < depth * 2:
        raise ValueError("Part halves too thin for requested pin sockets")
    cx, cy = (x_min+x_max)/2, (y_min+y_max)/2
    min_side = min(x_max-x_min, y_max-y_min)
    pin_radius = args.pin_diameter_mm / 2
    socket_radius = pin_radius + args.radial_clearance_mm
    material_margin = 0.8
    if min_side < 4 * (socket_radius + material_margin):
        raise ValueError("Cut cross-section too narrow for two alignment dowels")

    def inside(x, y, z):
        # Count upward crossings below the query point, not nearest-face distance.
        # bvh is frozen from the untouched original mesh.
        origin = Vector((x, y, z_min - max(5., height*0.1)))
        direction = Vector((0., 0., 1.))
        hits = 0
        for _ in range(512):
            hit, normal, index, dist = bvh.ray_cast(origin, direction, height*2+100)
            if hit is None or hit.z > z - 0.002:
                break
            hits += 1
            origin = hit + direction * 0.008
        return hits % 2 == 1

    def safe_location(x, y):
        # Check a full ring of solid material around blind bores on both sides.
        for offset in (-depth*0.92, -depth*0.45, depth*0.45, depth*0.92):
            for n in range(16):
                angle = math.tau * n / 16
                r = socket_radius + material_margin
                if not inside(x+r*math.cos(angle), y+r*math.sin(angle), cut+offset):
                    return False
        return inside(x, y, cut-0.1) and inside(x, y, cut+0.1)

    # Search candidate pairs in the actual center section, never blindly drill
    # through the character outline. Both dowels must fit in a solid volume.
    points = []
    for i in range(1, 9):
        separation = min_side * (0.05 + i*0.028)
        candidates = [(cx-separation, cy), (cx+separation, cy)]
        if all(safe_location(x, y) for x, y in candidates):
            if 2*separation >= 2*(socket_radius + material_margin)+1.:
                points = candidates
                break
    if len(points) != 2:
        raise ValueError("No safe pair of pin locations at this cut. Change ratio or select a larger cross section.")

    # Do not reuse the same operator selection or modifiers across parts.
    def bool_modifier(part, cutter, operation):
        bpy.ops.object.select_all(action="DESELECT")
        part.select_set(True)
        bpy.context.view_layer.objects.active = part
        mod = part.modifiers.new("Precision_boolean", "BOOLEAN")
        mod.operation = operation
        mod.solver = "EXACT"
        mod.object = cutter
        bpy.ops.object.modifier_apply(modifier=mod.name)

    def cube(zlo, zhi):
        bpy.ops.mesh.primitive_cube_add(size=2, location=(cx, cy, (zlo+zhi)/2))
        shape = bpy.context.object
        shape.scale = (
            max(x_max-x_min, 1.) * 2 + 10,
            max(y_max-y_min, 1.) * 2 + 10,
            (zhi-zlo)/2,
        )
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        return shape

    def duplicate(name):
        copy = obj.copy()
        copy.data = obj.data.copy()
        bpy.context.collection.objects.link(copy)
        copy.name = name
        return copy

    lower, upper = duplicate("lower"), duplicate("upper")
    for part, lo, hi in ((lower, z_min-5., cut), (upper, cut, z_max+5.)):
        cutter = cube(lo, hi)
        bool_modifier(part, cutter, "INTERSECT")
        bpy.data.objects.remove(cutter, do_unlink=True)

    for index, (x, y) in enumerate(points):
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=64, radius=socket_radius, depth=depth*2,
            location=(x, y, cut))
        drill = bpy.context.object
        drill.name = f"TemporarySocket_{index}"
        for part in (lower, upper):
            bool_modifier(part, drill, "DIFFERENCE")
        bpy.data.objects.remove(drill, do_unlink=True)

    def audit(part):
        mesh = bmesh.new()
        mesh.from_mesh(part.data)
        mesh.normal_update()
        try:
            boundaries = sum(1 for e in mesh.edges if not e.is_manifold)
            volume = abs(mesh.calc_volume(signed=True))
            if boundaries or volume <= 0.01:
                raise ValueError(f"Boolean generated broken mesh: {part.name} boundary_edges={boundaries}")
            return {"faces": len(mesh.faces), "volume_mm3": round(volume, 2),
                    "nonmanifold_edges": boundaries}
        finally:
            mesh.free()

    original_stats = {"faces": len(obj.data.polygons), "source_height_mm": round(height, 3)}
    lower_stats, upper_stats = audit(lower), audit(upper)

    def export(part, target, min_bed=False):
        bpy.ops.object.select_all(action="DESELECT")
        part.select_set(True)
        bpy.context.view_layer.objects.active = part
        if min_bed:
            # Separate copies: keep original CAD assembly positions untouched.
            part_copy = part.copy()
            part_copy.data = part.data.copy()
            bpy.context.collection.objects.link(part_copy)
            part_copy.location.z -= min((part.matrix_world @ Vector(v.co)).z for v in part.data.vertices)
            bpy.ops.object.select_all(action="DESELECT")
            part_copy.select_set(True)
            bpy.context.view_layer.objects.active = part_copy
        else:
            part_copy = None
        target.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.stl_export(filepath=str(target), export_selected_objects=True, apply_modifiers=True)
        if part_copy:
            bpy.data.objects.remove(part_copy, do_unlink=True)

    for part, label in ((lower, "lower"), (upper, "upper")):
        export(part, out / "assembly" / (label + ".stl"))
        export(part, out / "print" / (label + ".stl"), min_bed=True)

    pin_length = depth*2 - 0.35  # leaves 0.175 mm axial play in each blind end
    for i, (x, y) in enumerate(points, 1):
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=64, radius=pin_radius, depth=pin_length, location=(x, y, cut))
        dowel = bpy.context.object
        dowel.name = f"alignment_pin_{i}"
        audit(dowel)
        export(dowel, out / "assembly" / f"pin_{i}.stl")
        export(dowel, out / "print" / f"pin_{i}.stl", min_bed=True)

    # Save a tiny *separate* tolerance coupon to test BEFORE printing a figurine.
    # This uses the same pin and socket dimensions as the actual assembly.
    # Every print line must be confirmed using the user's own slicer and filament.
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, depth))
    block = bpy.context.object
    block.name = "tolerance_block"
    block.scale = (pin_radius + 3., pin_radius + 3., depth)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=64, radius=socket_radius, depth=depth+1,
        location=(0, 0, depth*1.5))
    drill = bpy.context.object
    bool_modifier(block, drill, "DIFFERENCE")
    bpy.data.objects.remove(drill, do_unlink=True)
    audit(block)
    export(block, out / "print" / "test_socket.stl", min_bed=True)

    with (out / "parts.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["piece", "quantity", "source", "notes"])
        writer.writerows([
            ["lower", 1, "print/lower.stl", "lower body, print on original base"],
            ["upper", 1, "print/upper.stl", "upper body, cut face down"],
            ["pin", 2, "print/pin_1.stl;print/pin_2.stl", "dry fit before adhesive"],
            ["test_socket", 1, "print/test_socket.stl", "first check tolerance and adjust if needed"],
        ])

    report = {
        "schema_version": 1,
        "input": str(source),
        "tflex_cad_target": "T-FLEX CAD 18 (mesh import, not parametric solid)",
        "printing_assumption": "single-extruder FDM; validate exact filament and printer",
        "cut_z_in_original_mm": round(cut, 4),
        "cut_ratio": args.cut_ratio,
        "dowels_xy_mm": [[round(x, 3), round(y, 3)] for x, y in points],
        "pin_diameter_mm": args.pin_diameter_mm,
        "hole_diameter_mm": round(2*socket_radius, 3),
        "radial_clearance_mm_per_side": args.radial_clearance_mm,
        "hole_depth_mm_per_half": depth,
        "pin_length_mm": pin_length,
        "source": original_stats, "lower": lower_stats, "upper": upper_stats,
        "exports": {
            "assembly": ["assembly/lower.stl", "assembly/upper.stl",
                         "assembly/pin_1.stl", "assembly/pin_2.stl"],
            "print": ["print/lower.stl", "print/upper.stl",
                      "print/pin_1.stl", "print/pin_2.stl", "print/test_socket.stl"],
        },
        "print_ready_certified": False,
        "human_review": [
            "Check seam location away from face/fragile details",
            "Print and measure tolerance coupon with actual nozzle and filament",
            "Inspect every STL in slicer for unsupported overhangs and weak walls",
            "Dry fit both pins and halves before gluing",
            "Confirm printer build-volume fit, part orientation and T-FLEX mm import",
            "Sand seam, assemble with suitable material-compatible glue, prime/paint",
        ],
    }
    (out / "assembly.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SPLIT_OK " + str(out / "assembly.json"))


if __name__ == "__main__":
    run()
