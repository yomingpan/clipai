from pathlib import Path

from ClipAI.core.managed_update import transaction_id
from ClipAI.core.update_ports import CandidateBuildRequest, CandidateEnvironment


class FakeCandidateBuilder:
    def __init__(self, result: CandidateEnvironment) -> None:
        self.result = result
        self.requests: list[CandidateBuildRequest] = []

    def build(self, request: CandidateBuildRequest) -> CandidateEnvironment:
        self.requests.append(request)
        return self.result


def test_candidate_builder_seam_has_a_small_fakeable_interface(tmp_path: Path):
    result = CandidateEnvironment(tmp_path, tmp_path / "python.exe", tmp_path / "main.py", "3.8.0")
    fake = FakeCandidateBuilder(result)
    request = CandidateBuildRequest(transaction_id("tx"), tmp_path, tmp_path / "base.exe", "3.8.0", "payload/main.py")
    assert fake.build(request) == result
    assert fake.requests == [request]
