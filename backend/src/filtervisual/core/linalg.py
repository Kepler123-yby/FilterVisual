"""Strict covariance validation and bounded, observable numerical repair."""
from __future__ import annotations

import numpy as np
from scipy.linalg import cho_solve


class CovarianceError(ValueError):
    pass


def symmetric(matrix: np.ndarray) -> np.ndarray:
    return (np.asarray(matrix, dtype=float) + np.asarray(matrix, dtype=float).T) * .5


def validate_covariance(matrix: np.ndarray, *, name: str = "covariance",
                        positive_definite: bool = False,
                        dimension: int | None = None) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or not matrix.size:
        raise CovarianceError(f"{name}: expected a nonempty square matrix")
    if dimension is not None and matrix.shape != (dimension, dimension):
        raise CovarianceError(f"{name}: expected shape ({dimension}, {dimension})")
    if not np.isfinite(matrix).all():
        raise CovarianceError(f"{name}: values must be finite")
    if not np.allclose(matrix, matrix.T, rtol=1e-10, atol=1e-12):
        raise CovarianceError(f"{name}: matrix must be symmetric")
    eigenvalues = np.linalg.eigvalsh(symmetric(matrix))
    if positive_definite and eigenvalues[0] <= 0:
        raise CovarianceError(f"{name}: matrix must be positive definite (min eigenvalue {eigenvalues[0]:.3g})")
    if not positive_definite and eigenvalues[0] < -1e-12 * max(1., float(np.max(np.abs(matrix)))):
        raise CovarianceError(f"{name}: matrix must be positive semidefinite (min eigenvalue {eigenvalues[0]:.3g})")
    return matrix.copy()


def cholesky_with_jitter(matrix: np.ndarray, *, name: str = "covariance") -> tuple[np.ndarray, np.ndarray, float]:
    matrix = np.asarray(matrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or not matrix.size:
        raise CovarianceError(f"{name}: expected a nonempty square matrix")
    if not np.isfinite(matrix).all():
        raise CovarianceError(f"{name}: values must be finite")
    if not np.allclose(matrix, matrix.T, rtol=1e-10, atol=1e-12):
        raise CovarianceError(f"{name}: matrix must be symmetric")
    matrix = symmetric(matrix)
    scale = max(float(np.max(np.abs(np.diag(matrix)))), np.finfo(float).tiny)
    for relative in (0., 1e-12, 1e-11, 1e-10, 1e-9, 1e-8):
        jitter = relative * scale
        repaired = matrix + np.eye(len(matrix)) * jitter
        try:
            return np.linalg.cholesky(repaired), repaired, jitter
        except np.linalg.LinAlgError:
            continue
    raise CovarianceError(f"{name}: not positive definite after relative jitter <= 1e-8")


def solve_positive(matrix: np.ndarray, rhs: np.ndarray, *, name: str = "covariance"):
    factor, repaired, jitter = cholesky_with_jitter(matrix, name=name)
    return cho_solve((factor, True), rhs, check_finite=True), repaired, jitter
