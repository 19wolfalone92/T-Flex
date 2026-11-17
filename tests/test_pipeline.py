"""End-to-end offline print-preflight pipeline tests."""
from pathlib import Path

import trimesh

from tflex_figurines.pipeline import prepare_figurine


def test_pipeline_cube_scales_and_produces_evidence(tmp_path: Path):
    source = tmp_path / "cube.stl"
    trimesh.creation.box(extents=(1, 2, 3)).export(source)
    result = prepare_figurine(source, tmp_path / "build", 120, "z")
    assert result["status"] == "GEOMETRY_REVIEW_PASSED_MANUAL_PRINT_QA_PENDING"
    assert result["verified_print_ready"] is False
    assert (tmp_path / "build" / "exports" / "cube.stl").exists()
    assert (tmp_path / "build" / "evidence" / "source_mesh_audit.json").exists()
    assert (tmp_path / "build" / "evidence" / "prepared_mesh_audit.json").exists()
    assert (tmp_path / "build" / "manifest.json").exists()


def test_pipeline_blocks_nonwatertight_input(tmp_path: Path):
    f = tmp_path / "triangle.obj"
    trimesh.Trimesh(vertices=[[0, 0, 0], [1, 0, 0], [0, 1, 1]],
                    faces=[[0, 1, 2]], process=False).export(f)
    output = tmp_path / "build"
    result = prepare_figurine(f, output, 100)
    assert result["status"] == "BLOCKED_PENDING_MESH_REPAIR"
    assert not (output / "exports" / "triangle.stl").exists()
    assert (output / "manifest.json").exists()
