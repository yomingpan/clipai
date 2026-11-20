from ClipAI.app.managed_update_composition import (
    PRODUCTION_MANAGED_UPDATE_CATALOG_URL,
    ManagedUpdateRuntimeConfiguration,
)


def test_production_catalog_is_the_public_github_release_asset() -> None:
    assert PRODUCTION_MANAGED_UPDATE_CATALOG_URL == (
        "https://github.com/yomingpan/clipai/releases/latest/download/catalog.json"
    )
    assert ManagedUpdateRuntimeConfiguration.__dataclass_fields__["catalog_url"].default == (
        PRODUCTION_MANAGED_UPDATE_CATALOG_URL
    )
