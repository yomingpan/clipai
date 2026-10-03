from __future__ import annotations

from pathlib import Path

from ClipAI.core.managed_update import TransactionId
from ClipAI.core.update_bundle import VerifiedManagedBundle
from ClipAI.core.update_ports import CandidateBuildRequest, CandidateEnvironment, CandidateEnvironmentBuilder
from ClipAI.platform.candidate_environment import validate_candidate_environment
from ClipAI.platform.managed_update_fs import copy_regular_tree
from ClipAI.platform.update_bundle import verify_bundle_inventory


class PreparedManagedPayloadMaterializer:
    """Copy a verified release and prove its offline runtime at one target root."""

    def __init__(self, *, candidate_builder: CandidateEnvironmentBuilder) -> None:
        self._candidate_builder = candidate_builder

    def prepare(
        self,
        verified: VerifiedManagedBundle,
        *,
        target_root: Path,
        transaction_id: TransactionId,
        base_python: Path,
    ) -> CandidateEnvironment:
        copy_regular_tree(verified.staging_root, target_root)
        verify_bundle_inventory(target_root, verified.manifest)
        request = CandidateBuildRequest(
            transaction_id=transaction_id,
            candidate_root=target_root,
            base_python=base_python,
            expected_version=verified.manifest.app_version,
            entrypoint=verified.manifest.entrypoint,
        )
        candidate = self._candidate_builder.build(request)
        validate_candidate_environment(candidate, request)
        return candidate
