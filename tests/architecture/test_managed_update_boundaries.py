from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_application_paths_are_injected_at_composition_root():
    main_source = (ROOT / "main.py").read_text(encoding="utf-8")
    container_source = (ROOT / "ClipAI" / "app" / "container.py").read_text(encoding="utf-8")
    assert "build_application_paths(" in main_source
    assert "build_runtime(bootstrap, paths=paths)" in main_source
    assert "paths: ApplicationPaths" in container_source
    assert "JsonUserPreferencesStore()" not in container_source
    assert "JsonlArchiveStore()" not in container_source


def test_managed_update_platform_io_has_one_declared_owner():
    contract = (ROOT / "docs" / "adr" / "0017-managed-update-transaction.md").read_text(encoding="utf-8")
    assert "ClipAI.platform.managed_update_fs" in contract
    assert "CandidateEnvironmentBuilder" in contract
    assert "ManagedApplicationLifecycle" in contract
