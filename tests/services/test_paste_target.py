from ClipAI.core.models import PasteTarget
from ClipAI.services.paste_target import PasteTargetCoordinator


class Presenter:
    def __init__(self) -> None:
        self.targets = []

    def present_paste_target(self, target) -> None:
        self.targets.append(target)


def target(sequence: int, handle: int = 10) -> PasteTarget:
    return PasteTarget(f"hwnd:{handle:x}", 42, "Notepad", "Untitled", sequence)


def test_latest_external_target_is_single_authoritative_projection() -> None:
    presenter = Presenter()
    coordinator = PasteTargetCoordinator(presenter)

    assert coordinator.observe(target(2, 20)) is True
    assert coordinator.observe(target(1, 10)) is False

    assert coordinator.current == target(2, 20)
    assert presenter.targets == [target(2, 20)]


def test_equal_observation_cannot_replace_current_target() -> None:
    coordinator = PasteTargetCoordinator()
    coordinator.observe(target(3, 10))

    assert coordinator.observe(target(3, 20)) is False
    assert coordinator.current == target(3, 10)
