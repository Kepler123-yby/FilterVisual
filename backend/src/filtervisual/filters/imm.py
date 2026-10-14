"""Interacting multiple-model filtering with continuous-time mode transitions."""
from __future__ import annotations

import copy
from functools import lru_cache
import numpy as np
from scipy.linalg import expm, cho_solve
from scipy.special import logsumexp

from filtervisual.core.linalg import cholesky_with_jitter, validate_covariance
from filtervisual.core.types import Estimate, FilterSnapshot, UpdateDiagnostics


@lru_cache(maxsize=256)
def _cached_transition(generator_bytes: bytes, dimension: int, dt: float) -> np.ndarray:
    generator = np.frombuffer(generator_bytes, dtype=float).reshape(dimension, dimension)
    probabilities = expm(generator * dt)
    if np.min(probabilities) < -1e-12:
        raise ValueError("IMM transition exponential produced negative probability")
    probabilities = np.maximum(probabilities, 0.)
    return probabilities / probabilities.sum(axis=1, keepdims=True)


def transition_matrix(generator: np.ndarray, dt: float) -> np.ndarray:
    generator = np.asarray(generator, dtype=float)
    if generator.ndim != 2 or generator.shape[0] != generator.shape[1] or not generator.size:
        raise ValueError("IMM generator must be a nonempty square matrix")
    if not np.isfinite(generator).all() or not np.isfinite(dt) or dt < 0:
        raise ValueError("IMM generator and dt must be finite; dt must be nonnegative")
    off_diagonal = generator.copy()
    np.fill_diagonal(off_diagonal, 0.)
    if (off_diagonal < 0).any() or not np.allclose(generator.sum(axis=1), 0., atol=1e-12, rtol=0.):
        raise ValueError("IMM generator requires nonnegative off-diagonals and zero row sums")
    # Cache common exact dt values; no rounding changes requested timestamps.
    return _cached_transition(generator.tobytes(), len(generator), float(dt)).copy()


def fuse_gaussians(means, covariances, weights, model):
    weights = np.asarray(weights, dtype=float)
    means = np.asarray(means, dtype=float)
    covariances = np.asarray(covariances, dtype=float)
    if means.ndim != 2 or not len(means) or covariances.shape != (len(means), means.shape[1], means.shape[1]):
        raise ValueError("IMM means and covariances must have matching dimensions")
    if weights.shape != (len(means),) or not np.isfinite(weights).all() or (weights < 0).any() or not np.isclose(weights.sum(), 1.):
        raise ValueError("IMM weights must be nonnegative and sum to one")
    if not np.isfinite(means).all() or not np.isfinite(covariances).all():
        raise ValueError("IMM mode states must be finite")
    mean = model.state_mean(means, weights)
    covariance = np.zeros(covariances.shape[1:])
    for point, P, weight in zip(means, covariances, weights):
        delta = model.state_residual(point, mean)
        covariance += weight * (P + np.outer(delta, delta))
    return mean, (covariance + covariance.T) * .5


class InteractingMultipleModel:
    def __init__(self, filters, probabilities, generator):
        if not filters:
            raise ValueError("IMM needs at least one sub-filter")
        self.filters = list(filters)
        self.model = self.filters[0].model
        signature = (tuple(self.model.state_names), tuple(self.model.units), tuple(self.model.angular_indices))
        for mode in self.filters:
            if (tuple(mode.model.state_names), tuple(mode.model.units), tuple(mode.model.angular_indices)) != signature:
                raise ValueError("IMM modes require identical state dimensions and semantics")
            if not np.isclose(mode.snapshot().t, self.filters[0].snapshot().t, rtol=0., atol=1e-10):
                raise ValueError("IMM modes must have the same time")
        self.probabilities = probabilities
        self.generator = np.asarray(generator, dtype=float).copy()
        if self.generator.shape != (len(filters), len(filters)):
            raise ValueError("IMM generator dimension differs from mode count")
        transition_matrix(self.generator, 0.)
        self.jitter = 0.
        self._fuse()

    @property
    def t(self):
        return self.filters[0].t

    @property
    def probabilities(self):
        return np.exp(self._log_probabilities)

    @probabilities.setter
    def probabilities(self, probabilities):
        probabilities = np.asarray(probabilities, dtype=float)
        if (probabilities.shape != (len(self.filters),) or not np.isfinite(probabilities).all()
                or (probabilities < 0).any() or not np.isclose(probabilities.sum(), 1., atol=1e-12)):
            raise ValueError("IMM probabilities must be nonnegative and sum to one")
        with np.errstate(divide="ignore"):
            self._log_probabilities = np.log(probabilities / probabilities.sum())

    def _fuse(self):
        states = [mode.snapshot() for mode in self.filters]
        self.x, self.P = fuse_gaussians([s.x for s in states], [s.P for s in states],
                                       self.probabilities, self.model)
        _, self.P, jitter = cholesky_with_jitter(self.P, name="IMM fused P")
        self.jitter = max(jitter, *[float(getattr(s, "jitter", 0.)) for s in states])
        return Estimate(t=self.t, x=self.x.copy(), P=self.P.copy(),
                        mode_probabilities=self.probabilities.copy())

    def predict(self, dt):
        Pi = transition_matrix(self.generator, dt)
        origin = [mode.snapshot() for mode in self.filters]
        with np.errstate(divide="ignore"):
            log_joint = self._log_probabilities[:, None] + np.log(Pi)
        next_logs = logsumexp(log_joint, axis=0)
        # Prepare every destination before mutating any source mode.
        mixed = []
        for destination, log_probability in enumerate(next_logs):
            if np.isneginf(log_probability):
                mixed.append((origin[destination].x.copy(), origin[destination].P.copy()))
                continue
            mixed.append(fuse_gaussians([s.x for s in origin], [s.P for s in origin],
                                       np.exp(log_joint[:, destination] - log_probability), self.model))
        for mode, previous, (mean, covariance) in zip(self.filters, origin, mixed):
            mode.restore(FilterSnapshot(t=previous.t, x=mean, P=covariance))
            mode.predict(dt)
        self._log_probabilities = next_logs - logsumexp(next_logs)
        return self._fuse()

    def update(self, frame):
        prior_weights = self.probabilities.copy()
        diagnostics = [mode.update(frame) for mode in self.filters]
        log_likelihood = []
        for diagnostic in diagnostics:
            factor, _, _ = cholesky_with_jitter(diagnostic.S, name="IMM innovation S")
            whitened = cho_solve((factor, True), diagnostic.innovation)
            score = float(diagnostic.innovation @ whitened)
            log_determinant = 2. * np.log(np.diag(factor)).sum()
            log_likelihood.append(-.5 * (score + log_determinant + diagnostic.dof * np.log(2. * np.pi)))
        logs = self._log_probabilities + np.asarray(log_likelihood)
        normalizer = logsumexp(logs)
        if not np.isfinite(normalizer):
            raise ValueError("IMM likelihood normalization failed")
        self._log_probabilities = logs - normalizer
        posterior = self._fuse()
        # A moment-matched innovation supports an explicitly approximate NIS.
        innovations = np.asarray([d.innovation for d in diagnostics])
        innovation = self.model.observation_mean(innovations, prior_weights, frame.context)
        # Local angular means can lie outside the principal interval. The
        # fused innovation still needs the shortest residual for its NIS.
        innovation = self.model.observation_residual(
            innovation, np.zeros_like(innovation), frame.context)
        S = np.zeros_like(diagnostics[0].S)
        for d, weight in zip(diagnostics, prior_weights):
            delta = self.model.observation_residual(d.innovation, innovation, frame.context)
            S += weight * (d.S + np.outer(delta, delta))
        return UpdateDiagnostics(t=self.t, innovation=innovation, S=S, dof=len(innovation),
                                 posterior=posterior, observation_id=frame.id,
                                 mode_diagnostics=tuple(diagnostics), jitter=self.jitter)

    def snapshot(self):
        return FilterSnapshot(t=self.t, x=self.x.copy(), P=self.P.copy(),
                              mode_probabilities=self.probabilities.copy(),
                              mode_snapshots=tuple(mode.snapshot() for mode in self.filters),
                              kind="imm", jitter=self.jitter,
                              extra={"log_probabilities": tuple(self._log_probabilities)})

    def restore(self, snapshot):
        if len(snapshot.mode_snapshots) != len(self.filters):
            raise ValueError("IMM snapshot mode count differs")
        probabilities = np.asarray(snapshot.mode_probabilities, dtype=float)
        if probabilities.shape != self.probabilities.shape or not np.isfinite(probabilities).all() or (probabilities < 0).any() or not np.isclose(probabilities.sum(), 1.):
            raise ValueError("invalid IMM snapshot probabilities")
        log_probabilities = snapshot.extra.get("log_probabilities")
        if log_probabilities is not None:
            log_probabilities = np.asarray(log_probabilities, dtype=float)
            if (log_probabilities.shape != probabilities.shape or np.isnan(log_probabilities).any()
                    or np.isposinf(log_probabilities).any() or not np.isfinite(log_probabilities).any()
                    or not np.isclose(logsumexp(log_probabilities), 0., atol=1e-12)
                    or not np.allclose(np.exp(log_probabilities), probabilities, atol=1e-12, rtol=1e-10)):
                raise ValueError("invalid IMM snapshot log probabilities")
        for mode, state in zip(self.filters, snapshot.mode_snapshots):
            mode.restore(state)
        if log_probabilities is None:
            self.probabilities = probabilities
        else:
            self._log_probabilities = log_probabilities.copy()
        self._fuse()

    def clone(self):
        clone = copy.deepcopy(self)
        clone.restore(self.snapshot())
        return clone
