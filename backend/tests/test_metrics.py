import numpy as np
import pytest

from filtervisual.evaluation.metrics import (
    chi_square_bounds,
    consistency_summary,
    error_summary,
    nees_score,
    nis_score,
    quadratic_score,
)


def test_consistency_scores_and_bounds():
    assert quadratic_score(np.array([3.]), np.array([[5.]])) == pytest.approx(1.8)
    assert quadratic_score(np.array([.4, -1.]), np.diag([.8, 1.])) == pytest.approx(1.2)
    low, high = chi_square_bounds(dof=2, confidence=.95)
    assert low == pytest.approx(.05063562, rel=1e-6)
    assert high == pytest.approx(7.37775891, rel=1e-6)


def test_independent_trial_bounds_use_total_degrees_of_freedom():
    from scipy.stats import chi2

    low, high = chi_square_bounds(2, .95, trials=20)
    assert low == pytest.approx(chi2.ppf(.025, 40) / 20)
    assert high == pytest.approx(chi2.ppf(.975, 40) / 20)


@pytest.mark.parametrize("matrix", [np.array([[0.]]), np.array([[-1.]]),
                                    np.array([[np.nan]]), np.ones((2, 1))])
def test_score_rejects_invalid_covariance(matrix):
    with pytest.raises(ValueError):
        quadratic_score(np.array([1.]), matrix)


def test_nees_subset_and_wrapped_angle():
    estimate = np.array([100., np.deg2rad(179.), 3.])
    truth = np.array([np.deg2rad(-179.), 2.])
    covariance = np.diag([100., .01, 2.])
    out = nees_score(estimate, covariance, indices=[1, 2], truth_values=truth,
                     angular_indices=[0], state_names=["angle", "position"])
    assert out["dof"] == 2
    assert out["value"] == pytest.approx(np.deg2rad(2.) ** 2 / .01 + .5)
    assert out["state_names"] == ["angle", "position"]


def test_unavailable_scores_have_null_and_specific_reason():
    assert nis_score(None, None)["reason"] == "no_new_observation"
    assert nis_score(None, None)["value"] is None
    assert nees_score(np.zeros(1), np.eye(1), indices=[], truth_values=[])["reason"] == "no_truth_mapping"
    assert nees_score(np.zeros(1), np.eye(1), indices=[0], truth_values=None,
                      truth_available=False)["reason"] == "truth_unavailable"


def test_imm_score_is_labeled_as_gaussian_approximation():
    out = nis_score(np.array([1.]), np.eye(1), filter_kind="imm")
    assert out["assumption"] == "gaussian_mixture_approximation"
    assert "通过" not in out["label"]


def test_error_summary_excludes_unscored_endpoints_and_preserves_gaps():
    out = error_summary([0., 1., 2., 3.], [[1.], [3.], [np.nan], [np.nan]])
    assert out["count"] == 2
    assert out["rmse"] == pytest.approx([np.sqrt(5.)])
    assert out["time_weighted_rmse"] == pytest.approx([np.sqrt(5.)])
    assert out["evidence_interval"] == [0., 1.]
    gaps = error_summary([0., 1., 2.], [[1.], [np.nan], [3.]])
    assert gaps["time_weighted_rmse"] is None
    assert gaps["count"] == 2


def test_descriptive_consistency_does_not_pool_different_dof_or_claim_independence():
    records = [dict(nis_score(np.array([1.]), np.eye(1)), t=0.),
               dict(nis_score(np.array([1., 1.]), np.eye(2)), t=1.)]
    groups = consistency_summary(records)
    assert len(groups) == 2
    assert {group["dof"] for group in groups} == {1, 2}
    assert all(group["interpretation"] == "correlated_time_samples_descriptive" for group in groups)
