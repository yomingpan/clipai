from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ClipAI.app.managed_update_handoff import ManagedUpdateHandoffExecutor
from ClipAI.app.runtime_managed_update import ManagedUpdatePresenter, ManagedUpdateRuntimeModule
from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.managed_install import ManagedUpdateClientIdentity
from ClipAI.platform.managed_release_source import HttpsManagedReleaseSource
from ClipAI.platform.managed_update_handoff import SubprocessManagedUpdateHandoff
from ClipAI.platform.managed_update_transport import UrllibManagedUpdateTransport
from ClipAI.services.managed_update_coordinator import ManagedUpdateCoordinator


PRODUCTION_MANAGED_UPDATE_CATALOG_URL = (
    "https://github.com/yomingpan/clipai/releases/latest/download/catalog.json"
)


@dataclass(frozen=True)
class ManagedUpdateRuntimeConfiguration:
    identity: ManagedUpdateClientIdentity
    launcher_python: Path
    launcher_entrypoint: Path
    base_python: Path
    environment: Mapping[str, str]
    catalog_url: str = PRODUCTION_MANAGED_UPDATE_CATALOG_URL


def build_managed_update_runtime(
    configuration: ManagedUpdateRuntimeConfiguration | None,
    *,
    supervisor: TaskSupervisor,
    enqueue: Callable[[object], None],
    presenter: ManagedUpdatePresenter,
    request_shutdown: Callable[[], None],
) -> ManagedUpdateRuntimeModule:
    if configuration is None:
        return ManagedUpdateRuntimeModule(
            executor=None,
            identity=None,
            supervisor=supervisor,
            enqueue=enqueue,
            presenter=presenter,
        )
    executor = ManagedUpdateHandoffExecutor(
        coordinator=ManagedUpdateCoordinator(
            release_source=HttpsManagedReleaseSource(
                catalog_url=configuration.catalog_url,
                transport=UrllibManagedUpdateTransport(),
            ),
            now=lambda: datetime.now(timezone.utc).isoformat(),
        ),
        handoff=SubprocessManagedUpdateHandoff(
            launcher_python=configuration.launcher_python,
            launcher_entrypoint=configuration.launcher_entrypoint,
            base_python=configuration.base_python,
            environment=configuration.environment,
        ),
        request_shutdown=request_shutdown,
    )
    return ManagedUpdateRuntimeModule(
        executor=executor,
        identity=configuration.identity,
        supervisor=supervisor,
        enqueue=enqueue,
        presenter=presenter,
    )
