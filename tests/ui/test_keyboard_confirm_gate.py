import pytest

from ClipAI.ui.keyboard_confirm_gate import KeyboardConfirmGate


def test_external_enter_is_sampled_at_focus_before_first_delayed_repeat():
    now = [0.0]
    held = [True]
    gate = KeyboardConfirmGate(clock=lambda: now[0], key_down_reader=lambda: held[0])
    # No press event is delivered while the external App owns the keyboard.
    gate.focus_changed(True)
    now[0] = 1.0
    gate.press()  # first repeat delivered to the Popup after the settle window
    held[0] = False
    assert not gate.release()
    gate.press()
    assert gate.release()


def test_confirmation_requires_a_fresh_press_and_release_after_focus_settles():
    now = [0.0]
    gate = KeyboardConfirmGate(clock=lambda: now[0])
    gate.focus_changed(True)
    now[0] = .3
    gate.press()
    assert gate.release()
    assert not gate.release()


@pytest.mark.parametrize("case", ["before_focus", "too_early", "repeat", "modifier", "focus_left", "restart", "release_without_press"])
def test_unsafe_keyboard_sequences_never_confirm(case):
    now = [0.0]
    gate = KeyboardConfirmGate(clock=lambda: now[0])
    if case == "before_focus": gate.press()
    gate.focus_changed(True)
    now[0] = .299 if case == "too_early" else .4
    if case != "release_without_press": gate.press(state=4 if case == "modifier" else 0)
    if case == "repeat": gate.press()
    if case == "focus_left": gate.focus_changed(False)
    if case == "restart": gate.restart()
    now[0] = 1
    assert not gate.release()


@pytest.mark.parametrize("state", [0, 2, 8, 16, 26])
def test_lock_bits_are_the_only_accepted_modifier_bits(state):
    now = [0.0]
    gate = KeyboardConfirmGate(clock=lambda: now[0])
    gate.focus_changed(True)
    now[0] = .4
    gate.press(state=state)
    assert gate.release(state=state)
