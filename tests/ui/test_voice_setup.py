from __future__ import annotations

from ClipAI.core.commands import RetryVoiceInputSetup
from ClipAI.core.voice import VoiceCapabilityPhase, VoiceProjection
from ClipAI.ui.voice_setup import VoiceSetupDialog


class Widget:
    def __init__(self) -> None:
        self.configurations: list[dict[str, object]] = []

    def configure(self, **kwargs: object) -> None:
        self.configurations.append(kwargs)


class Dialog:
    def winfo_exists(self) -> bool:
        return True


def test_blocked_setup_offers_an_explicit_profile_repair_and_retry() -> None:
    commands: list[object] = []
    setup = VoiceSetupDialog.__new__(VoiceSetupDialog)
    setup._command_sink = commands.append
    setup._dialog = Dialog()
    setup._status = Widget()
    setup._enable_button = Widget()

    setup.set_voice_projection(VoiceProjection(VoiceCapabilityPhase.PERMISSION_BLOCKED, "zh-TW"))

    options = setup._enable_button.configurations[-1]
    assert options["text"] == "Reset & try again"
    assert callable(options["command"])
    options["command"]()
    assert isinstance(commands[-1], RetryVoiceInputSetup)
