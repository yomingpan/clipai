from __future__ import annotations

from ClipAI.core.ports import ApplicationInstanceGate
from ClipAI.platform.application_instance import WindowsApplicationInstanceGate


APPLICATION_INSTANCE_NAME = "Local\\ClipAI.DesktopRuntime"


def build_application_instance_gate() -> ApplicationInstanceGate:
    return WindowsApplicationInstanceGate(APPLICATION_INSTANCE_NAME)
