# ADR-0006: NativeWindowSurface owns application-window OS facts

## Status

Accepted.

## Context

Popup code in `ui/base_dialog.py` independently resolved Tk child ids to
top-level HWNDs, read foreground ownership, changed task-switcher styles, and
activated or restored windows. `ui/window_icons.py` and `ui/pointer_input.py`
also reached Win32 directly. `platform/window_focus.py` already owned external
foreground observation for Paste targets, so UI had become a second source of
native window truth.

The existing layer import test only inspected package-qualified `ClipAI.*`
imports. Standard-library `ctypes` and `sys.platform` branches were invisible to
it even though the architecture document prohibited those dependencies.

## Decision

`core.ports.NativeWindowSurface` is the injected contract for application
window native operations: task-switcher hiding, activation, no-activate show,
foreground ownership, icon installation, and icon destruction. It receives a
toolkit child id; the adapter alone resolves the top-level native handle.

`WindowsNativeWindowSurface` implements the contract with Win32.
`HeadlessNativeWindowSurface` returns conservative answers. Both contain OS
failure and never raise through the port. `app/container.py` constructs and
injects the Windows adapter into the presenter and its dialogs.

Toolkit lifecycle remains in UI: `deiconify`, `withdraw`, `update_idletasks`,
`winfo_id`, and `focus_get`. UI also locates the packaged `clipai.ico` resource;
the platform adapter owns loading and destroying native icon handles. Native
pointer polling moves to a platform adapter behind `PointerPressReader`.

## Measurements

The supplied source audit counted 33 direct native uses across three UI files.
The deterministic AST regression loop on this revision reported seven forbidden
native imports and 13 explicit `sys.platform`/`windll` UI accesses before the
change. After migration both independent architecture tests pass, and the
focused architecture/platform/UI/container suite reports 156 passing tests in
4.41 s.

## Rejected alternatives

- Extending the old `ClipAI.*` import test would still obscure the native-owner
  rule inside a general failure message.
- Passing `user32` objects into UI helpers preserves duplicate ownership and
  lets UI continue interpreting HWNDs.
- Moving icon resource discovery to platform would make the OS adapter know UI
  package layout rather than only receiving an explicit path.
- Keeping a Windows pointer adapter in UI would satisfy the window port but
  leave the same boundary leak active through another input path.

## Consequences

- UI can project toolkit state without importing native Windows modules or
  branching on the operating system.
- Native foreground ownership has one application-window port; external Paste
  target observation remains the separate platform monitor capability.
- Headless behavior is explicit and conservative instead of an implicit fake
  Windows success.
- Adding another native module outside `platform/`, or another `sys.platform` /
  `windll` access inside UI, fails with a targeted architecture message.
