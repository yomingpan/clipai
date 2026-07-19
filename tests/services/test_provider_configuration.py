from ClipAI.core.models import ModelCatalogConnection, ProviderOption, ProviderSettingsInput
from ClipAI.providers.fake import FakeProvider
from ClipAI.services.provider_binding import ProviderExecutionBinding, ProviderRuntimeSnapshot
from ClipAI.services.provider_configuration import ProviderConfigurationCoordinator, ProviderConfigurationResult


class Backend:
    def __init__(self, snapshot: ProviderRuntimeSnapshot) -> None:
        self.snapshot = snapshot
        self.calls = []
        self.models = ("remote",)

    def reload(self):
        self.calls.append(("reload",))
        return self.snapshot

    def persist_provider(self, provider):
        self.calls.append(("provider", provider))
        return self.snapshot

    def persist_model(self, provider, model):
        self.calls.append(("model", provider, model))
        return self.snapshot

    def validate_save_and_build(self, settings):
        self.calls.append(("save", settings.provider))
        return self.snapshot

    def discover_models(self, provider, connection):
        self.calls.append(("refresh", provider, connection))
        return self.models


def make_coordinator():
    snapshot = ProviderRuntimeSnapshot(
        "openai",
        (
            ProviderExecutionBinding(FakeProvider(), "openai", "model"),
            ProviderExecutionBinding(FakeProvider(), "gemini", "gemini-model"),
        ),
        (
            ProviderOption("openai", "OpenAI", ("model", "new"), "model", True),
            ProviderOption("gemini", "Gemini", ("gemini-model",), "gemini-model", True),
        ),
    )
    backend = Backend(snapshot)
    return ProviderConfigurationCoordinator(snapshot, backend), backend


def test_save_gates_every_other_configuration_mutation() -> None:
    coordinator, backend = make_coordinator()
    work, update = coordinator.begin_save(ProviderSettingsInput("gemini", "gemini-model", "secret"), "save-1")

    assert work is not None
    assert update.settings_state.operation_kind == "save"
    assert coordinator.model_selection().configuration_pending is True
    assert coordinator.provider_selection().configuration_pending is True

    blocked = coordinator.select_model("openai", "new")
    assert blocked.error.message == "Provider configuration is busy."
    assert not any(call[0] == "model" for call in backend.calls)


def test_refresh_and_save_share_one_operation_identity() -> None:
    coordinator, _backend = make_coordinator()
    refresh, _ = coordinator.begin_refresh("openai", "refresh-1", ModelCatalogConnection())
    save, update = coordinator.begin_save(ProviderSettingsInput("gemini", "gemini-model", "secret"), "save-1")

    assert refresh is not None
    assert save is None
    assert update.settings_state.operation_id == "refresh-1"
    assert update.settings_state.operation_kind == "refresh"


def test_failure_keeps_the_operation_target_provider() -> None:
    coordinator, _backend = make_coordinator()
    coordinator.begin_save(ProviderSettingsInput("gemini", "gemini-model", "secret"), "save-1")

    update = coordinator.complete(ProviderConfigurationResult("save", "save-1", "gemini", error="bad key"))

    assert update.settings_state.selected_provider == "gemini"
    assert update.settings_state.operation_state == "failed"
    assert coordinator.active_binding.provider_id == "openai"


def test_late_completion_cannot_replace_a_new_operation() -> None:
    coordinator, _backend = make_coordinator()
    coordinator.begin_refresh("openai", "old", None)
    coordinator.complete(ProviderConfigurationResult("refresh", "old", "openai", models=("old",)))
    coordinator.begin_refresh("openai", "new", None)

    ignored = coordinator.complete(ProviderConfigurationResult("refresh", "old", "openai", models=("late",)))

    assert ignored.ignored is True
    assert coordinator.model_selection().available_models == ("model", "old")
    assert coordinator.model_selection().configuration_pending is True


def test_save_snapshot_preserves_discovered_catalog() -> None:
    coordinator, backend = make_coordinator()
    coordinator.begin_refresh("openai", "refresh", None)
    coordinator.complete(ProviderConfigurationResult("refresh", "refresh", "openai", models=("remote",)))
    fresh = ProviderRuntimeSnapshot(
        "openai",
        backend.snapshot.bindings,
        (
            ProviderOption("openai", "OpenAI", ("default",), "model", True),
            backend.snapshot.options[1],
        ),
    )
    coordinator.begin_save(ProviderSettingsInput("openai", "model", "secret"), "save")
    coordinator.complete(ProviderConfigurationResult("save", "save", "openai", snapshot=fresh))

    assert coordinator.model_selection().available_models == ("model", "remote")
