"""Owned Windows selection evidence: auto adapters or attended physical keys.

Auto never injects keys. Attended observes the application's existing capture log.
JSONL contains metadata and SHA-256 only; exit 0/1/2/3 = pass/fail/arguments/blocked.
"""
from __future__ import annotations

import argparse
import errno
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import random
import re
import statistics
import subprocess
import sys
import tempfile
import time

from ClipAI.app.application_lifecycle import APPLICATION_INSTANCE_NAME
from ClipAI.core.models import ExternalWindowRef
from ClipAI.core.state import CancellationToken
from ClipAI.platform.clipboard import SystemClipboard
from ClipAI.platform.external_window import SystemExternalWindowActivator
from ClipAI.platform.selection_uia import WindowsSelectionProbe
from ClipAI.services.clipboard_transaction import ClipboardTransactionCoordinator
from ClipAI.services.selection_capture import SelectionCaptureCoordinator
from ClipAI.support.statistics import percentile

ROOT = Path(__file__).resolve().parents[1]
AUTO_STATES = ('selected', 'modifier_held', 'caret_only', 'focus_moved', 'unsupported_control')
ATTENDED_STATES = ('selected', 'modifier_held', 'held_after_open', 'caret_only')
_DIRECTIONS = {
    'selected': 'Press physical Alt for 0.5 seconds, then release. Close the panel with Esc.',
    'modifier_held': 'Hold physical Alt for at least 2 seconds. Then release and close with Esc.',
    'held_after_open': 'Hold physical Alt until the panel opens, keep holding another 2 seconds, then release and close with Esc.',
    'caret_only': 'No text is selected. Hold physical Alt for 0.5 seconds, then release and close with Esc.',
}
_CAPTURE_LOG = re.compile(
    r'Selection capture operation_id=\S+ target=(\S+) status=(\S+) reason=(.*?) '
    r'strategy=(.*?) focus_restored=(True|False) elapsed_ms=(\d+)\s*$'
)


class ClipboardUnavailableError(RuntimeError):
    pass


class EnvironmentBlockedError(RuntimeError):
    pass


def retry_clipboard(work, *, wait=time.sleep):
    for attempt in range(20):
        try:
            return work()
        except OSError as error:
            if str(error) != 'Clipboard is busy':
                raise
            if attempt == 19:
                raise ClipboardUnavailableError('Clipboard is busy') from error
            wait(.25)


class _RetryingClipboard:
    def __init__(self):
        self.native = SystemClipboard()
        self.writes = 0
        self.last_owned_sequence = None

    def snapshot(self): return retry_clipboard(self.native.snapshot)
    def read_text(self): return retry_clipboard(self.native.read_text)
    def sequence_number(self): return retry_clipboard(self.native.sequence_number)

    def write_transient_text(self, text):
        retry_clipboard(lambda: self.native.write_transient_text(text))
        self.writes += 1
        self.last_owned_sequence = self.sequence_number()

    def restore_if_unchanged(self, snapshot, expected_sequence):
        # No-op restoration preserves the sequence when this harness never wrote.
        if self.sequence_number() != expected_sequence:
            return False
        if fingerprint(self.snapshot()) == fingerprint(snapshot):
            return True
        restored = retry_clipboard(lambda: self.native.restore_if_unchanged(snapshot, expected_sequence))
        if restored:
            self.last_owned_sequence = self.sequence_number()
        return restored


def fingerprint(snapshot):
    digest = hashlib.sha256()
    for item in sorted(snapshot.formats, key=lambda value: value.format_id):
        digest.update(item.format_id.to_bytes(4, 'little'))
        digest.update(len(item.data).to_bytes(8, 'little'))
        digest.update(item.data)
    return digest.hexdigest()


@dataclass(frozen=True)
class EnvironmentFacts:
    windows: bool
    interactive: bool
    elevated: bool
    application_running: bool


def environment_facts():
    if os.name != 'nt':
        return EnvironmentFacts(False, False, False, False)
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    user32.OpenInputDesktop.restype = wintypes.HANDLE
    user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    user32.CloseDesktop.restype = wintypes.BOOL
    desktop = user32.OpenInputDesktop(0, False, 0x0100)
    interactive = bool(desktop)
    if desktop:
        user32.CloseDesktop(desktop)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.OpenMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    mutex = kernel32.OpenMutexW(0x00100000, False, APPLICATION_INSTANCE_NAME)
    running = bool(mutex)
    if mutex:
        kernel32.CloseHandle(mutex)
    return EnvironmentFacts(True, interactive, bool(ctypes.windll.shell32.IsUserAnAdmin()), running)


def _environment_reason(mode, facts):
    if not facts.windows: return 'windows_required'
    if not facts.interactive: return 'interactive_desktop_required'
    if facts.elevated: return 'elevated_harness'
    if mode == 'attended' and not facts.application_running: return 'application_not_running'
    return ''


@dataclass(frozen=True)
class CaptureRecord:
    status: str
    reason: str
    strategy: str
    focus_restored: bool
    elapsed_ms: float


def expected_for_state(state):
    if state in ('selected', 'modifier_held', 'held_after_open'): return ('selected', '')
    if state == 'caret_only': return ('none', 'uia_caret_only')
    if state == 'focus_moved': return ('unknown', 'source_changed')
    if state == 'unsupported_control': return ('unknown', 'uia_unsupported')
    raise ValueError('unknown controlled state')


def read_attended_capture(path, offset, window_token, *, timeout_sec=15, monotonic=time.monotonic, wait=time.sleep):
    deadline, pending = monotonic() + timeout_sec, b''
    while monotonic() < deadline:
        try:
            with path.open('rb') as stream:
                if path.stat().st_size < offset:
                    offset, pending = 0, b''
                stream.seek(offset)
                data = stream.read()
                offset = stream.tell()
        except FileNotFoundError:
            data = b''
        pending += data
        lines = pending.split(b'\n')
        pending = lines.pop()
        for line in lines:
            match = _CAPTURE_LOG.search(line.decode('utf-8', errors='replace'))
            if match is not None and match[1] == window_token:
                return CaptureRecord(match[2], match[3], match[4], match[5] == 'True', int(match[6])), offset
        wait(.1)
    return None, offset


def case_record(state, capture, *, before, after, text_match, writes=0):
    expected = expected_for_state(state)
    status, reason = (capture.status, capture.reason) if capture else ('unknown', 'no_capture_logged')
    preserved = before == after
    return {
        'schema': 1, 'gate': 'selection-desktop-case', 'state': state,
        'status': status, 'reason': reason, 'strategy': capture.strategy if capture else '',
        'elapsed_ms': capture.elapsed_ms if capture else None,
        'focus_restored': capture.focus_restored if capture else False,
        'clipboard_before_sha256': before, 'clipboard_after_sha256': after,
        'clipboard_preserved': preserved, 'clipboard_writes': writes, 'text_match': text_match,
        'unknown_as_none': expected[0] == 'unknown' and status == 'none',
        'no_capture_logged': capture is None, 'content_recorded': False, 'device_evidence': True,
        'passed': (status, reason) == expected and preserved and text_match is not False and writes == 0,
    }


def summarize(mode, records, rounds, *, warmup_verified):
    elapsed = [record['elapsed_ms'] for record in records if record['elapsed_ms'] is not None]
    states = AUTO_STATES if mode == 'auto' else ATTENDED_STATES
    cases, passed = len(records), sum(record['passed'] for record in records)
    latencies = {
        'p50': round(statistics.median(elapsed), 3) if elapsed else None,
        'p90': round(percentile(elapsed, .9), 3) if elapsed else None,
        'p95': round(percentile(elapsed, .95), 3) if elapsed else None,
    }
    performance = bool(elapsed) and (mode != 'auto' or (latencies['p50'] <= 50 and latencies['p95'] <= 130))
    state_counts = {state: {
        'cases': sum(record['state'] == state for record in records),
        'selected': sum(record['state'] == state and record['status'] == 'selected' for record in records),
        'passed': sum(record['state'] == state and record['passed'] for record in records),
    } for state in states}
    return {
        'schema': 1, 'gate': 'selection-desktop-summary', 'mode': mode,
        'cases': cases, 'requested_cases': rounds * len(states), 'passed_cases': passed,
        'status': 'completed', 'warmup_verified': warmup_verified, 'latency_ms': latencies,
        'state_counts': state_counts, 'reason_histogram': dict(sorted(Counter(record['reason'] for record in records).items())),
        'clipboard_preserved': sum(record['clipboard_preserved'] for record in records),
        'unknown_as_none': sum(record['unknown_as_none'] for record in records),
        'no_capture_logged': sum(record['no_capture_logged'] for record in records),
        'content_recorded': False, 'device_evidence': True,
        'acceptance_covered': cases >= (100 if mode == 'auto' else 20),
        'passed': passed == cases == rounds * len(states) and performance and warmup_verified,
    }


class _OwnedHost:
    def __init__(self):
        temporary_root = (ROOT / '.clipai-test-artifacts').resolve()
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='selection-desktop-', dir=temporary_root)
        self.directory = Path(self.temporary.name).resolve()
        if not self.directory.is_relative_to(temporary_root):
            raise RuntimeError('host workspace escaped temporary root')
        self.command = self.directory / 'command.json'
        self.ready = self.directory / 'ready.json'
        self.sequence = 0
        self.process = subprocess.Popen(
            [getattr(sys, '_base_executable', sys.executable), str(Path(__file__).resolve()), '--host', str(self.command), str(self.ready)],
            cwd=ROOT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            env={**os.environ, 'PYTHONPATH': os.pathsep.join([str(ROOT)] + [str(Path(p).resolve()) for p in sys.path if p])},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def configure(self, state, instruction=''):
        self.sequence += 1
        # Immutable per-request files avoid Windows replacement/read sharing races.
        command = self.command.with_name(f'command-{self.sequence}.json')
        ready = self.ready.with_name(f'ready-{self.sequence}.json')
        _atomic_json(command, {'sequence': self.sequence, 'state': state, 'instruction': instruction})
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise EnvironmentBlockedError('host_exited')
            try:
                payload = json.loads(ready.read_text(encoding='utf-8'))
                if payload['sequence'] == self.sequence:
                    return payload
            except (FileNotFoundError, json.JSONDecodeError):
                pass
            except PermissionError as error:
                # Windows can briefly deny opening a just-published IPC file.
                # This bounded host poll never broadens clipboard retry policy.
                if error.errno != errno.EACCES or error.filename != str(ready):
                    raise
            time.sleep(.01)
        raise EnvironmentBlockedError('host_not_ready')

    def close(self):
        if self.process.poll() is None:
            self.sequence += 1
            _atomic_json(self.command.with_name(f'command-{self.sequence}.json'), {'sequence': self.sequence, 'state': 'shutdown'})
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        # This resolved path was verified inside the task workspace at creation.
        self.temporary.cleanup()


def _atomic_json(path, payload):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload), encoding='utf-8')
    temporary.replace(path)


class _ReadOnlyAdapter:
    def __init__(self): self.held = False
    def modifier_is_pressed(self, key): return self.held and key == 'alt'
    def copy_selection(self): raise AssertionError('controlled UIA host must never receive copy')


def run_loop(mode, rounds, seed, log_path, emit):
    clipboard = _RetryingClipboard()
    original = clipboard.snapshot()
    original_sequence = clipboard.sequence_number()
    host, probe = None, WindowsSelectionProbe()
    records, warmup_verified = [], False
    try:
        host = _OwnedHost()
        adapter = _ReadOnlyAdapter()
        coordinator = SelectionCaptureCoordinator(ClipboardTransactionCoordinator(clipboard), adapter, probe)
        activator = SystemExternalWindowActivator(modifier_is_pressed=lambda _: False)
        def prepare(state, instruction=''):
            payload = host.configure(state, instruction)
            target = ExternalWindowRef(payload['window_token'], payload['process_id'], 0)
            if not activator.activate(target, CancellationToken()).activated:
                raise EnvironmentBlockedError('host_focus_unavailable')
            return payload, coordinator.begin_capture(target)
        # One unrecorded warm-up, including before/after clipboard verification.
        before = fingerprint(clipboard.snapshot())
        payload, request = prepare('selected')
        warmup = coordinator.capture(request=request)
        warmup_verified = (warmup.status == 'selected' and _text_sha256(warmup.text) == payload['selected_sha256']
            and before == fingerprint(clipboard.snapshot()) and clipboard.writes == 0)
        if not warmup_verified:
            return summarize(mode, records, rounds, warmup_verified=False)
        rng = random.Random(seed)
        offset = log_path.stat().st_size if mode == 'attended' and log_path.exists() else 0
        for round_number in range(1, rounds + 1):
            states = list(AUTO_STATES if mode == 'auto' else ATTENDED_STATES)
            if mode == 'auto': rng.shuffle(states)
            for state in states:
                # Freeze evidence before making the physical-key instructions visible.
                before = fingerprint(clipboard.snapshot())
                writes_before = clipboard.writes
                if mode == 'attended' and log_path.exists():
                    offset = log_path.stat().st_size
                instruction = f'{round_number}/{rounds} {state}: {_DIRECTIONS[state]}' if mode == 'attended' else ''
                payload, request = prepare('caret_only' if state == 'caret_only' else 'unsupported_control' if state == 'unsupported_control' else 'selected', instruction)
                if state == 'focus_moved': host.configure('focus_moved')
                if mode == 'auto':
                    adapter.held = state == 'modifier_held'
                    started = time.perf_counter()
                    outcome = coordinator.capture(request=request)
                    capture = CaptureRecord(outcome.status, outcome.reason, outcome.strategy, outcome.focus_restored,
                        (time.perf_counter() - started) * 1000)
                    text_match = _text_sha256(outcome.text) == payload['selected_sha256'] if outcome.status == 'selected' else None
                else:
                    # Only fresh bytes for this newly prepared owned target are admissible.
                    print(instruction, flush=True)
                    capture, offset = read_attended_capture(log_path, offset, payload['window_token'])
                    text_match = None  # App logs deliberately contain no selected text.
                record = case_record(state, capture, before=before, after=fingerprint(clipboard.snapshot()),
                    text_match=text_match, writes=clipboard.writes - writes_before)
                record['round'] = round_number
                record['source_sha256'] = hashlib.sha256(f"{payload['window_token']}:{payload['process_id']}".encode()).hexdigest()
                records.append(record)
                emit(record)
        return summarize(mode, records, rounds, warmup_verified=warmup_verified)
    finally:
        try:
            probe.stop()
        finally:
            try:
                if host is not None: host.close()
            finally:
                expected_sequence = clipboard.last_owned_sequence if clipboard.last_owned_sequence is not None else original_sequence
                clipboard.restore_if_unchanged(original, expected_sequence)


def _text_sha256(text):
    return hashlib.sha256(text.replace('\r\n', '\n').replace('\r', '\n').encode('utf-8')).hexdigest()


def _host(command, ready):
    import clr
    clr.AddReference('System.Windows.Forms')
    from System.Windows.Forms import Application, Button, DockStyle, Form, Label, RichTextBox, Timer
    form = Form()
    form.Text = 'ClipAI controlled selection evidence'
    form.Width, form.Height = 660, 310
    box, button, directions = RichTextBox(), Button(), Label()
    box.Dock, button.Dock, directions.Dock = DockStyle.Fill, DockStyle.Bottom, DockStyle.Top
    directions.Height, button.Height = 60, 28
    button.Text = 'Controlled unsupported control'
    form.Controls.Add(box)
    form.Controls.Add(button)
    form.Controls.Add(directions)
    current = [0]
    text = 'prefix\nClipAI selection loop sample\nsuffix'
    selected = 'ClipAI selection loop sample'
    def tick(_sender, _event):
        try:
            payload = json.loads(command.with_name(f'command-{current[0] + 1}.json').read_text(encoding='utf-8'))
        except (FileNotFoundError, json.JSONDecodeError):
            return
        except PermissionError as error:
            if error.errno != errno.EACCES:
                raise
            return
        if payload['sequence'] == current[0]: return
        current[0] = payload['sequence']
        state = payload['state']
        if state == 'shutdown':
            form.Close()
            return
        directions.Text = payload.get('instruction', '')
        box.Text = text
        form.Activate()
        if state in ('unsupported_control', 'focus_moved'):
            button.Focus()
        else:
            box.Focus()
            box.Select(7, 0 if state == 'caret_only' else len(selected))
        _atomic_json(ready.with_name(f'ready-{current[0]}.json'), {'sequence': current[0], 'window_token': f'hwnd:{form.Handle.ToInt64():x}',
            'process_id': os.getpid(), 'selected_sha256': _text_sha256(str(box.SelectedText))})
    timer = Timer()
    timer.Interval = 50
    timer.Tick += tick
    timer.Start()
    Application.Run(form)
    timer.Stop()
    timer.Dispose()
    form.Dispose()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('auto', 'attended'), default='auto')
    parser.add_argument('--rounds', type=int)
    parser.add_argument('--seed', type=int, default=17)
    parser.add_argument('--output', type=Path, default=Path('artifacts/selection-desktop.jsonl'))
    parser.add_argument('--log', type=Path, default=Path(os.environ.get('LOCALAPPDATA', '.')) / 'ClipAI/logs/clipai.log')
    args = parser.parse_args(argv)
    rounds = args.rounds if args.rounds is not None else (20 if args.mode == 'auto' else 5)
    if rounds < 1: parser.error('rounds must be positive')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', encoding='utf-8') as stream:
        observed_cases = []
        def emit(record):
            if record.get('gate') == 'selection-desktop-case':
                observed_cases.append(record)
            stream.write(json.dumps(record, ensure_ascii=True) + '\n')
            stream.flush()
        reason = _environment_reason(args.mode, environment_facts())
        try:
            if reason: raise EnvironmentBlockedError(reason)
            summary = run_loop(args.mode, rounds, args.seed, args.log, emit)
        except (EnvironmentBlockedError, ClipboardUnavailableError) as error:
            summary = summarize(args.mode, observed_cases, rounds, warmup_verified=False)
            summary.update({'status': 'blocked',
                'reason': 'clipboard_unavailable' if isinstance(error, ClipboardUnavailableError) else str(error),
                'device_evidence': bool(observed_cases), 'acceptance_covered': False, 'passed': False})
            emit(summary)
            print(json.dumps(summary), flush=True)
            return 3
        except Exception as error:
            summary = summarize(args.mode, observed_cases, rounds, warmup_verified=False)
            summary.update({'status': 'failed', 'reason': 'harness_failed', 'error_type': type(error).__name__,
                'device_evidence': bool(observed_cases), 'acceptance_covered': False, 'passed': False})
            emit(summary)
            raise
        emit(summary)
        print(json.dumps(summary), flush=True)
        return 0 if summary['passed'] else 1


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--host':
        _host(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        raise SystemExit(main())
