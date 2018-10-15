import numpy as np
from numpy.testing import assert_almost_equal
from numpy.testing import assert_array_almost_equal
import pytest

from pygbm.splitting import _find_histogram_split
from pygbm.splitting import HistogramSplitter


@pytest.mark.parametrize('n_bins', [3, 32, 256])
def test_hitstogram_split(n_bins):
    rng = np.random.RandomState(42)
    feature_idx = 12
    l2_regularization = 0
    min_hessian_to_split = 1e-3
    binned_feature = rng.randint(0, n_bins, size=int(1e4)).astype(np.uint8)
    sample_indices = np.arange(binned_feature.shape[0], dtype=np.uint32)
    ordered_hessians = np.ones_like(binned_feature, dtype=np.float32)

    for true_bin in range(1, n_bins - 1):
        for sign in [-1, 1]:
            ordered_gradients = np.full_like(binned_feature, sign,
                                             dtype=np.float32)
            ordered_gradients[binned_feature <= true_bin] *= -1

            split_info = _find_histogram_split(
                feature_idx, binned_feature, n_bins, sample_indices,
                ordered_gradients, ordered_hessians, l2_regularization,
                min_hessian_to_split, True, ordered_hessians[0],
                ordered_gradients.sum(),
                ordered_hessians[0] * sample_indices.shape[0])

            assert split_info.bin_idx == true_bin
            assert split_info.gain >= 0
            assert split_info.feature_idx == feature_idx


@pytest.mark.parametrize('constant_hessian', [True, False])
def test_split_vs_split_subtraction(constant_hessian):
    # Make sure find_node_split and find_node_split_subtraction return the
    # same results.
    # Should we add a test about computation time to make sure
    # time(subtraction) < time(regular)?
    rng = np.random.RandomState(42)

    n_bins = 10
    n_features = 20
    n_samples = 500
    l2_regularization = 0.
    min_hessian_to_split = 1e-3

    binned_features = rng.randint(0, n_bins, size=(n_samples, n_features),
                                  dtype=np.uint8)
    binned_features = np.asfortranarray(binned_features)
    sample_indices = np.arange(n_samples, dtype=np.uint32)
    all_gradients = rng.randn(n_samples).astype(np.float32)
    if constant_hessian:
        all_hessians = np.ones(1, dtype=np.float32)
    else:
        all_hessians = rng.lognormal(size=n_samples).astype(np.float32)

    splitter = HistogramSplitter(n_features, binned_features, n_bins,
                                 all_gradients, all_hessians,
                                 l2_regularization, min_hessian_to_split)

    mask = rng.randint(0, 2, n_samples).astype(np.bool)
    sample_indices_left = sample_indices[mask]
    sample_indices_right = sample_indices[~mask]

    # first split parent, left and right with classical method
    si_parent, hists_parent = splitter.find_node_split(sample_indices)
    si_left, hists_left = splitter.find_node_split(sample_indices_left)
    si_right, hists_right = splitter.find_node_split(sample_indices_right)

    # split left with subtraction method
    gradient_left = si_left.gradient_left + si_left.gradient_right
    hessian_left = si_left.hessian_left + si_left.hessian_right
    si_left_sub, hists_left_sub = splitter.find_node_split_subtraction(
        sample_indices_left, hists_parent, hists_right, gradient_left,
        hessian_left)

    # split right with subtraction method
    gradient_right = si_right.gradient_left + si_right.gradient_right
    hessian_right = si_right.hessian_left + si_right.hessian_right
    si_right_sub, hists_right_sub = splitter.find_node_split_subtraction(
        sample_indices_right, hists_parent, hists_left, gradient_right,
        hessian_right)

    # make sure histograms from classical and subtraction method are the same
    for hists, hists_sub in ((hists_left, hists_left_sub),
                             (hists_right, hists_right_sub)):
        for hist, hist_sub in zip(hists, hists_sub):
            for key in ('count', 'sum_hessians', 'sum_gradients'):
                assert_array_almost_equal(hist[key], hist_sub[key], decimal=4)

    # make sure split_infos from classical and subtraction method are the same
    for si, si_sub in ((si_left, si_left_sub), (si_right, si_right_sub)):
        assert_almost_equal(si.gain, si_sub.gain, decimal=4)
        assert_almost_equal(si.feature_idx, si_sub.feature_idx, decimal=4)
        assert_almost_equal(si.gradient_left, si_sub.gradient_left, decimal=4)
        assert_almost_equal(si.gradient_right, si_sub.gradient_right,
                            decimal=4)
        assert_almost_equal(si.hessian_right, si_sub.hessian_right, decimal=4)
        assert_almost_equal(si.hessian_left, si_sub.hessian_left, decimal=4)
