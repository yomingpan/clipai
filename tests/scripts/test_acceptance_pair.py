import pytest

from experiments.first_install.prepare_acceptance_pair import require_newer_version


@pytest.mark.parametrize("b", ["3.7.8", "3.7.7", "3.7.8rc1", "03.7.9"])
def test_rebuild_downgrade_and_noncanonical_version_are_not_upgrade_evidence(b):
    with pytest.raises(ValueError):
        require_newer_version("3.7.8", b)


def test_real_newer_version_is_admitted():
    require_newer_version("3.7.8", "3.7.9")
