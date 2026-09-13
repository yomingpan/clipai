from pathlib import Path


def test_managed_update_verifier_is_the_single_staged_harness():
    source = (Path(__file__).resolve().parents[2] / "scripts" / "verify_managed_update.py").read_text(encoding="utf-8")
    for stage in ("fast", "synthetic", "loopback-http", "managed-bundle"):
        assert f'"{stage}"' in source
    assert "tests/e2e/test_managed_update_synthetic.py" in source
    assert "tests/e2e/test_managed_update_loopback_http.py" in source
