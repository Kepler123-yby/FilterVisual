"""Six-state XY example with slowly varying measurement biases.

State order: [cx, cy, vx, vy, bx, by]. Geometry and reference yaw are known
constants, so this example requires fixed orientation and constant XY velocity.
Each visible plate still provides the application's [x, y, z, yaw] observation.

``q_accel`` and ``q_bias`` are continuous-time noise intensities, not standard
deviations. ``position_std`` (m), ``yaw_std`` (rad), and ``xy_correlation``
describe the filter's measurement covariance, not the simulator's noise source.
Use ``xy_correlation=0`` for diagonal R; a nonzero value correlates a plate's
x/y errors within one frame. Different plates remain independent in this R.

The measurements contain cx + bx and cy + by: a constant center offset cannot
be distinguished from an opposite bias offset from these observations alone.
An initial bias prior or independent calibration must anchor that ambiguity.
The built-in simulator has no latent bx/by truth, so truth_mapping deliberately
includes only center and velocity, and this model does not synthesize biases.

To run, load this file as a Python model and set each instance's x0 to six
values and p0 to a positive-definite 6x6 matrix; see the custom-model guide.
"""
from __future__ import annotations

import numpy as np

from filtervisual.core.types import PhysicalEstimate, TruthMapping
from filtervisual.models.protocol import AngularModel


class XYBiasModel(AngularModel):
    state_names = ("cx", "cy", "vx", "vy", "bx", "by")
    units = ("m", "m", "m/s", "m/s", "m", "m")
    angular_indices = ()

    def __init__(self, geometry, q_accel=0.2, q_bias=1e-6,
                 position_std=0.01, yaw_std=0.02, xy_correlation=0.0,
                 reference_yaw=0.0):
        parameters = np.asarray(
            [q_accel, q_bias, position_std, yaw_std, xy_correlation, reference_yaw],
            dtype=float,
        )
        if parameters.shape != (6,) or not np.isfinite(parameters).all():
            raise ValueError("model parameters must be finite scalars")
        if (parameters[:2] < 0).any():
            raise ValueError("q_accel and q_bias must be nonnegative")
        if (parameters[2:4] <= 0).any():
            raise ValueError("position_std and yaw_std must be positive")
        if abs(parameters[4]) >= 1:
            raise ValueError("xy_correlation must be strictly between -1 and 1")
        (self.q_accel, self.q_bias, self.position_std, self.yaw_std,
         self.xy_correlation, self.reference_yaw) = parameters
        self.geometry = geometry.model_copy(deep=True)

    def f(self, x, dt, t0):
        """Predict position; velocity and bias retain their current means."""
        result = np.asarray(x, dtype=float).copy()
        result[0] += result[2] * dt
        result[1] += result[3] * dt
        # Random bias drift is represented by Q, not by a deterministic offset.
        return result

    def jacobian_f(self, x, dt, t0):
        """F = df/dx in exactly the order declared by state_names."""
        F = np.eye(6)
        F[0, 2] = dt
        F[1, 3] = dt
        return F

    def Q(self, dt):
        """Integrate white acceleration and independent bias random walks."""
        if not np.isfinite(dt) or dt < 0:
            raise ValueError("Q dt must be finite and nonnegative")
        covariance = np.zeros((6, 6))
        # Per-axis [position, velocity] covariance. q_accel has units m^2/s^3.
        acceleration_block = self.q_accel * np.array([
            [dt ** 3 / 3.0, dt ** 2 / 2.0],
            [dt ** 2 / 2.0, dt],
        ])
        covariance[np.ix_([0, 2], [0, 2])] = acceleration_block
        covariance[np.ix_([1, 3], [1, 3])] = acceleration_block
        # q_bias has units m^2/s. At dt=0 all process covariance is zero.
        covariance[4, 4] = self.q_bias * dt
        covariance[5, 5] = self.q_bias * dt
        return covariance

    @staticmethod
    def _plate_ids(context):
        ids = tuple(context.plate_ids)
        if not ids or len(set(ids)) != len(ids) or any(i not in range(4) for i in ids):
            raise ValueError("observation plate IDs must be unique values in 0..3")
        return ids

    def h(self, x, context):
        """Map state to each requested plate's [x, y, z, yaw], in ID order."""
        values = []
        geometry = self.geometry
        for plate in self._plate_ids(context):
            yaw = self.reference_yaw + (plate - geometry.reference_id) * np.pi / 2.0
            radius = geometry.radius_b if plate % 2 else geometry.radius_a
            height = geometry.height_a + (geometry.height_diff if plate % 2 else 0.0)
            values.extend([
                x[0] + radius * np.cos(yaw) + x[4],
                x[1] + radius * np.sin(yaw) + x[5],
                height,
                yaw,
            ])
        return np.asarray(values, dtype=float)

    def jacobian_h(self, x, context):
        """H has 4 rows per plate and 6 columns for this model's states."""
        ids = self._plate_ids(context)
        H = np.zeros((4 * len(ids), 6))
        for index in range(len(ids)):
            H[4 * index, 0] = 1.0       # d plate_x / d cx
            H[4 * index, 4] = 1.0       # d plate_x / d bx
            H[4 * index + 1, 1] = 1.0   # d plate_y / d cy
            H[4 * index + 1, 5] = 1.0   # d plate_y / d by
            # z/yaw are known constants, so their state derivatives are zero.
        return H

    def R(self, frame):
        """Build one [x, y, z, yaw] covariance block per observed plate."""
        count = len(self._plate_ids(frame.context))
        position_variance = self.position_std ** 2
        block = np.diag([
            position_variance, position_variance, position_variance,
            self.yaw_std ** 2,
        ])
        block[0, 1] = block[1, 0] = self.xy_correlation * position_variance
        return np.kron(np.eye(count), block)

    def project(self, x, P):
        """Expose only the center and velocity that this reduced state holds."""
        return PhysicalEstimate(
            center_xy=np.asarray(x[:2]).copy(),
            velocity_xyz=np.r_[x[2:4], 0.0],
            covariance={"center_xy": np.asarray(P[:2, :2]).copy()},
        )

    def truth_mapping(self, physical):
        # Do not invent truth values for latent biases absent from the simulator.
        return TruthMapping(
            indices=(0, 1, 2, 3),
            values=np.r_[physical.center_xy, physical.velocity_xyz[:2]],
        )


def build_model(params, geometry):
    return XYBiasModel(geometry, **params)
