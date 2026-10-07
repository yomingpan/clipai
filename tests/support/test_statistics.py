import pytest

from ClipAI.support.statistics import percentile


def test_percentile_uses_one_consistent_nearest_rank_policy():
    assert percentile([40.0, 10.0, 30.0, 20.0], 0.5) == 20.0
    assert percentile([40.0, 10.0, 30.0, 20.0], 0.95) == 40.0


@pytest.mark.parametrize("fraction", [-0.1, 1.1])
def test_percentile_rejects_out_of_range_fraction(fraction):
    with pytest.raises(ValueError, match="fraction"):
        percentile([1.0], fraction)


def test_percentile_rejects_empty_input():
    with pytest.raises(ValueError, match="values"):
        percentile([], 0.5)
