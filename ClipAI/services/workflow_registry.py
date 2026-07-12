from __future__ import annotations

from ClipAI.services.workflow_controller import WorkflowController


class WorkflowRegistry:
    """Own workflow lookup plus foreground and headless-sequence identities."""

    def __init__(self) -> None:
        self.workflows: dict[str, WorkflowController] = {}
        self.foreground_id: str | None = None
        self.sequence_id: str | None = None

    def add(self, workflow_id: str, controller: WorkflowController, *, foreground: bool = False) -> None:
        self.workflows[workflow_id] = controller
        if foreground:
            self.foreground_id = workflow_id

    def get(self, workflow_id: str | None) -> WorkflowController | None:
        return self.workflows.get(workflow_id or "")

    def remove(self, workflow_id: str) -> WorkflowController | None:
        controller = self.workflows.pop(workflow_id, None)
        if self.foreground_id == workflow_id:
            self.foreground_id = None
        if self.sequence_id == workflow_id:
            self.sequence_id = None
        return controller

    def activate(self, workflow_id: str) -> bool:
        if workflow_id not in self.workflows:
            return False
        self.foreground_id = workflow_id
        return True
