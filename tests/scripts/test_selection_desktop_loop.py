import json
from pathlib import Path

import pytest

from scripts import selection_desktop_loop as loop


def test_clipboard_busy_retry_is_exact_and_bounded():
    calls, waits = [], []
    def busy():
        calls.append(1)
        raise OSError('Clipboard is busy')
    with pytest.raises(loop.ClipboardUnavailableError):
        loop.retry_clipboard(busy, wait=waits.append)
    assert len(calls) == 20
    assert waits == [.25] * 19


def test_busy_clipboard_can_recover_but_other_os_errors_propagate():
    calls = []
    def available():
        calls.append(1)
        if len(calls) < 3:
            raise OSError('Clipboard is busy')
        return 'snapshot'
    assert loop.retry_clipboard(available, wait=lambda _: None) == 'snapshot'
    for message in ('access denied', 'Clipboard is busy elsewhere'):
        def fail():
            raise OSError(message)
        with pytest.raises(OSError, match=message):
            loop.retry_clipboard(fail, wait=lambda _: pytest.fail('must not retry other OSError'))


@pytest.mark.parametrize('state', ['selected', 'modifier_held', 'held_after_open'])
def test_held_attended_states_expect_immediate_selected(state):
    assert loop.expected_for_state(state) == ('selected', '')


def test_attended_log_parses_only_owned_new_capture_metadata(tmp_path):
    path = tmp_path / 'app.log'
    old = 'Selection capture operation_id=old target=hwnd:1 status=selected reason= strategy=uia focus_restored=False elapsed_ms=44\n'
    path.write_text(old, encoding='utf-8')
    offset = path.stat().st_size
    unrelated = old.replace('target=hwnd:1', 'target=hwnd:2')
    new = old.replace('operation_id=old', 'operation_id=new')
    clock = [0.0]
    def wait(seconds):
        clock[0] += seconds
        with path.open('a', encoding='utf-8') as stream:
            stream.write('provider content that must not enter evidence\n' + unrelated + new)
    result, end = loop.read_attended_capture(path, offset, 'hwnd:1', timeout_sec=15,
        monotonic=lambda: clock[0], wait=wait)
    assert result.status == 'selected' and result.reason == ''
    assert result.elapsed_ms == 44
    assert end > offset
    assert 'provider content' not in json.dumps(result.__dict__)


def test_attended_no_capture_has_bounded_virtual_deadline(tmp_path):
    path = tmp_path / 'app.log'
    path.write_bytes(b'')
    clock = [0.0]
    result, _ = loop.read_attended_capture(path, 0, 'hwnd:1', timeout_sec=15,
        monotonic=lambda: clock[0], wait=lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    assert result is None
    assert 15 <= clock[0] < 15.2


@pytest.mark.parametrize('facts,reason', [
    (loop.EnvironmentFacts(False, False, False, False), 'windows_required'),
    (loop.EnvironmentFacts(True, False, False, True), 'interactive_desktop_required'),
    (loop.EnvironmentFacts(True, True, True, True), 'elevated_harness'),
    (loop.EnvironmentFacts(True, True, False, False), 'application_not_running'),
])
def test_attended_environment_block_is_explicit_and_nonempty(tmp_path, monkeypatch, facts, reason):
    monkeypatch.setattr(loop, 'environment_facts', lambda: facts)
    output = tmp_path / 'evidence.jsonl'
    assert loop.main(['--mode', 'attended', '--output', str(output)]) == 3
    record = json.loads(output.read_text(encoding='utf-8'))
    assert record['status'] == 'blocked' and record['reason'] == reason
    assert record['content_recorded'] is False
    assert record['passed'] is False


def test_clipboard_exhaustion_is_blocked_but_other_os_errors_escape(tmp_path, monkeypatch):
    monkeypatch.setattr(loop, 'environment_facts', lambda: loop.EnvironmentFacts(True, True, False, True))
    def run(*args):
        raise loop.ClipboardUnavailableError()
    monkeypatch.setattr(loop, 'run_loop', run)
    output = tmp_path / 'evidence.jsonl'
    assert loop.main(['--mode', 'auto', '--output', str(output)]) == 3
    assert json.loads(output.read_text())['reason'] == 'clipboard_unavailable'
    def other(*args):
        raise OSError('access denied')
    monkeypatch.setattr(loop, 'run_loop', other)
    with pytest.raises(OSError, match='access denied'):
        loop.main(['--mode', 'auto', '--output', str(output)])


def test_desktop_loop_never_injects_hotkeys():
    import ast
    tree = ast.parse(Path(loop.__file__).read_text(encoding='utf-8'))
    calls = {getattr(node.func, 'attr', getattr(node.func, 'id', '')) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    assert not calls & {'SendInput', 'keybd_event', 'press', 'release', 'send', 'send_keys'}


def test_synthetic_fixture_text_never_enters_records():
    record = loop.case_record('modifier_held', loop.CaptureRecord('selected', '', 'uia', False, 20),
        before='a' * 64, after='a' * 64, text_match=True)
    payload = json.dumps(loop.summarize('auto', [record], 1, warmup_verified=True))
    assert record['passed']
    assert 'verified selection' not in payload
    assert 'frozen clipboard' not in payload
    assert 'ClipAI selection loop sample' not in payload


def test_argument_error_is_exit_two():
    with pytest.raises(SystemExit) as error:
        loop.main(['--rounds', '0'])
    assert error.value.code == 2


def test_blocked_summary_retains_completed_case_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(loop, 'environment_facts', lambda: loop.EnvironmentFacts(True, True, False, True))
    def interrupted(mode, rounds, seed, log, emit):
        emit(loop.case_record('selected', loop.CaptureRecord('selected', '', 'uia', False, 20),
            before='a' * 64, after='a' * 64, text_match=True))
        raise loop.EnvironmentBlockedError('host_exited')
    monkeypatch.setattr(loop, 'run_loop', interrupted)
    output = tmp_path / 'evidence.jsonl'
    assert loop.main(['--mode', 'attended', '--output', str(output)]) == 3
    summary = json.loads(output.read_text().splitlines()[-1])
    assert summary['status'] == 'blocked'
    assert summary['cases'] == summary['passed_cases'] == summary['clipboard_preserved'] == 1
    assert summary['latency_ms']['p95'] == 20
    assert summary['passed'] is False and summary['acceptance_covered'] is False


@pytest.mark.parametrize('stop_fails', [False, True])
def test_failed_warmup_is_unrecorded_and_cleanup_order_is_guaranteed(tmp_path, monkeypatch, stop_fails):
    from types import SimpleNamespace
    from ClipAI.core.models import SelectionCaptureOutcome
    events, emitted = [], []
    class Clipboard:
        writes, last_owned_sequence = 0, None
        def snapshot(self): return SimpleNamespace(formats=())
        def sequence_number(self): return 7
        def restore_if_unchanged(self, snapshot, sequence):
            assert sequence == 7
            events.append('restore')
    class Host:
        def configure(self, *args):
            return {'window_token': 'hwnd:1', 'process_id': 1, 'selected_sha256': 'mismatch'}
        def close(self): events.append('host_close')
    class Probe:
        def stop(self):
            events.append('probe_stop')
            if stop_fails: raise RuntimeError('cleanup failed')
    class Coordinator:
        def __init__(self, *args): pass
        def begin_capture(self, target): return object()
        def capture(self, **kwargs): return SelectionCaptureOutcome(status='none')
    monkeypatch.setattr(loop, '_RetryingClipboard', Clipboard)
    monkeypatch.setattr(loop, '_OwnedHost', Host)
    monkeypatch.setattr(loop, 'WindowsSelectionProbe', Probe)
    monkeypatch.setattr(loop, 'SelectionCaptureCoordinator', Coordinator)
    monkeypatch.setattr(loop, 'SystemExternalWindowActivator', lambda **kwargs:
        SimpleNamespace(activate=lambda *args: SimpleNamespace(activated=True)))
    if stop_fails:
        with pytest.raises(RuntimeError, match='cleanup failed'):
            loop.run_loop('auto', 20, 17, tmp_path / 'log', emitted.append)
    else:
        summary = loop.run_loop('auto', 20, 17, tmp_path / 'log', emitted.append)
        assert summary['cases'] == 0 and not summary['warmup_verified']
    assert emitted == []
    assert events == ['probe_stop', 'host_close', 'restore']
