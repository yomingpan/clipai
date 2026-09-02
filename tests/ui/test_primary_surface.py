from __future__ import annotations

from ClipAI.core.models import EntryPanelSnapshot, PopupBounds
from ClipAI.ui.primary_surface import PrimarySurfaceHost, PrimarySurfaceSpec
from ClipAI.ui.result_dialog import ResultDialogPresenter, _PrimaryEntrySurface, _SessionView


class Window:
    def __init__(self) -> None:
        self.events: list[object] = []
        self._geometry = "400x336+20+30"
        self._jobs = 0

    def withdraw(self): self.events.append("withdraw")
    def title(self, value): self.events.append(("title", value))
    def geometry(self, value=None):
        if value is not None:
            self._geometry = (
                f"{self._geometry.split('+', 1)[0]}{value}"
                if value.startswith("+")
                else value
            )
            self.events.append(("geometry", value))
        return self._geometry
    def minsize(self, width, height): self.events.append(("minsize", width, height))
    def configure(self, **kwargs): self.events.append(("configure", kwargs))
    def overrideredirect(self, value): self.events.append(("frameless", value))
    def attributes(self, *args): self.events.append(("attributes", args))
    def update_idletasks(self): self.events.append("update")
    def after_idle(self, callback): self.idle_callback = callback
    def deiconify(self): self.events.append("deiconify")
    def winfo_id(self): return 17
    def after(self, _delay, callback):
        self._jobs += 1
        return f"job-{self._jobs}"
    def after_cancel(self, job): self.events.append(("cancel", job))
    def destroy(self): self.events.append("destroy")
    def lift(self): self.events.append("lift")
    def focus_force(self): self.events.append("focus")
    def focus_get(self): return self
    def winfo_toplevel(self): return self
    def winfo_x(self): return 20
    def winfo_y(self): return 30


class Native:
    def __init__(self) -> None:
        self.hidden = []
    def hide_from_task_switcher(self, child_id): self.hidden.append(child_id); return True
    def activate(self, _child_id): return True
    def show_without_activation(self, _child_id): return True
    def owns_foreground(self, _child_id): return True


class View:
    def __init__(self, *, mount_result=True) -> None:
        self.events = []
        self.mount_result = mount_result
    def mount_primary_content(self): self.events.append("mount"); return self.mount_result
    def unmount_primary_content(self): self.events.append("unmount")


def make_host():
    window = Window()
    native = Native()
    host = PrimarySurfaceHost(
        object(),
        PrimarySurfaceSpec(PopupBounds(20, 30, 400, 336)),
        native,
        window_factory=lambda _master: window,
        dpi_resampler=lambda value: value.events.append("dpi"),
    )
    return host, window, native


def test_host_owns_one_shell_geometry_dpi_and_native_registration() -> None:
    host, window, native = make_host()
    lease = host.acquire()
    view = View()

    assert host.mount(lease, view) is True
    assert host.show(lease) is True
    window.idle_callback()

    assert window.events.count(("geometry", "400x336+20+30")) == 1
    assert window.events.count("dpi") == 1
    assert window.events.count("deiconify") == 1
    assert native.hidden == [17]
    assert host.current_bounds() == PopupBounds(20, 30, 400, 336)


def test_replace_is_identity_matched_and_rolls_back_mount_failure() -> None:
    host, _window, _native = make_host()
    first_lease = host.acquire()
    next_lease = host.acquire()
    first = View()
    failed = View(mount_result=False)
    host.mount(first_lease, first)

    assert host.replace(next_lease, first_lease, failed) is False
    assert first.events == ["mount"]
    assert host.replace(first_lease, next_lease, failed) is False
    assert first.events == ["mount", "unmount", "mount"]


def test_replace_and_restore_keep_the_same_window_shell() -> None:
    host, window, _native = make_host()
    first_lease = host.acquire()
    next_lease = host.acquire()
    first = View()
    second = View()
    host.mount(first_lease, first)

    assert host.replace(first_lease, next_lease, second) is True
    assert host.restore(next_lease) is True
    assert first.events == ["mount", "unmount", "mount"]
    assert second.events == ["mount", "unmount"]
    assert window.events.count(("geometry", "400x336+20+30")) == 1


def test_only_the_mounted_lease_can_show_or_close_the_host() -> None:
    host, window, _native = make_host()
    lease = host.acquire()
    stale = host.acquire()
    host.mount(lease, View())

    assert host.show(stale) is False
    assert host.close(stale) is False
    assert host.close(lease) is True
    assert host.close(lease) is False
    assert window.events[-1] == "destroy"


def test_host_owns_drag_and_resize_for_every_mounted_view() -> None:
    class Handle:
        def __init__(self): self.bindings = {}
        def bind(self, sequence, callback, add=None): self.bindings[sequence] = (callback, add)

    host, window, _native = make_host()
    first = Handle()
    second = Handle()

    host.bind_drag(first)
    host.bind_drag(second)
    start = type("Event", (), {"x_root": 50, "y_root": 60})()
    move = type("Event", (), {"x_root": 80, "y_root": 90})()
    first.bindings["<ButtonPress-1>"][0](start)
    second.bindings["<B1-Motion>"][0](move)
    host.resize(460, 350)

    assert ("geometry", "+50+60") in window.events
    assert window.events[-1] == ("geometry", "460x350+50+60")


def test_result_presenter_builds_existing_popup_content_in_primary_host(monkeypatch) -> None:
    events = []

    class Metrics:
        def current(self):
            return object()

    class Layout:
        def calculate(self, _metrics):
            return PopupBounds(40, 50, 420, 350)

    class Host:
        def __init__(self, root, spec, native):
            events.append(("host", root, spec.bounds, native))
        def acquire(self):
            events.append("acquire")
            return "lease"

    class Dialog:
        def __init__(self, **kwargs):
            events.append(("dialog", kwargs))
        def show(self):
            events.append("show")
            return True

    class Surface:
        def __init__(self, dialog):
            events.append(("surface", dialog))
        def configure_standard_actions(self):
            events.append("actions")

    monkeypatch.setattr("ClipAI.ui.result_dialog.PrimarySurfaceHost", Host)
    monkeypatch.setattr("ClipAI.ui.result_dialog.BaseDialog", Dialog)
    monkeypatch.setattr("ClipAI.ui.result_dialog.BaseResultSurface", Surface)
    presenter = ResultDialogPresenter.__new__(ResultDialogPresenter)
    presenter._root = "tk-root"
    presenter._display_metrics = Metrics()
    presenter._layout_policy = Layout()
    presenter._native_window_surface = "native"

    presenter._create_view("workflow-1")

    dialog_kwargs = next(value[1] for value in events if isinstance(value, tuple) and value[0] == "dialog")
    assert events[0] == (
        "host",
        "tk-root",
        PopupBounds(40, 50, 420, 350),
        "native",
    )
    assert dialog_kwargs["primary_surface_host"].__class__ is Host
    assert dialog_kwargs["primary_surface_lease"] == "lease"
    assert dialog_kwargs["show_on_create"] is False
    assert events.index("actions") < events.index("show")


def test_entry_panel_replaces_and_restores_existing_result_in_same_host(monkeypatch) -> None:
    events = []

    class Host:
        def acquire(self): events.append("acquire"); return "panel-lease"
        def replace(self, active, replacement, view): events.append(("replace", active, replacement, view)); return True
        def restore(self, active): events.append(("restore", active)); return True
        def close(self, lease=None): events.append(("close-host", lease)); return True

    class ResultDialog:
        primary_surface_host = Host()
        primary_surface_lease = "result-lease"

    class Panel:
        def __init__(self, *args, **kwargs):
            self.panel_id = None
            events.append(("panel", kwargs["primary_surface_host"], kwargs["primary_surface_lease"]))
        def apply(self, snapshot): self.panel_id = snapshot.panel_id; events.append("apply")
        def reveal(self): events.append("focus-panel")
        def presents(self, panel_id): return panel_id == self.panel_id
        def close(self): events.append("close-panel")

    monkeypatch.setattr("ClipAI.ui.result_dialog.UnifiedEntryPanelDialog", Panel)
    presenter = ResultDialogPresenter.__new__(ResultDialogPresenter)
    presenter._root = "root"
    presenter._command_sink = lambda _command: None
    presenter._native_window_surface = "native"
    presenter._display_metrics = object()
    presenter._layout_policy = object()
    presenter._entry_panel_dialog = None
    presenter._primary_entry_surface = None
    held_view = _SessionView(ResultDialog(), object())
    presenter._shortcut_guide_focus_return = ("workflow-1", held_view)
    presenter._hold_focus_for_owned_surface = lambda: None
    presenter._owned_popup_bounds = lambda: PopupBounds(10, 20, 400, 336)
    presenter._restore_focus_after_owned_surface = lambda: events.append("restore-focus")

    presenter.present_entry_panel(EntryPanelSnapshot("panel-1", "root"))
    presenter.transition_entry_panel_to_popup("panel-1", "workflow-1")

    assert presenter._primary_entry_surface.workflow_id == "workflow-1"
    assert events[0:4] == [
        "acquire",
        ("panel", held_view.dialog.primary_surface_host, "panel-lease"),
        "apply",
        ("replace", "result-lease", "panel-lease", presenter._entry_panel_dialog),
    ]

    presenter.present_entry_panel(None)

    assert ("restore", "panel-lease") in events
    assert "close-host" not in events
    assert events[-2:] == ["close-panel", "restore-focus"]


def test_accepted_action_mounts_result_before_releasing_panel_state() -> None:
    events = []

    class Host:
        def replace(self, active, replacement, view):
            events.append(("replace", active, replacement, view))
            return True

    class Panel:
        def close(self): events.append("panel:closed")

    class ResultDialog:
        def __init__(self, host):
            self.primary_surface_host = host
            self.primary_surface_lease = "result-lease"

    class Control:
        def observe_focus(self, event): events.append(type(event).__name__)

    host = Host()
    panel = Panel()
    transition = _PrimaryEntrySurface(panel, host, "panel-lease", "workflow-1")
    view = _SessionView(ResultDialog(host), object())
    presenter = ResultDialogPresenter.__new__(ResultDialogPresenter)
    presenter._entry_panel_dialog = panel
    presenter._primary_entry_surface = transition
    presenter._restore_focus_after_owned_surface = lambda: events.append("focus:released")
    presenter._popup_control = lambda _workflow, _view: Control()
    presenter._schedule_initial_focus = lambda workflow, _view: events.append(("focus", workflow))

    assert presenter._complete_primary_entry_transition(
        "workflow-1", view, transition
    ) is True

    assert events == [
        ("replace", "panel-lease", "result-lease", view.dialog),
        "panel:closed",
        "focus:released",
        "PopupControlShown",
        ("focus", "workflow-1"),
    ]
    assert presenter._entry_panel_dialog is None
    assert presenter._primary_entry_surface is None


def test_m0_failed_result_replacement_keeps_the_entry_panel_mounted() -> None:
    events = []

    class Host:
        def replace(self, active, replacement, view):
            events.append(("replace", active, replacement, view))
            return False

    class Panel:
        def close(self):
            events.append("panel:closed")

    class ResultDialog:
        def __init__(self, host):
            self.primary_surface_host = host
            self.primary_surface_lease = "result-lease"

    host = Host()
    panel = Panel()
    transition = _PrimaryEntrySurface(panel, host, "panel-lease", "workflow-1")
    view = _SessionView(ResultDialog(host), object())
    presenter = ResultDialogPresenter.__new__(ResultDialogPresenter)
    presenter._entry_panel_dialog = panel
    presenter._primary_entry_surface = transition

    assert presenter._complete_primary_entry_transition(
        "workflow-1", view, transition
    ) is False

    assert events == [
        ("replace", "panel-lease", "result-lease", view.dialog),
    ]
    assert presenter._entry_panel_dialog is panel
    assert presenter._primary_entry_surface is transition
