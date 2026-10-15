import numpy as np
import pytest

from filtervisual.config.schema import RotationConfig, SceneConfig, SineTerm, TranslationConfig, Waypoint
from filtervisual.scene.motion import build_truth, rotation_at


def constant_scene(**updates):
    return SceneConfig(
        duration_s=1.0, simulation_dt=0.02,
        translation=TranslationConfig(mode="constant", initial_xy=[1.0, -2.0], velocity_xy=[2.0, 0.5]),
        rotation=RotationConfig(mode="angular_velocity", initial_yaw=0, terms=[SineTerm(amplitude=0, frequency_rad_s=0, offset=2)]),
        **updates,
    )


def test_continuous_constant_motion_at_arbitrary_time():
    truth = build_truth(constant_scene(), 42)
    state = truth.sample(0.3137)
    np.testing.assert_allclose(state.center_xy, [1.6274, -1.84315], atol=1e-10)
    np.testing.assert_allclose(state.velocity_xyz, [2, 0.5, 0], atol=1e-12)
    assert state.reference_yaw == pytest.approx(0.6274)
    assert state.angular_velocity == pytest.approx(2)
    assert truth.sample(0.3).reference_yaw == pytest.approx(0.6)


def test_negative_constant_translation_and_clockwise_spin():
    scene = constant_scene()
    scene.translation.velocity_xy = [-2., -.5]
    scene.rotation.terms[0].offset = -2.
    state = build_truth(scene, 42).sample(.3137)
    np.testing.assert_allclose(state.center_xy, [.3726, -2.15685], atol=1e-10)
    np.testing.assert_allclose(state.velocity_xyz, [-2., -.5, 0.], atol=1e-12)
    assert state.reference_yaw == pytest.approx(-.6274)
    assert state.angular_velocity == pytest.approx(-2.)


@pytest.mark.parametrize("mode", ["angle", "angular_velocity"])
def test_zero_and_tiny_frequency_have_constant_limit(mode):
    rotation = RotationConfig(
        mode=mode, initial_yaw=.4,
        terms=[SineTerm(amplitude=2, frequency_rad_s=0, phase_rad=np.pi / 2, offset=3)],
    )
    theta, omega = rotation_at(rotation, .7)
    if mode == "angle":
        assert theta == pytest.approx(5.4)
        assert omega == 0
    else:
        assert theta == pytest.approx(3.9)
        assert omega == pytest.approx(5)
    tiny = rotation.model_copy(deep=True)
    tiny.terms[0].frequency_rad_s = 1e-15
    np.testing.assert_allclose(rotation_at(tiny, .7), [theta, omega], atol=1e-12)


def test_multisine_velocity_integrates_each_phase_and_offset():
    rotation = RotationConfig(
        mode="angular_velocity", initial_yaw=.6,
        terms=[
            SineTerm(amplitude=1.3, frequency_rad_s=2, phase_rad=.3, offset=1),
            SineTerm(amplitude=-.2, frequency_rad_s=3, phase_rad=-.4, offset=.5),
        ],
    )
    t = .435
    expected = .6 + 1.3 * (np.cos(.3) - np.cos(2 * t + .3)) / 2 + t
    expected += -.2 * (np.cos(-.4) - np.cos(3 * t - .4)) / 3 + .5 * t
    theta, omega = rotation_at(rotation, t)
    assert theta == pytest.approx(expected, abs=1e-12)
    numerical_derivative = (rotation_at(rotation, t + 1e-6)[0] - rotation_at(rotation, t - 1e-6)[0]) / 2e-6
    assert omega == pytest.approx(numerical_derivative, abs=1e-9)
    assert rotation_at(rotation, 0)[0] == .6


def test_angle_mode_derivative_and_continuity():
    rotation = RotationConfig(
        mode="angle", initial_yaw=4,
        terms=[SineTerm(amplitude=.8, frequency_rad_s=1.2, phase_rad=.4, offset=.7)],
    )
    theta, omega = rotation_at(rotation, .6)
    assert theta > np.pi
    assert omega == pytest.approx(.8 * 1.2 * np.cos(1.2 * .6 + .4), abs=1e-12)


@pytest.mark.parametrize("mode", ["angle", "angular_velocity"])
def test_negative_sine_parameters_preserve_signed_rotation(mode):
    rotation = RotationConfig(mode=mode, initial_yaw=-.4, terms=[
        SineTerm(amplitude=-.8, frequency_rad_s=-1.2, phase_rad=-.4, offset=-.7),
    ])
    t = .6
    theta, omega = rotation_at(rotation, t)
    if mode == "angle":
        assert theta == pytest.approx(-.4 - .8 * np.sin(-1.2 * t - .4) - .7)
        assert omega == pytest.approx(.96 * np.cos(-1.2 * t - .4))
    else:
        assert theta == pytest.approx(-.4 + (-.8 / -1.2) * (np.cos(-.4) - np.cos(-1.2 * t - .4)) - .7 * t)
        assert omega == pytest.approx(-.8 * np.sin(-1.2 * t - .4) - .7)
    derivative = (rotation_at(rotation, t + 1e-6)[0] - rotation_at(rotation, t - 1e-6)[0]) / 2e-6
    assert omega == pytest.approx(derivative, abs=1e-9)


def test_random_smooth_speed_bounds_reproducibility_and_seed_effect():
    scene = SceneConfig(duration_s=3, simulation_dt=.025, translation=TranslationConfig(
        mode="random_smooth", speed_min=.5, speed_max=2, node_interval_s=1,
    ))
    a, b, c = build_truth(scene, 42), build_truth(scene, 42), build_truth(scene, 43)
    times = np.linspace(0, 3, 101)
    speed = np.array([np.linalg.norm(a.sample(t).velocity_xyz) for t in times])
    assert speed.min() >= .5 - 1e-12
    assert speed.max() <= 2 + 1e-12
    np.testing.assert_array_equal(a.sample(1.337).center_xy, b.sample(1.337).center_xy)
    assert not np.allclose(a.sample(2.0).center_xy, c.sample(2.0).center_xy)
    # Node transitions have vanishing derivatives and do not redraw on sample.
    np.testing.assert_allclose(a.velocity(1 - 1e-6), a.velocity(1 + 1e-6), atol=1e-10)
    np.testing.assert_array_equal(a.sample(.8).center_xy, a.sample(.8).center_xy)


def test_waypoint_heading_takes_short_path_and_speed_stays_bounded():
    scene = SceneConfig(duration_s=1, simulation_dt=.02, translation=TranslationConfig(
        mode="waypoints", waypoints=[
            Waypoint(time_s=0, speed=1, heading_rad=np.deg2rad(170)),
            Waypoint(time_s=1, speed=2, heading_rad=np.deg2rad(-170)),
        ],
    ))
    state = build_truth(scene, 7).sample(.5)
    np.testing.assert_allclose(state.velocity_xyz, [-1.5, 0, 0], atol=1e-12)


def test_signed_waypoints_reverse_continuously_through_zero():
    scene = SceneConfig(duration_s=1, simulation_dt=.01, translation=TranslationConfig(
        mode="waypoints", initial_xy=[1., -2.], waypoints=[
            Waypoint(time_s=0, speed=-2, heading_rad=0),
            Waypoint(time_s=1, speed=2, heading_rad=0),
        ],
    ))
    truth = build_truth(scene, 7)
    for t in [0., .1, .3, .5, .7, .9, 1.]:
        state = truth.sample(t)
        np.testing.assert_allclose(state.velocity_xyz, [-2 * np.cos(np.pi * t), 0, 0], atol=1e-12)
        np.testing.assert_allclose(state.center_xy, [1 - 2 / np.pi * np.sin(np.pi * t), -2], atol=1e-9)
    assert truth.sample(.5 - 1e-6).velocity_xyz[0] < 0
    assert truth.sample(.5 + 1e-6).velocity_xyz[0] > 0


def test_negative_waypoint_speed_moves_opposite_its_heading():
    scene = SceneConfig(duration_s=1, simulation_dt=.02, translation=TranslationConfig(
        mode="waypoints", waypoints=[Waypoint(time_s=0, speed=-2, heading_rad=np.pi / 2)],
    ))
    state = build_truth(scene, 7).sample(.7)
    np.testing.assert_allclose(state.center_xy, [0., -1.4], atol=1e-10)
    np.testing.assert_allclose(state.velocity_xyz, [0., -2., 0.], atol=1e-12)


@pytest.mark.parametrize("speed_min,speed_max", [(-2., -.5), (-1., 1.), (-1., -1.)])
def test_random_smooth_accepts_signed_speed_ranges(speed_min, speed_max):
    scene = SceneConfig(duration_s=3, simulation_dt=.02, translation=TranslationConfig(
        mode="random_smooth", speed_min=speed_min, speed_max=speed_max, node_interval_s=1.,
    ))
    a, b = build_truth(scene, 42), build_truth(scene, 42)
    profile = a.velocity
    assert np.all(profile.speeds >= speed_min)
    assert np.all(profile.speeds <= speed_max)
    for t, speed, heading in zip(profile.times, profile.speeds, profile.headings):
        np.testing.assert_allclose(a.sample(t).velocity_xyz[:2], speed * np.array([np.cos(heading), np.sin(heading)]), atol=1e-12)
    np.testing.assert_array_equal(a.sample(1.337).center_xy, b.sample(1.337).center_xy)


def test_simulation_step_changes_accuracy_without_changing_random_profile():
    scene = SceneConfig(duration_s=2, simulation_dt=.03, translation=TranslationConfig(mode="random_smooth"))
    finer = scene.model_copy(deep=True)
    finer.simulation_dt = .002
    a, b = build_truth(scene, 12), build_truth(finer, 12)
    for time in [.1, .37, 1.113, 2.0]:
        np.testing.assert_array_equal(a.sample(time).velocity_xyz, b.sample(time).velocity_xyz)
        np.testing.assert_allclose(a.sample(time).center_xy, b.sample(time).center_xy, atol=2e-7)


@pytest.mark.parametrize("t", [-.1, 1.1, np.nan, np.inf])
def test_truth_rejects_time_outside_scene(t):
    with pytest.raises(ValueError, match="outside"):
        build_truth(constant_scene(), 42).sample(t)


def test_truth_snapshots_edited_scene():
    scene = constant_scene()
    truth = build_truth(scene, 42)
    scene.geometry.radius_a = .9
    assert truth.sample(.2).radius_a != scene.geometry.radius_a
