import numpy as np
import pytest

from filtervisual.config.schema import GeometryConfig
from filtervisual.scene.geometry import armor_positions, armor_yaws


def test_four_plate_geometry():
    geometry = GeometryConfig(
        radius_a=0.4, radius_b=0.2, height_a=0.1,
        height_diff=0.15, reference_id=0,
    )
    actual = armor_positions(np.array([1.0, 2.0]), geometry, 0.0)
    np.testing.assert_allclose(actual, [
        [1.4, 2.0, 0.1], [1.0, 2.2, 0.25],
        [0.6, 2.0, 0.1], [1.0, 1.8, 0.25],
    ], atol=1e-12)


def test_reference_change_preserves_plate_identity_and_pose():
    geometry = GeometryConfig(
        radius_a=0.4, radius_b=0.2, height_a=0.1,
        height_diff=-0.05, reference_id=0,
    )
    changed = geometry.model_copy(update={"reference_id": 1})
    center = np.array([-0.2, 1.1])
    yaw = 0.7
    np.testing.assert_allclose(
        armor_positions(center, geometry, yaw),
        armor_positions(center, changed, yaw + np.pi / 2), atol=1e-12,
    )
    np.testing.assert_allclose(
        armor_yaws(geometry, yaw),
        armor_yaws(changed, yaw + np.pi / 2), atol=1e-12,
    )


def test_armor_yaws_remain_continuous_across_pi():
    geometry = GeometryConfig()
    before = armor_yaws(geometry, np.pi - 0.01)
    after = armor_yaws(geometry, np.pi + 0.01)
    np.testing.assert_allclose(after - before, np.full(4, 0.02), atol=1e-12)


@pytest.mark.parametrize("center,yaw", [([0.0], 0.0), ([0.0, np.nan], 0.0), ([0.0, 0.0], np.inf)])
def test_nonphysical_geometry_input_is_rejected(center, yaw):
    with pytest.raises(ValueError):
        armor_positions(np.asarray(center), GeometryConfig(), yaw)
