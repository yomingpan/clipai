"""Independent selection-policy oracle; virtual waits, content-free evidence."""
from __future__ import annotations
import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import random
import statistics
import time
from types import SimpleNamespace
from unittest.mock import patch
from ClipAI.core.models import ExternalWindowRef, SelectionCaptureOutcome, SelectionSource
from ClipAI.core.state import CancellationToken
from ClipAI.services.clipboard_transaction import ClipboardTransactionCoordinator
from ClipAI.services.selection_capture import SelectionCaptureCoordinator
from ClipAI.support.statistics import percentile

class _SimulationClock:
    def __init__(self): self.now = 0.0
    def monotonic(self): return self.now
    def wait(self, seconds): self.now += max(seconds, .001)

@dataclass(frozen=True)
class _Snapshot:
    text: str

class _Clipboard:
    def __init__(self, fault=''):
        self.value, self.sequence, self.writes = 'frozen clipboard', 1, 0
        self.fault, self.changed = fault, False
    def read_text(self):
        if self.fault == 'clipboard-changed' and self.value == 'verified selection' and not self.changed:
            self.changed = True
            self.write_text('external update')
            return 'verified selection'
        return self.value
    def write_text(self, text):
        self.value = text
        self.sequence += 1
        self.writes += 1
    def write_transient_text(self, text): self.write_text(text)
    def snapshot(self):
        if self.fault == 'snapshot-failed': raise OSError('fixture snapshot failure')
        return _Snapshot(self.value)
    def sequence_number(self): return self.sequence
    def restore_if_unchanged(self, snapshot, expected_sequence):
        if self.sequence != expected_sequence: return False
        self.write_text(snapshot.text)
        return True

class _Adapter:
    def __init__(self, clipboard, name, token):
        self.clipboard, self.name, self.token = clipboard, name, token
        self.modifier_checks = self.copy_calls = self.copy_while_held = 0
    def modifier_is_pressed(self, modifier):
        self.modifier_checks += 1
        if self.name == 'cancelled-during-gate': self.token.cancel()
        return self.held and modifier == 'alt'
    @property
    def held(self):
        return self.name in {'modifier-held-uia-selected', 'modifier-held-copy-path', 'cancelled-during-gate'} or (
            self.name in {'modifier-released-before-copy', 'source-changed-after-release'} and self.modifier_checks <= 3)
    def copy_selection(self):
        self.copy_calls += 1
        self.copy_while_held += self.held
        if self.name == 'copy-failed': raise OSError('fixture copy failure')
        if self.name != 'copy-timeout': self.clipboard.write_text('' if self.name == 'copy-empty' else 'verified selection')

class _Probe:
    def __init__(self, case, adapter, token):
        self.case, self.adapter, self.token = case, adapter, token
        self.source = SelectionSource(ExternalWindowRef('hwnd:1', 42, 0), 'hwnd:2')
        self.current_checks, self.probed = 0, False
    def capture_source(self, target=None):
        name = self.case.name
        if name == 'source-unavailable' or (target is not None and name == 'focus-restored-unavailable'): return None
        if target is not None:
            window = ExternalWindowRef('hwnd:9' if name == 'focus-restored-other-window' else 'hwnd:1',
                99 if name == 'focus-restored-other-pid' else 42, 0)
            return SelectionSource(window, 'hwnd:3')
        return self.source
    def source_is_current(self, source):
        self.current_checks += 1
        name = self.case.name
        return not (name == 'wrong-source' or (name == 'source-changed-after-probe' and self.probed)
            or (name == 'source-changed-after-release' and self.probed and not self.adapter.held))
    def probe(self, source, cancellation):
        self.probed = True
        if self.case.name == 'probe-raises': raise OSError('fixture provider failure')
        if self.case.name == 'cancelled-after-probe': self.token.cancel()
        return self.case.probe

class _ClockedTransactions(ClipboardTransactionCoordinator):
    def __init__(self, clipboard, clock):
        super().__init__(clipboard)
        self.clock = clock
    def capture_selection(self, *args, **kwargs):
        return super().capture_selection(*args, monotonic=self.clock.monotonic, wait=self.clock.wait, **kwargs)

@dataclass(frozen=True)
class _Case:
    name: str
    probe: SelectionCaptureOutcome
    expected: tuple[str, str]

_SELECTED = SelectionCaptureOutcome('verified selection', 'selected', strategy='uia')
_COPY = SelectionCaptureOutcome(reason='selection_only_copy_available', copy_selection_only=True)
_RESTORED = SelectionCaptureOutcome('verified selection', 'selected', strategy='uia', focus_restored=True)
_SCENARIOS = (
    _Case('uia-selected', _SELECTED, ('selected', '')),
    _Case('uia-caret', SelectionCaptureOutcome(status='none', reason='uia_caret_only'), ('none', 'uia_caret_only')),
    _Case('unsupported', SelectionCaptureOutcome(reason='uia_unsupported'), ('unknown', 'uia_unsupported')),
    _Case('no-ranges', SelectionCaptureOutcome(reason='uia_no_ranges'), ('unknown', 'uia_no_ranges')),
    _Case('uia-timeout', SelectionCaptureOutcome(reason='uia_timeout'), ('unknown', 'uia_timeout')),
    _Case('source-unavailable', _SELECTED, ('unknown', 'source_unavailable')),
    _Case('positive-copy', SelectionCaptureOutcome(reason='uia_text_failed', selection_detected=True), ('selected', '')),
    _Case('verified-copy', _COPY, ('selected', '')),
    _Case('copy-timeout', _COPY, ('unknown', 'copy_timeout')),
    _Case('copy-empty', _COPY, ('unknown', 'copy_empty')),
    _Case('clipboard-changed', _COPY, ('unknown', 'clipboard_changed')),
    _Case('snapshot-failed', _COPY, ('unknown', 'snapshot_failed')),
    _Case('copy-failed', _COPY, ('unknown', 'copy_failed')),
    _Case('wrong-source', _SELECTED, ('unknown', 'source_changed')),
    _Case('source-changed-after-probe', _SELECTED, ('unknown', 'source_changed')),
    _Case('source-changed-after-release', _COPY, ('unknown', 'source_changed')),
    _Case('cancelled', _SELECTED, ('cancelled', '')),
    _Case('cancelled-after-probe', _SELECTED, ('cancelled', '')),
    _Case('cancelled-during-gate', _COPY, ('cancelled', '')),
    _Case('focus-restored', _RESTORED, ('selected', '')),
    _Case('focus-restored-other-window', _RESTORED, ('unknown', 'source_changed')),
    _Case('focus-restored-other-pid', _RESTORED, ('unknown', 'source_changed')),
    _Case('focus-restored-unavailable', _RESTORED, ('unknown', 'source_changed')),
    _Case('probe-raises', _COPY, ('unknown', 'capture_failed')),
    _Case('modifier-held-uia-selected', _SELECTED, ('selected', '')),
    _Case('modifier-held-copy-path', _COPY, ('unknown', 'modifier_timeout')),
    _Case('modifier-released-before-copy', _COPY, ('selected', '')),
)

def run(seed: int, cases: int = 480) -> dict[str, object]:
    if cases < len(_SCENARIOS): raise ValueError('cases must cover all 27 scenarios')
    rng = random.Random(seed)
    samples = [rng.choice(_SCENARIOS) for _ in range(cases - len(_SCENARIOS))] + list(_SCENARIOS)
    rng.shuffle(samples)
    correct = exact_expected = exact_available = 0
    latencies, fingerprints = [], []
    histogram = Counter()
    violations = dict.fromkeys(('policy', 'clipboard_dirty', 'unknown_as_none', 'blind_copy', 'copy_while_held', 'text_mismatch'), 0)
    for case in samples:
        clock, token = _SimulationClock(), CancellationToken()
        clipboard = _Clipboard(case.name)
        adapter = _Adapter(clipboard, case.name, token)
        probe = _Probe(case, adapter, token)
        if case.name == 'cancelled': token.cancel()
        # Inject virtual time into both owners. No real sleep or deadline race.
        with patch('ClipAI.services.selection_capture.time', SimpleNamespace(monotonic=clock.monotonic, sleep=clock.wait)):
            coordinator = SelectionCaptureCoordinator(_ClockedTransactions(clipboard, clock), adapter, probe,
                modifier_release_timeout_sec=.01, timeout_sec=.01, poll_sec=.001)
            started = time.perf_counter()
            outcome = coordinator.capture(token)
            latencies.append((time.perf_counter() - started) * 1000)
        policy_ok = (outcome.status, outcome.reason) == case.expected
        correct += policy_ok
        violations['policy'] += not policy_ok
        expected_clipboard = 'external update' if case.name == 'clipboard-changed' else 'frozen clipboard'
        violations['clipboard_dirty'] += clipboard.value != expected_clipboard
        violations['unknown_as_none'] += case.expected[0] == 'unknown' and outcome.status == 'none'
        violations['blind_copy'] += adapter.copy_calls > 0 and not (case.probe.selection_detected or case.probe.copy_selection_only)
        violations['copy_while_held'] += adapter.copy_while_held
        if case.expected[0] == 'selected':
            exact_expected += 1
            exact_available += outcome.text == 'verified selection'
            violations['text_mismatch'] += outcome.text != 'verified selection'
        histogram[outcome.reason] += 1
        fingerprints.append((case.name, outcome.status, outcome.reason, outcome.strategy,
            hashlib.sha256(outcome.text.encode()).hexdigest(), adapter.copy_calls, adapter.modifier_checks, clipboard.writes))
    return {
        'schema': 1, 'gate': 'selection-policy-simulation', 'seed': seed, 'cases': cases,
        'scenario_count': len(_SCENARIOS), 'policy_correct': correct, 'policy_correct_rate': correct / cases,
        'exact_expected': exact_expected, 'exact_available': exact_available,
        'exact_available_rate': exact_available / exact_expected if exact_expected else 1.0,
        'violations': violations, 'reason_histogram': dict(sorted(histogram.items())),
        'determinism_sha256': hashlib.sha256(json.dumps(fingerprints).encode()).hexdigest(),
        'latency_ms': {'p50': round(statistics.median(latencies), 3), 'p90': round(percentile(latencies, .9), 3), 'p95': round(percentile(latencies, .95), 3)},
        'content_recorded': False, 'device_evidence': False,
        'passed': correct == cases and exact_available == exact_expected and not any(violations.values()),
    }

def run_iterations(seed, cases, iterations):
    if iterations < 1: raise ValueError('iterations must be positive')
    results = [run(seed, cases) for _ in range(iterations)]
    result = results[0]
    result['iterations'] = iterations
    result['nondeterministic'] = len({row['determinism_sha256'] for row in results}) != 1
    result['latency_ms'] = {key: max(row['latency_ms'][key] for row in results) for key in ('p50', 'p90', 'p95')}
    result['passed'] = all(row['passed'] for row in results) and not result['nondeterministic'] and result['latency_ms']['p95'] < 1
    return result

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('artifacts/selection-reliability.jsonl'))
    parser.add_argument('--seeds', type=int, nargs='+', default=[17, 41, 73])
    parser.add_argument('--cases', type=int, default=480)
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args(argv)
    if args.cases < 27 or args.iterations < 1: parser.error('cases must be >=27 and iterations >=1')
    results = [run_iterations(seed, args.cases, args.iterations) for seed in args.seeds]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', encoding='utf-8') as stream:
        for result in results: stream.write(json.dumps(result, ensure_ascii=True) + '\n')
    return 0 if all(result['passed'] for result in results) else 1

if __name__ == '__main__': raise SystemExit(main())
