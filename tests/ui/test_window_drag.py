from types import SimpleNamespace

from ClipAI.ui.window_drag import WindowDragController


def test_window_drag_binds_header_and_moves_from_the_press_offset() -> None:
    class Window:
        def __init__(self) -> None:
            self.geometry_calls: list[str] = []

        def winfo_x(self) -> int:
            return 100

        def winfo_y(self) -> int:
            return 60

        def geometry(self, value: str) -> None:
            self.geometry_calls.append(value)

    class Header:
        def __init__(self) -> None:
            self.bindings = {}

        def bind(self, event_name, callback, add=None) -> None:
            self.bindings[event_name] = (callback, add)

    window = Window()
    header = Header()
    drag = WindowDragController(window)
    drag.bind(header)

    assert set(header.bindings) == {"<ButtonPress-1>", "<B1-Motion>"}
    assert all(add == "+" for _callback, add in header.bindings.values())

    header.bindings["<ButtonPress-1>"][0](
        SimpleNamespace(x_root=130, y_root=90)
    )
    header.bindings["<B1-Motion>"][0](
        SimpleNamespace(x_root=200, y_root=160)
    )

    assert window.geometry_calls == ["+170+130"]
