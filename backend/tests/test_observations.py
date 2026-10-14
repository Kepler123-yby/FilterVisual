import numpy as np
import pytest

from filtervisual.config.schema import GeometryConfig, ObservationConfig, RotationConfig, SceneConfig, SineTerm, TranslationConfig
from filtervisual.scene.geometry import armor_yaws
from filtervisual.scene.motion import build_truth
from filtervisual.scene.observations import generate_observations, observation_covariance, select_plate_ids


def scene(duration=1):
    return SceneConfig(
        duration_s=duration, simulation_dt=.025,
        translation=TranslationConfig(mode="constant", velocity_xy=[0, 0]),
        rotation=RotationConfig(mode="angular_velocity", terms=[SineTerm(amplitude=0, frequency_rad_s=0, offset=2)]),
    )


def noiseless(**kwargs):
    return ObservationConfig(std_xyz=0, std_yaw=0, **kwargs)


def test_all_plate_joint_frame_is_sorted_and_uses_fixed_id_yaw():
    truth = build_truth(scene(), 42)
    frames = generate_observations(truth, noiseless(mode="all", frequency_hz=37), 42)
    assert len(frames) == 38
    for frame in frames:
        assert frame.context.plate_ids == (0, 1, 2, 3)
        assert frame.context.angular_indices == (3, 7, 11, 15)
        assert frame.context.time_s == frame.t
        state = truth.sample(frame.t)
        values = frame.values.reshape(4, 4)
        np.testing.assert_allclose(values[:, :3], state.armor_positions, atol=1e-12)
        yaw_error = (values[:, 3] - armor_yaws(truth.scene.geometry, state.reference_yaw) + np.pi) % (2 * np.pi) - np.pi
        np.testing.assert_allclose(yaw_error, 0, atol=1e-12)


def test_plate_visibility_switch_preserves_reference_and_id():
    truth = build_truth(scene(3.4), 42)
    frames = generate_observations(truth, noiseless(mode="nearest_visible", frequency_hz=20), 42)
    assert frames[0].context.plate_ids == (2,)
    assert {frame.context.plate_ids[0] for frame in frames} == {0, 1, 2, 3}
    for frame in frames:
        plate = frame.context.plate_ids[0]
        state = truth.sample(frame.t)
        np.testing.assert_allclose(frame.values[:3], state.armor_positions[plate], atol=1e-12)
        expected = armor_yaws(truth.scene.geometry, state.reference_yaw)[plate]
        assert ((frame.values[3] - expected + np.pi) % (2 * np.pi) - np.pi) == pytest.approx(0, abs=1e-12)


def test_nearest_visible_ties_choose_smaller_id_and_interior_has_no_front_plate():
    g = GeometryConfig(radius_a=.25, radius_b=.25, height_a=.2, height_diff=0)
    truth_scene = scene()
    truth_scene.geometry = g
    truth = build_truth(truth_scene, 42)
    state = truth.sample(0)
    yaws = armor_yaws(g, 0)
    config = noiseless(mode="nearest_visible", viewpoint_xyz=[-3, -3, .2])
    assert select_plate_ids(state.armor_positions, yaws, config) == (2,)
    config.viewpoint_xyz = [0, 0, .2]
    assert select_plate_ids(state.armor_positions, yaws, config) == ()
    assert generate_observations(truth, config, 42) == []


def test_specified_board_can_be_geometrically_invisible():
    truth = build_truth(scene(), 42)
    frames = generate_observations(truth, noiseless(mode="fixed", plate_id=0), 42)
    assert frames[0].context.plate_ids == (0,)
    np.testing.assert_allclose(frames[0].values[:3], truth.sample(0).armor_positions[0])


def test_same_seed_observations_are_identical_and_do_not_change_truth():
    truth = build_truth(scene(), 42)
    before = truth.sample(.33).center_xy.copy()
    config = ObservationConfig(mode="all", dropout_probability=.1, outlier_probability=.2)
    a, b = generate_observations(truth, config, 42), generate_observations(truth, config, 42)
    assert [frame.id for frame in a] == [frame.id for frame in b]
    for first, second in zip(a, b):
        np.testing.assert_array_equal(first.values, second.values)
    np.testing.assert_array_equal(before, truth.sample(.33).center_xy)
    different = generate_observations(truth, config, 43)
    assert a[0].values[0] != different[0].values[0]


def test_dropout_does_not_redraw_surviving_noise():
    truth = build_truth(scene(), 42)
    base = ObservationConfig(mode="fixed")
    full = {frame.id: frame for frame in generate_observations(truth, base, 42)}
    base.dropout_probability = .4
    dropped = generate_observations(truth, base, 42)
    assert 0 < len(dropped) < len(full)
    for frame in dropped:
        np.testing.assert_array_equal(frame.values, full[frame.id].values)
    base.dropout_probability = 1
    assert generate_observations(truth, base, 42) == []


def test_full_covariance_subset_and_correlated_gaussian_noise():
    covariance = np.diag(np.tile([1e-4, 4e-4, 1e-4, 4e-4], 4))
    covariance[0, 4] = covariance[4, 0] = 8e-5
    config = ObservationConfig(mode="all", frequency_hz=1000, covariance=covariance.tolist())
    np.testing.assert_array_equal(observation_covariance(config, (1,)), covariance[4:8, 4:8])
    truth = build_truth(scene(5), 42)
    frames = generate_observations(truth, config, 42)
    noise = np.array([
        frame.values[[0, 4]] - truth.sample(frame.t).armor_positions[[0, 1], 0]
        for frame in frames
    ])
    np.testing.assert_allclose(np.cov(noise.T), covariance[np.ix_([0, 4], [0, 4])], atol=7e-6)


def test_outliers_use_separate_selection_and_requested_noise_scale():
    truth = build_truth(scene(), 42)
    config = ObservationConfig(mode="fixed", std_xyz=.001, std_yaw=.001)
    baseline = generate_observations(truth, config, 42)
    config.outlier_probability = 1
    config.outlier_scale = 8
    outliers = generate_observations(truth, config, 42)
    for a, b in zip(baseline, outliers):
        expected = np.r_[truth.sample(a.t).armor_positions[0], truth.sample(a.t).reference_yaw]
        np.testing.assert_allclose(b.values - expected, 8 * (a.values - expected), atol=1e-12)


def test_indefinite_true_covariance_is_rejected():
    config = ObservationConfig(mode="fixed", covariance=np.diag([-1, 1, 1, 1]).tolist())
    with pytest.raises(ValueError, match="positive semidefinite"):
        generate_observations(build_truth(scene(), 42), config, 42)
