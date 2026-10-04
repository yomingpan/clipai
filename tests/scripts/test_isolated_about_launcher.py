import pytest
from experiments.first_install.launch_isolated_about import require_isolated_url


@pytest.mark.parametrize("url", ["http://updates.invalid/catalog.json", "https://u:p@updates.invalid/catalog.json",
    "https://github.com/yomingpan/clipai/releases/latest/download/catalog.json",
    "https://api.github.com/repos/yomingpan/clipai/releases", "https://updates.invalid/catalog.json#fragment"])
def test_isolated_about_rejects_production_or_credential_sources(url):
    with pytest.raises(ValueError):
        require_isolated_url(url)


def test_isolated_about_accepts_operator_owned_https_source():
    assert require_isolated_url("https://updates.invalid/acceptance/catalog.json") == "https://updates.invalid/acceptance/catalog.json"
