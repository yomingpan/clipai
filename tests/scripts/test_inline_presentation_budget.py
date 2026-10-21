from scripts.inline_surface_presentation_benchmark import initial_budget_passed


def test_initial_presentation_budget_rejects_slow_or_missing_observations():
    assert not initial_budget_passed({"minimal.initial": {"count": 20, "p95_ms": 75}}, 51.7)
    assert not initial_budget_passed({}, 51.7)
    assert initial_budget_passed({"minimal.initial": {"count": 20, "p95_ms": 47}, "choice.initial": {"count": 20, "p95_ms": 49}}, 51.7)
