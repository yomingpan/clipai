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


def test_release_builder_has_one_core_and_one_thin_cli():
    scripts = [path.name for path in (ROOT / "scripts").glob("*managed*release*.py")]
    assert scripts == ["build_managed_release.py"]
    cli = (ROOT / "scripts" / scripts[0]).read_text(encoding="utf-8")
    assert "ManagedReleaseBuilder(signer).build(" in cli


def test_client_install_identity_never_requires_a_publisher_private_key():
    layout = (ROOT / "ClipAI" / "platform" / "managed_install.py").read_text(encoding="utf-8")
    signature = (ROOT / "ClipAI" / "platform" / "update_signature.py").read_text(encoding="utf-8")
    assert "marker_verifier" not in layout
    assert "INSTALL_SIGNING_NAMESPACE" not in signature


def test_managed_entry_has_one_subcommand_dispatcher_and_one_executor_seam():
    dispatchers = list((ROOT / "ClipAI" / "app").glob("*managed*dispatcher*.py"))
    assert [path.name for path in dispatchers] == ["managed_update_dispatcher.py"]
    source = dispatchers[0].read_text(encoding="utf-8")
    for command in ("install", "launch", "host", "selfcheck"):
        assert f'add_parser("{command}")' in source
    assert "execute: Callable[[ManagedCommand], int]" in source


def test_bundle_admission_has_one_platform_owner():
    platform_root = ROOT / "ClipAI" / "platform"
    callers = [
        path.name
        for path in platform_root.glob("*.py")
        if path.name != "managed_update_fs.py"
        and "extract_prefixed_zip(" in path.read_text(encoding="utf-8")
    ]
    assert callers == ["verified_managed_bundle.py"]
    backend = (platform_root / "managed_update_backend.py").read_text(encoding="utf-8")
    assert "VerifiedManagedBundleStager" in backend
