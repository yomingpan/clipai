import pytest
from experiments.first_install.launch_isolated_about import require_isolated_url
from experiments.first_install.launch_isolated_about import require_unredirected_shared_root


@pytest.mark.parametrize("url", ["http://updates.invalid/catalog.json", "https://u:p@updates.invalid/catalog.json",
    "https://github.com/yomingpan/clipai/releases/latest/download/catalog.json",
    "https://api.github.com/repos/yomingpan/clipai/releases", "https://updates.invalid/catalog.json#fragment"])
def test_isolated_about_rejects_production_or_credential_sources(url):
    with pytest.raises(ValueError):
        require_isolated_url(url)


def test_isolated_about_accepts_operator_owned_https_source():
    assert require_isolated_url("https://updates.invalid/acceptance/catalog.json") == "https://updates.invalid/acceptance/catalog.json"


def test_isolated_about_accepts_named_github_acceptance_release():
    url = "https://github.com/yomingpan/clipai/releases/download/acceptance-20261004/catalog.json"
    assert require_isolated_url(url) == url


@pytest.mark.parametrize("suffix", ["v3.7.9/catalog.json", "acceptance-20261004/catalog.json?token=value",
    "acceptance-20261004/not-catalog.json", "acceptance-20261004/catalog.json/extra"])
def test_isolated_github_entry_refuses_official_or_ambiguous_asset_paths(suffix):
    with pytest.raises(ValueError):
        require_isolated_url("https://github.com/yomingpan/clipai/releases/download/" + suffix)


def test_isolated_github_entry_refuses_other_repositories():
    with pytest.raises(ValueError):
        require_isolated_url("https://github.com/another/clipai/releases/download/acceptance-20261004/catalog.json")


def test_isolated_launcher_admits_unredirected_shared_paths(tmp_path):
    require_unredirected_shared_root(tmp_path)


def test_isolated_launcher_rejects_effective_path_redirection_before_app_start(tmp_path, monkeypatch):
    from pathlib import Path
    original = Path.resolve
    redirected = tmp_path / "managed-update"
    outside = tmp_path.parent / "virtualized-shared" / "managed-update"
    def resolve(path, *args, **kwargs):
        return outside if path == redirected else original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(RuntimeError, match="ordinary Windows PowerShell"):
        require_unredirected_shared_root(tmp_path)
