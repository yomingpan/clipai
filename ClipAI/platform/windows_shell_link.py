"""Stateless, isolated Unicode Shell Link worker; only Windows and stdlib APIs."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import json
from pathlib import Path
import sys
import uuid


class _Guid(ctypes.Structure):
    _fields_ = [('data1', ctypes.c_uint32), ('data2', ctypes.c_uint16),
                ('data3', ctypes.c_uint16), ('data4', ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, value: str) -> '_Guid':
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


@dataclass(frozen=True)
class _ShortcutIntent:
    path: Path
    target: Path
    arguments: str
    icon: Path
    create: bool

    @classmethod
    def parse(cls, data: object) -> '_ShortcutIntent':
        if not isinstance(data, dict) or set(data) != {'path', 'target', 'arguments', 'icon', 'create'}:
            raise ValueError('invalid shortcut request')
        if type(data['create']) is not bool or any(
                not isinstance(data[key], str) or '\0' in data[key]
                for key in ('path', 'target', 'arguments', 'icon')):
            raise ValueError('invalid shortcut request values')
        paths = [Path(data[key]) for key in ('path', 'target', 'icon')]
        if not all(path.is_absolute() for path in paths):
            raise ValueError('shortcut paths must be absolute')
        return cls(paths[0], paths[1], data['arguments'], paths[2], data['create'])


def _read_batch(request: Path) -> tuple[_ShortcutIntent, ...]:
    data = json.loads(request.read_text(encoding='utf-8'))
    if not isinstance(data, list) or not 1 <= len(data) <= 3:
        raise ValueError('one bounded shortcut phase is required')
    intents = tuple(_ShortcutIntent.parse(item) for item in data)
    if len({intent.create for intent in intents}) != 1:
        raise ValueError('shortcut phases must not be mixed')
    if len({str(intent.path.resolve()).casefold() for intent in intents}) != len(intents):
        raise ValueError('duplicate shortcut paths')
    return intents


class _ShellLink:
    """Balance this apartment and both interface references on every exit."""

    def __init__(self) -> None:
        self.link, self.persist = ctypes.c_void_p(), ctypes.c_void_p()
        self.initialized = False
        self.ole = ctypes.WinDLL('ole32')
        self.ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        self.ole.CoInitializeEx.restype = ctypes.c_long
        self.ole.CoUninitialize.argtypes = []
        self.ole.CoUninitialize.restype = None
        self.ole.CoCreateInstance.argtypes = [ctypes.POINTER(_Guid), ctypes.c_void_p,
            wintypes.DWORD, ctypes.POINTER(_Guid), ctypes.POINTER(ctypes.c_void_p)]
        self.ole.CoCreateInstance.restype = ctypes.c_long
        try:
            status = self.ole.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED
            self._check(status)
            self.initialized = True
            class_id = _Guid.parse('00021401-0000-0000-C000-000000000046')
            interface_id = _Guid.parse('000214F9-0000-0000-C000-000000000046')
            self._check(self.ole.CoCreateInstance(ctypes.byref(class_id), None, 1,
                ctypes.byref(interface_id), ctypes.byref(self.link)))
            persist_id = _Guid.parse('0000010B-0000-0000-C000-000000000046')
            self.call(self.link, 0, (ctypes.POINTER(_Guid), ctypes.POINTER(ctypes.c_void_p)),
                      ctypes.byref(persist_id), ctypes.byref(self.persist))
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _check(status: int) -> None:
        if status < 0:
            raise RuntimeError(f'shortcut_integration_failed:0x{status & 0xffffffff:08x}')

    @staticmethod
    def _method(pointer: ctypes.c_void_p, index: int, types: tuple, result=ctypes.c_long):
        if not pointer.value:
            raise RuntimeError('shortcut_integration_failed:null_interface')
        table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(result, ctypes.c_void_p, *types)(table[index])

    def call(self, pointer: ctypes.c_void_p, index: int, types: tuple, *values) -> None:
        self._check(self._method(pointer, index, types)(pointer, *values))

    def close(self) -> None:
        try:
            for pointer in (self.persist, self.link):
                if pointer.value:
                    self._method(pointer, 2, (), wintypes.ULONG)(pointer)
                    pointer.value = None
        finally:
            if self.initialized:
                self.ole.CoUninitialize()
                self.initialized = False


def _apply(intent: _ShortcutIntent) -> None:
    # Vtable slots are the Microsoft SDK IShellLinkW and IPersistFile ABI.
    native = _ShellLink()
    try:
        if intent.create:
            native.call(native.link, 20, (wintypes.LPCWSTR,), str(intent.target))
            native.call(native.link, 11, (wintypes.LPCWSTR,), intent.arguments)
            native.call(native.link, 17, (wintypes.LPCWSTR, ctypes.c_int), str(intent.icon), 0)
            native.call(native.link, 9, (wintypes.LPCWSTR,), str(intent.target.parent))
            native.call(native.persist, 6, (wintypes.LPCWSTR, wintypes.BOOL), str(intent.path), True)
        else:
            native.call(native.persist, 5, (wintypes.LPCWSTR, wintypes.DWORD), str(intent.path), 0)
            target, arguments = ctypes.create_unicode_buffer(32768), ctypes.create_unicode_buffer(32768)
            native.call(native.link, 3, (wintypes.LPWSTR, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD),
                        target, len(target), None, 4)  # SLGP_RAWPATH; never Resolve a target.
            native.call(native.link, 10, (wintypes.LPWSTR, ctypes.c_int), arguments, len(arguments))
            if not target.value or Path(target.value).resolve() != intent.target.resolve() or arguments.value != intent.arguments:
                raise RuntimeError('shortcut_integration_failed:ownership_changed')
    finally:
        native.close()


def main() -> int:
    if len(sys.argv) != 2:
        raise ValueError('one explicit shortcut request is required')
    try:
        # Admit the entire phase before any COM call or native mutation.
        for intent in _read_batch(Path(sys.argv[1])):
            _apply(intent)
    except Exception as error:
        # No paths, arguments, environment or request contents in diagnostics.
        print(f'shortcut_integration_failed:{type(error).__name__}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
