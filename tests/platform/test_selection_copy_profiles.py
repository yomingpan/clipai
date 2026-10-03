from ClipAI.platform.selection_copy_profiles import (
    AccessibleControlIdentity,
    FocusRepairPlan,
    selection_source_policy,
)


ANKI_CARD = (
    AccessibleControlIdentity("QObject", "Qt"),
    AccessibleControlIdentity("MainWebView", "Qt"),
    AccessibleControlIdentity("QWidget", "Qt"),
    AccessibleControlIdentity("AnkiQt", "Qt"),
)
ANKI_MENU = (
    AccessibleControlIdentity("QMenuBar", "Qt"),
    AccessibleControlIdentity("AnkiQt", "Qt"),
)
ANKI_SHELL = (
    AccessibleControlIdentity("QWidget", "Qt"),
    AccessibleControlIdentity("AnkiQt", "Qt"),
)


def test_native_anki_identity_allows_card_focus_restore_and_card_copy():
    executable = r"C:\Program Files\Anki\anki.exe"

    assert selection_source_policy("anki", executable, ANKI_SHELL).focus_repair == FocusRepairPlan(
        AccessibleControlIdentity("MainWebView", "Qt"),
        focus_first_child=True,
    )
    assert selection_source_policy("anki", executable, ANKI_CARD).copy_selection_only


def test_version_variable_embedded_cpython_identity_is_verified():
    executable = (
        r"C:\Users\me\AppData\Local\AnkiProgramFiles\python"
        r"\cpython-3.13.7-windows-x86_64-none\pythonw.exe"
    )

    assert selection_source_policy("pythonw", executable, ANKI_SHELL).focus_repair is not None
    assert selection_source_policy("pythonw", executable, ANKI_CARD).copy_selection_only


def test_focus_restore_identity_rejects_broad_anki_or_python_matches():
    rejected = (
        ("pythonw", r"C:\Python313\pythonw.exe"),
        ("pythonw", r"C:\temp\anki\pythonw.exe"),
        ("pythonw", r"C:\AnkiProgramFiles\python\cpython-3.13.7-windows-amd64-none\pythonw.exe"),
        ("anki-helper", r"C:\Program Files\Anki\anki-helper.exe"),
        ("pythonw", r"C:\AnkiProgramFiles\python\cpython-3.13.7-windows-x86_64-none\python.exe"),
    )

    for process_name, executable in rejected:
        assert selection_source_policy(process_name, executable, ANKI_SHELL).focus_repair is None
        assert not selection_source_policy(process_name, executable, ANKI_CARD).copy_selection_only


def test_menu_and_editor_ancestry_cannot_authorize_focus_repair_or_copy():
    executable = r"C:\Program Files\Anki\anki.exe"

    menu_policy = selection_source_policy("anki", executable, ANKI_MENU)
    editor_policy = selection_source_policy(
        "anki",
        executable,
        (
            AccessibleControlIdentity("QObject", "Qt"),
            AccessibleControlIdentity("EditorWebView", "Qt"),
            AccessibleControlIdentity("AnkiQt", "Qt"),
        ),
    )

    assert menu_policy.focus_repair is None
    assert not menu_policy.copy_selection_only
    assert editor_policy.focus_repair is None
    assert not editor_policy.copy_selection_only
