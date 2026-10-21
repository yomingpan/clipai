from scripts.probe_uia_standby import summarize


def test_standby_acceptance_requires_fifty_real_new_source_samples_and_cleanup():
    records = [{"elapsed_ms": 250, "selected": True, "unknown_as_none": False}] * 50
    report = summarize(records, standby=True, private_mb=[40, 49], max_workers=2, workers_after_stop=0)
    assert report["passed"]
    assert report["new_source_cases"] == 50
    assert report["latency_ms"]["p95"] == 250
    assert not summarize(records[:49], standby=True, private_mb=[40], max_workers=2, workers_after_stop=0)["passed"]
    assert not summarize(records, standby=True, private_mb=[61], max_workers=2, workers_after_stop=0)["passed"]
    assert not summarize(records, standby=True, private_mb=[40], max_workers=2, workers_after_stop=1)["passed"]
    assert not summarize(records, standby=True, private_mb=[], max_workers=2, workers_after_stop=0)["passed"]


def test_unknown_selection_cannot_pass_as_no_selection():
    records = [{"elapsed_ms": 10, "selected": True, "unknown_as_none": False}] * 49
    records += [{"elapsed_ms": 10, "selected": False, "unknown_as_none": True}]
    report = summarize(records, standby=True, private_mb=[40], max_workers=2, workers_after_stop=0)
    assert not report["passed"]
    assert report["unknown_as_none"] == 1
