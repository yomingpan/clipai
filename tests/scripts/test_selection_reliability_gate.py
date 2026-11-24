import json
import pytest

from scripts import selection_reliability_gate as gate
from ClipAI.core.models import SelectionCaptureOutcome


def test_independent_oracle_covers_27_cases_with_virtual_waits(monkeypatch):
    monkeypatch.setattr('time.sleep', lambda _: pytest.fail('real sleep in simulation'))
    result = gate.run_iterations(17, 480, 3)
    assert result['scenario_count'] == 27
    assert result['policy_correct_rate'] == result['exact_available_rate'] == 1
    assert result['passed'] and not result['nondeterministic']
    assert not any(result['violations'].values())
    assert result['latency_ms']['p95'] < 1
    payload = json.dumps(result)
    for text in ('verified selection', 'frozen clipboard', 'ClipAI selection loop sample'):
        assert text not in payload
    assert result['content_recorded'] is False
    assert result['device_evidence'] is False


def test_all_none_mutation_is_rejected(monkeypatch):
    monkeypatch.setattr(gate.SelectionCaptureCoordinator, 'capture', lambda *a, **k: SelectionCaptureOutcome(status='none'))
    result = gate.run(17)
    assert not result['passed']
    assert result['violations']['unknown_as_none'] > 0


@pytest.mark.parametrize('args', [['--cases', '26'], ['--iterations', '0']])
def test_incomplete_matrix_or_iterations_is_argument_error(args):
    with pytest.raises(SystemExit) as error:
        gate.main(args)
    assert error.value.code == 2
