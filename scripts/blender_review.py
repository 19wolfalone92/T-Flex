"""Blender headless four-view quality preview + mesh topology audit.

Call with: blender --background --python scripts/blender_review.py -- \
    --input /path/model.glb --output-dir /path/review
This script is only executed inside Blender (bpy required). No geometry edits.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def run() -> None:
    import bpy
    import bmesh
    from mathutils import Vector

    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=640)
    options = parser.parse_args(args)
    if not 128 <= options.resolution <= 2048:
        raise ValueError("resolution must be between 128 and 2048")
    path = options.input.resolve()
    if not path.is_file():
        raise ValueError("Input not found")
    out = options.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    ext = path.suffix.lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    elif ext == ".stl":
        bpy.ops.wm.stl_import(filepath=str(path))
    else:
        raise ValueError("Supported sources: GLB, GLTF, OBJ, STL")
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise ValueError("No mesh objects imported")

    sizes = []
    audit = []
    for obj in meshes:
        obj_m = obj.matrix_world.copy()
        for corner in obj.bound_box:
            sizes.append(obj_m @ Vector(corner))
        b = bmesh.new()
        try:
            b.from_mesh(obj.data)
            boundary = sum(1 for e in b.edges if e.is_boundary)
            non_manifold = sum(1 for e in b.edges if not e.is_manifold)
            degenerate = sum(1 for face in b.faces if face.calc_area() <= 1e-12)
            audit.append({
                "name": obj.name, "vertices": len(b.verts), "faces": len(b.faces),
                "boundary_edges": boundary, "non_manifold_edges": non_manifold,
                "degenerate_faces": degenerate,
            })
        finally:
            b.free()
    xs, ys, zs = [i.x for i in sizes], [i.y for i in sizes], [i.z for i in sizes]
    mini = Vector((min(xs), min(ys), min(zs)))
    maxi = Vector((max(xs), max(ys), max(zs)))
    center = (mini + maxi) / 2
    extent = maxi - mini
    scale = max(extent.x, extent.y, extent.z, 1e-6)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 16
    scene.render.resolution_x = options.resolution
    scene.render.resolution_y = options.resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    world = bpy.data.worlds.new("Neutral Studio")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes.get("Background").inputs["Color"].default_value = (0.7, 0.7, 0.7, 1)
    world.node_tree.nodes.get("Background").inputs["Strength"].default_value = 0.6

    def area_light(name, pos, power):
        lamp = bpy.data.lights.new(name, type="AREA")
        lamp.energy = power
        lamp.shape = "DISK"
        lamp.size = scale * 1.5
        light = bpy.data.objects.new(name, lamp)
        scene.collection.objects.link(light)
        light.location = center + Vector(pos) * scale
        light.rotation_euler = (center - light.location).to_track_quat("-Z", "Y").to_euler()

    area_light("Key", (-2, -3, 4), 400)
    area_light("Fill", (3, 0, 2), 220)
    area_light("Rim", (0, 3, 4), 350)
    camera_data = bpy.data.cameras.new("Turntable camera")
    camera = bpy.data.objects.new("Turntable camera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = scale * 1.45
    viewpoints = {
        "front": (0, -1, 0.13),
        "left": (-1, 0, 0.13),
        "back": (0, 1, 0.13),
        "right": (1, 0, 0.13),
    }
    for label, direction in viewpoints.items():
        camera.location = center + Vector(direction) * (scale * 3.0)
        camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = str(out / (label + ".png"))
        bpy.ops.render.render(write_still=True)

    summary = {
        "source": str(path), "mesh_count": len(meshes),
        "world_space_bounds": [list(mini), list(maxi)],
        "geometry": audit,
        "renders": [str(out / (name + ".png")) for name in viewpoints],
        "ready_for_print": False,
        "limitations": [
            "Rendering does not verify likeness, watertightness across separate objects, internal intersections or wall thickness",
            "Inspect Blender 3D Print Toolbox and slicer before physical production",
            "Synthetic views are not reliable evidence about hidden sides of real characters",
        ],
    }
    (out / "blender_review.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    run()
