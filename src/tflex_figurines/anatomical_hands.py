"""Anatomical chibi hands to replace the V3 sphere placeholders.

This module produces two closed high-detail STL surfaces. It does not alter,
cut off or deform the existing full sleeves or wings. Physical FDM suitability
is a separate printer-specific acceptance step.
"""
from __future__ import annotations

import numpy as np
import trimesh
from skimage.measure import marching_cubes


def ellipsoid(points: np.ndarray, center, radii) -> np.ndarray:
    center = np.asarray(center, dtype=np.float32)
    radii = np.asarray(radii, dtype=np.float32)
    return (np.sqrt(np.sum(((points - center) / radii) ** 2, axis=-1)) - 1) * float(min(radii))


def capsule(points: np.ndarray, start, end, radius: float) -> np.ndarray:
    start = np.asarray(start, dtype=np.float32)
    end = np.asarray(end, dtype=np.float32)
    direction = end - start
    t = np.clip(np.sum((points - start) * direction, axis=-1) / float(direction @ direction), 0, 1)
    return np.sqrt(np.sum((points - start - t[..., None] * direction) ** 2, axis=-1)) - radius


def join_smooth(distance_a, distance_b, width: float):
    t = np.clip(0.5 + 0.5 * (distance_b - distance_a) / width, 0, 1)
    return distance_b * (1 - t) + distance_a * t - width * t * (1 - t)


def sculpt_hand(side: int, *, voxel_mm: float = 0.15) -> trimesh.Trimesh:
    """Construct one 5-digit hand under the extant full-length sleeve.

    Side -1 is the character's left, side +1 character's right.
    All dimensions are for an existing 150-mm figurine, not universal.
    """
    if side not in (-1, 1):
        raise ValueError("side must be -1 or +1")
    if not 0.08 <= voxel_mm <= 0.25:
        raise ValueError("voxel_mm must be 0.08..0.25")
    cx, cy, cz = side * 25.585, -3.45, 50.14
    dx = np.arange(-6.6, 6.61, voxel_mm, dtype=np.float32)
    dy = np.arange(-5.3, 5.31, voxel_mm, dtype=np.float32)
    dz = np.arange(-9.1, 5.71, voxel_mm, dtype=np.float32)
    x, y, z = np.meshgrid(dx, dy, dz, indexing="ij")
    xyz = np.stack((x, y, z), axis=-1)
    distance = ellipsoid(xyz, (0, 0, 0.65), (3.38, 2.62, 3.0))
    # Wrist connects invisibly up inside the oversized game costume cuff.
    distance = join_smooth(distance, ellipsoid(xyz, (0, 0, 3.5), (2.25, 2.15, 2.0)), 0.65)
    distance = join_smooth(distance, ellipsoid(xyz, (0, 0, -1.3), (3.20, 2.43, 2.22)), 0.42)
    # Four independently sculpted visible fingertips. Diameter >= 1.5 mm.
    fingers = (
        (-2.25, -2.3, -6.55, 0.78),
        (-0.77, -2.45, -7.35, 0.78),
        (+0.74, -2.32, -7.18, 0.78),
        (+2.25, -2.27, -6.18, 0.80),
    )
    for x_position, start_z, end_z, diameter_radius in fingers:
        d = capsule(
            xyz,
            (x_position, 0, start_z),
            (x_position + (-0.10 if x_position > 0 else +0.10), -0.12, end_z),
            diameter_radius,
        )
        distance = join_smooth(distance, d, 0.35)
    # One additional thumb angled towards torso, with printable strength.
    thumb = capsule(xyz, (-3.0 * side, -0.35, -1.3),
                    (-4.3 * side, -0.65, -3.65), 1.06)
    distance = join_smooth(distance, thumb, 0.50)
    vertices, faces, _, _ = marching_cubes(
        distance, level=0, spacing=(voxel_mm,) * 3, allow_degenerate=False
    )
    vertices += np.array([dx[0] + cx, dy[0] + cy, dz[0] + cz])
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    mesh.fix_normals()
    if not (mesh.is_watertight and mesh.is_winding_consistent and mesh.volume > 100):
        raise ValueError("Detailed hand sculpture failed solid topology check")
    if not 12 < mesh.extents[2] < 16 or len(mesh.faces) < 10000:
        raise ValueError("Unexpected anatomical hand size/detail")
    return mesh
