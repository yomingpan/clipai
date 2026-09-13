from ClipAI.core.commands import CheckForManagedUpdate
from ClipAI.core.models import ManagedUpdatePresentation
from ClipAI.ui import about


class Widget:
    def __init__(self, _master=None, **kwargs) -> None:
        self.options = dict(kwargs)

    def grid(self, **_kwargs) -> None:
        pass

    def grid_columnconfigure(self, *_args, **_kwargs) -> None:
        pass

    def grid_rowconfigure(self, *_args, **_kwargs) -> None:
        pass

    def title(self, _value) -> None:
        pass

    def geometry(self, _value) -> None:
        pass

    def minsize(self, *_args) -> None:
        pass

    def protocol(self, *_args) -> None:
        pass

    def bind(self, *_args) -> None:
        pass

    def after(self, *_args) -> None:
        pass

    def configure(self, **kwargs) -> None:
        self.options.update(kwargs)

    def invoke(self) -> None:
        self.options["command"]()


def test_about_button_emits_typed_update_intent_and_projects_real_lifecycle(monkeypatch) -> None:
    for name in ("CTkToplevel", "CTkLabel", "CTkFrame", "CTkButton"):
        monkeypatch.setattr(about.ctk, name, Widget)
    monkeypatch.setattr(about.ctk, "CTkFont", lambda **_kwargs: object())
    monkeypatch.setattr(about.ctk, "CTkImage", lambda **_kwargs: object())
    monkeypatch.setattr(about, "create_tray_image", lambda **_kwargs: object())
    commands = []

    dialog = about.AboutDialog(
        object(),
        commands.append,
        object(),
        version="3.7.3",
        github_url="https://github.com/yomingpan/clipai",
        managed_update=ManagedUpdatePresentation(
            "idle", "可檢查 GitHub 上的正式穩定版本。", True
        ),
    )
    dialog._update_button.invoke()

    assert len(commands) == 1
    assert isinstance(commands[0], CheckForManagedUpdate)
    assert dialog._update_button.options["text"] == "檢查更新"

    dialog.set_managed_update(
        ManagedUpdatePresentation("checking", "正在檢查並準備更新…", False)
    )
    assert dialog._update_button.options["text"] == "正在檢查更新…"
    assert dialog._update_button.options["state"] == "disabled"
    assert dialog._update_status.options["text"] == "正在檢查並準備更新…"
