from ClipAI.platform.selection_copy_profiles import (
    AccessibleControlIdentity,
    supports_card_focus_restore,
    supports_selection_only_copy,
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


def test_native_anki_identity_allows_card_focus_restore_and_card_copy():
    executable = r"C:\Program Files\Anki\anki.exe"

    assert supports_card_focus_restore("anki", executable, ANKI_MENU)
    assert supports_selection_only_copy("anki", executable, ANKI_CARD)


def test_version_variable_embedded_cpython_identity_is_verified():
    executable = (
        r"C:\Users\me\AppData\Local\AnkiProgramFiles\python"
        r"\cpython-3.13.7-windows-x86_64-none\pythonw.exe"
    )

    assert supports_card_focus_restore("pythonw", executable, ANKI_MENU)
    assert supports_selection_only_copy("pythonw", executable, ANKI_CARD)


def test_focus_restore_identity_rejects_broad_anki_or_python_matches():
    rejected = (
        ("pythonw", r"C:\Python313\pythonw.exe"),
        ("pythonw", r"C:\temp\anki\pythonw.exe"),
        ("pythonw", r"C:\AnkiProgramFiles\python\cpython-3.13.7-windows-amd64-none\pythonw.exe"),
        ("anki-helper", r"C:\Program Files\Anki\anki-helper.exe"),
        ("pythonw", r"C:\AnkiProgramFiles\python\cpython-3.13.7-windows-x86_64-none\python.exe"),
    )

    for process_name, executable in rejected:
        assert not supports_card_focus_restore(process_name, executable, ANKI_MENU)
        assert not supports_selection_only_copy(process_name, executable, ANKI_CARD)


def test_copy_trust_still_requires_focused_main_webview_ancestry():
    executable = r"C:\Program Files\Anki\anki.exe"

    assert supports_card_focus_restore("anki", executable, ANKI_MENU)
    assert not supports_selection_only_copy("anki", executable, ANKI_MENU)
    assert not supports_selection_only_copy(
        "anki",
        executable,
        (
            AccessibleControlIdentity("QObject", "Qt"),
            AccessibleControlIdentity("EditorWebView", "Qt"),
            AccessibleControlIdentity("AnkiQt", "Qt"),
        ),
    )
