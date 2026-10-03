from ClipAI.ui.owned_dialog import OwnedDialogSlot


class Dialog:
    def __init__(self) -> None:
        self.closed = 0
        self.destroyed = 0

    def close(self) -> None:
        self.closed += 1

    def destroy(self) -> None:
        self.destroyed += 1


def test_slot_builds_once_updates_and_forgets_closed_dialog() -> None:
    built = []
    slot = OwnedDialogSlot(lambda: built.append(Dialog()) or built[-1])
    used = []

    assert slot.present(lambda dialog: used.append(dialog)) is True
    assert slot.present(lambda dialog: used.append(dialog)) is True
    assert built == [used[0]]
    assert slot.close(forget=True) is True
    assert slot.instance is None


def test_slot_ignores_use_when_factory_returns_none_and_destroys_owned_dialog() -> None:
    used = []
    assert OwnedDialogSlot(lambda: None).present(used.append) is False
    dialog = Dialog()
    slot = OwnedDialogSlot(lambda: dialog)
    slot.ensure()
    assert slot.destroy() is True
    assert dialog.destroyed == 1
    assert slot.instance is None
