import numpy as np
from filtervisual.models.rm_cv import RoboMasterCVModel

class CustomCV(RoboMasterCVModel):
    # Metadata, angular residuals, projection and truth mapping are inherited.
    # Override f/h/Q/R and their Jacobians together when equations change.
    def f(self, x, dt, t0):
        y = np.asarray(x, dtype=float).copy()
        y[:3] += y[3:6] * dt
        y[6] += y[7] * dt
        return y

    def f_batch(self, points, dt, t0):
        return np.array([self.f(x, dt, t0) for x in points])

def build_model(params, geometry):
    return CustomCV(geometry, **params)
