from pathlib import Path

import numpy as np
import pytest
import trimesh

from tflex_figurines.cli import inspect, load_geometry, main, oriented_scaled_mesh, prepare


def test_closed_cube_120_mm(tmp_path: Path):
    source = tmp_path / "cube.stl"
    trimesh.creation.box(extents=(1, 2, 3)).export(source)
    report = prepare(source, tmp_path / "out", height_mm=120)
    assert report["analysis"]["print_ready"]
    assert report["status"] == "READY_FOR_MANUAL_REVIEW"
    output = load_geometry(tmp_path / "out" / "cube.stl")
    assert np.isclose(output.extents[2], 120)
    assert np.isclose(output.bounds[0, 2], 0)
    assert (tmp_path / "out" / "cube.obj").exists()
    assert (tmp_path / "out" / "cube.report.json").exists()


def test_y_up_is_rotated_to_z_up():
    source = trimesh.creation.box(extents=(1, 2, 3))
    output = oriented_scaled_mesh(source, height_mm=100, up_axis="y")
    assert np.isclose(output.extents[2], 100)
    assert np.isclose(output.bounds[0, 2], 0)


def test_open_mesh_fails_closed_preflight(tmp_path: Path):
    mesh = trimesh.Trimesh(vertices=[[0, 0, 0], [1, 0, 0], [0, 1, 1]], faces=[[0, 1, 2]], process=False)
    source = tmp_path / "triangle.obj"
    mesh.export(source)
    output_dir = tmp_path / "out"
    with pytest.raises(ValueError, match="preflight"):
        prepare(source, output_dir, height_mm=100)
    assert (output_dir / "triangle.report.json").exists()
    assert not (output_dir / "triangle.stl").exists()
    report = prepare(source, output_dir, height_mm=100, allow_open=True)
    assert report["status"] == "EXPORTED_WITH_WARNINGS_NOT_PRINT_READY"


def test_invalid_height_and_missing_file(tmp_path: Path):
    source = tmp_path / "cube.stl"
    trimesh.creation.box().export(source)
    with pytest.raises(ValueError, match="positive"):
        prepare(source, tmp_path / "out", height_mm=-2)
    assert main(["inspect", str(tmp_path / "missing.glb")]) == 2


def test_scene_transform_is_applied(tmp_path: Path):
    scene = trimesh.Scene()
    scene.add_geometry(trimesh.creation.box(), transform=trimesh.transformations.translation_matrix([4, 0, 0]))
    path = tmp_path / "scene.glb"
    scene.export(path)
    result = inspect(path)
    assert result["analysis"]["vertices"] > 0
    assert result["analysis"]["bounds"][0][0] > 3.4
