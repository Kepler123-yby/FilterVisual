"""Eleven-state center CV / constant-spin model with fixed armor identities."""
from __future__ import annotations

import numpy as np
from scipy.linalg import block_diag

from filtervisual.config.schema import GeometryConfig
from filtervisual.core.types import PhysicalEstimate, TruthMapping
from filtervisual.models.protocol import AngularModel
from filtervisual.scene.geometry import armor_positions


class RoboMasterCVModel(AngularModel):
    # Its continuous-white-acceleration transition is an exact semigroup.
    # Forecasts can propagate Gaussian engines in one step without loss.
    exact_linear_prediction = True
    state_names = ("cx", "cy", "zA", "vx", "vy", "vz", "theta", "omega", "rA", "rB", "dh")
    units = ("m", "m", "m", "m/s", "m/s", "m/s", "rad", "rad/s", "m", "m", "m")
    angular_indices = (6,)

    def __init__(self, geometry: GeometryConfig, q_translation=.5, q_rotation=.8,
                 q_geometry=1e-6, measurement_position_std=.01,
                 measurement_yaw_std=.02, observation_covariance=None):
        self.geometry = geometry.model_copy(deep=True)
        parameters = np.asarray([q_translation, q_rotation, q_geometry,
                                 measurement_position_std, measurement_yaw_std], dtype=float)
        if not np.isfinite(parameters).all() or (parameters[:3] < 0).any() or (parameters[3:] <= 0).any():
            raise ValueError("model noise strengths must be finite/nonnegative and stds positive")
        self.q_translation, self.q_rotation, self.q_geometry = parameters[:3]
        self.measurement_position_std, self.measurement_yaw_std = parameters[3:]
        self.observation_covariance = (None if observation_covariance is None else
                                       np.asarray(observation_covariance, dtype=float).copy())
        if self.observation_covariance is not None:
            from filtervisual.core.linalg import validate_covariance
            self.observation_covariance = validate_covariance(
                self.observation_covariance, name="observation_covariance",
                positive_definite=True)
            if self.observation_covariance.shape not in ((4, 4), (16, 16)):
                raise ValueError("observation_covariance must be 4x4 or 16x16")

    def f(self, x, dt, t0=0.):
        result = np.asarray(x, dtype=float).copy()
        result[:3] += result[3:6] * dt
        result[6] += result[7] * dt
        return result

    def f_batch(self, points, dt, t0=0.):
        result = np.asarray(points, dtype=float).copy()
        result[:, :3] += result[:, 3:6] * dt
        result[:, 6] += result[:, 7] * dt
        return result

    def state_residual_batch(self, points, mean):
        from filtervisual.core.angles import angular_residual
        return angular_residual(points, mean, self.angular_indices)

    def jacobian_f(self, x, dt, t0=0.):
        F = np.eye(11)
        F[0, 3] = F[1, 4] = F[2, 5] = F[6, 7] = dt
        return F

    def Q(self, dt):
        if not np.isfinite(dt) or dt < 0:
            raise ValueError("Q dt must be finite and nonnegative")
        covariance = np.zeros((11, 11))
        block = np.array([[dt ** 3 / 3., dt ** 2 / 2.], [dt ** 2 / 2., dt]])
        for position, velocity in ((0, 3), (1, 4), (2, 5)):
            covariance[np.ix_([position, velocity], [position, velocity])] = self.q_translation * block
        covariance[np.ix_([6, 7], [6, 7])] = self.q_rotation * block
        covariance[8:, 8:] = np.eye(3) * self.q_geometry * dt
        return covariance

    def _validate_plate_ids(self, context):
        ids = tuple(context.plate_ids)
        if not ids or len(set(ids)) != len(ids) or any(i not in range(4) for i in ids):
            raise ValueError("observation plate IDs must be unique values in 0..3")
        return ids

    def h(self, x, context):
        observations = []
        for plate_id in self._validate_plate_ids(context):
            odd = plate_id % 2
            yaw = x[6] + (plate_id - self.geometry.reference_id) * np.pi / 2.
            radius = x[9] if odd else x[8]
            observations.extend([x[0] + radius * np.cos(yaw), x[1] + radius * np.sin(yaw),
                                 x[2] + odd * x[10], yaw])
        return np.asarray(observations)

    def jacobian_h(self, x, context):
        matrices = []
        for plate_id in self._validate_plate_ids(context):
            odd = plate_id % 2
            yaw = x[6] + (plate_id - self.geometry.reference_id) * np.pi / 2.
            radius_index = 9 if odd else 8
            radius = x[radius_index]
            H = np.zeros((4, 11))
            H[0, 0] = H[1, 1] = H[2, 2] = H[3, 6] = 1.
            H[0, 6], H[1, 6] = -radius * np.sin(yaw), radius * np.cos(yaw)
            H[0, radius_index], H[1, radius_index] = np.cos(yaw), np.sin(yaw)
            H[2, 10] = odd
            matrices.append(H)
        return np.concatenate(matrices)

    def R(self, frame):
        ids = self._validate_plate_ids(frame.context)
        count = len(ids)
        if self.observation_covariance is not None and self.observation_covariance.shape == (16, 16):
            indices = [4 * plate + offset for plate in ids for offset in range(4)]
            return self.observation_covariance[np.ix_(indices, indices)].copy()
        block = (self.observation_covariance if self.observation_covariance is not None else
                 np.diag([self.measurement_position_std ** 2] * 3 + [self.measurement_yaw_std ** 2]))
        return block_diag(*[block] * count)

    def project(self, x, P):
        x, P = np.asarray(x), np.asarray(P)
        values = dict(center_xy=x[:2].copy(), height_a=float(x[2]), velocity_xyz=x[3:6].copy(),
                      reference_yaw=float(x[6]), angular_velocity=float(x[7]),
                      radius_a=float(x[8]), radius_b=float(x[9]), height_diff=float(x[10]))
        if not np.isfinite(x).all() or x[8] <= 0 or x[9] <= 0:
            return PhysicalEstimate(**values, armor_positions=np.full((4, 3), np.nan),
                                    valid=False, error="estimated radii must be positive and state finite")
        geometry = self.geometry.model_copy(update=dict(radius_a=x[8], radius_b=x[9],
                                                        height_a=x[2], height_diff=x[10]))
        positions = armor_positions(x[:2], geometry, x[6])
        plate_covariances = []
        from filtervisual.core.types import ObservationContext
        for plate_id in range(4):
            context = ObservationContext(time_s=0., plate_ids=(plate_id,), angular_indices=(3,))
            H = self.jacobian_h(x, context)[:3]
            plate_covariances.append(H @ P @ H.T)
        covariance = dict(center_xy=P[:2, :2].copy(), height_a=P[2:3, 2:3].copy(),
                          velocity_xyz=P[3:6, 3:6].copy(), reference_yaw=P[6:7, 6:7].copy(),
                          angular_velocity=P[7:8, 7:8].copy(), armor_positions=np.asarray(plate_covariances))
        return PhysicalEstimate(**values, armor_positions=positions, covariance=covariance)

    def truth_mapping(self, physical):
        values = np.r_[physical.center_xy, physical.height_a, physical.velocity_xyz,
                       physical.reference_yaw, physical.angular_velocity,
                       physical.radius_a, physical.radius_b, physical.height_diff]
        return TruthMapping(indices=tuple(range(11)), values=values, angular_indices=(6,))
