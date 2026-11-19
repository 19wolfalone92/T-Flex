"""Geometry regressions for the V4 anatomical replacement hands."""
import pytest
import numpy as np
import trimesh

from tflex_figurines.anatomical_hands import sculpt_hand


@pytest.mark.parametrize("side",[-1,1])
def test_five_digit_hand_is_not_a_sphere(side):
    mesh=sculpt_hand(side)
    assert mesh.is_watertight
    assert mesh.is_winding_consistent
    assert 150 < mesh.volume < 300
    assert 12000 < len(mesh.faces) < 70000
    assert 12 < mesh.extents[2] < 16
    # Distinct finger and thumb silhouette extends below the sleeve cuff.
    assert mesh.bounds[0,2] < 43
    assert mesh.bounds[1,2] > 55
    assert len(mesh.split(only_watertight=False)) == 1
    centre_x=float(mesh.bounds[:,0].mean())
    assert centre_x * side > 20


def test_invalid_hand_options_rejected():
    with pytest.raises(ValueError):
        sculpt_hand(0)
    with pytest.raises(ValueError):
        sculpt_hand(1,voxel_mm=0.4)
