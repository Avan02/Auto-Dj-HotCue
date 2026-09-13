import numpy as np

from serato_autocue.structure import _checkerboard_kernel, _normalize, _novelty_curve


def test_checkerboard_kernel_shape_and_signs():
    kernel = _checkerboard_kernel(4)
    assert kernel.shape == (9, 9)
    assert np.allclose(kernel, kernel.T)
    # Same-side quadrants (both offsets negative, or both positive) are
    # positive weight; cross quadrants (opposite-signed offsets) are negative.
    assert kernel[0, 0] > 0  # (-4, -4): same quadrant
    assert kernel[-1, -1] > 0  # (+4, +4): same quadrant
    assert kernel[0, -1] < 0  # (-4, +4): cross quadrant
    assert kernel[-1, 0] < 0  # (+4, -4): cross quadrant


def test_novelty_curve_peaks_at_a_sharp_block_transition():
    # A synthetic "self-similarity matrix" for two internally-similar,
    # mutually-dissimilar blocks should produce a novelty peak right at
    # the block boundary.
    n = 40
    boundary = 20
    ssm = np.zeros((n, n))
    ssm[:boundary, :boundary] = 1.0
    ssm[boundary:, boundary:] = 1.0
    novelty = _novelty_curve(ssm, half_size=6)
    assert np.argmax(novelty) in range(boundary - 2, boundary + 2)


def test_normalize_handles_constant_input():
    flat = np.full(10, 5.0)
    result = _normalize(flat)
    assert np.all(result == 0)
