from scripts.probe_inline_pill_focus import focus_result


def test_focus_probe_requires_same_external_foreground_and_control_and_exact_intent():
    before = (123, 456)
    good = focus_result("Notepad", "raw", before, before, before, False)
    assert good["status"] == "pass"
    assert not good["content_recorded"]
    for shown, clicked, received in (((999, 456), before, False), (before, (123, 999), False), (before, before, True)):
        assert focus_result("Notepad", "raw", before, shown, clicked, received)["status"] == "fail"
    assert focus_result("Notepad", "raw", (123, 0), (123, 0), (123, 0), False)["status"] == "fail"
