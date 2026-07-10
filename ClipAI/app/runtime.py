from __future__ import annotations

from collections.abc import Callable
import logging
import queue
import uuid

from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.commands import AppCommand, CancelSession, CloseSession, CopyResult, FollowUp, StartAction, TogglePin
from ClipAI.core.ports import ApplicationView
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.execute_action import ExecuteAction
from ClipAI.services.output_actions import OutputActions
from ClipAI.services.session_controller import SessionController

logger = logging.getLogger("clipai.runtime")


class AppRuntime:
    def __init__(
        self,
        *,
        actions: ActionCatalog,
        execute_action: ExecuteAction,
        output_actions: OutputActions,
        view: ApplicationView,
        supervisor: TaskSupervisor,
        model: str,
        hotkey_registrar: Callable[[dict[str, dict[str, str]], Callable[[str, str], None]], object],
    ) -> None:
        self._actions = actions
        self._execute_action = execute_action
        self._output_actions = output_actions
        self._view = view
        self._supervisor = supervisor
        self._model = model
        self._hotkey_registrar = hotkey_registrar
        self._commands: queue.Queue[AppCommand] = queue.Queue()
        self._sessions: dict[str, SessionController] = {}
        self._session_actions: dict[str, object] = {}
        self._foreground_id: str | None = None
        self._listener: object | None = None
        self._stopping = False
        self._view.set_command_sink(self.enqueue)

    def enqueue(self, command: object) -> None:
        if not self._stopping:
            self._commands.put(command)  # type: ignore[arg-type]

    def start(self) -> None:
        self._listener = self._hotkey_registrar(
            self._actions.hotkey_action_map(),
            lambda action_id, press_type: self.enqueue(StartAction(action_id, press_type)),
        )

    def run_forever(self) -> None:
        self.start()
        try:
            self._view.run(self.drain_commands)
        finally:
            self.stop()

    def drain_commands(self) -> None:
        while True:
            try:
                command = self._commands.get_nowait()
            except queue.Empty:
                return
            self._handle(command)

    def stop(self) -> None:
        if self._stopping:
            return
        self._stopping = True
        for controller in list(self._sessions.values()):
            controller.cancel()
        if self._listener is not None and hasattr(self._listener, "stop"):
            self._listener.stop()
        self._listener = None
        self._supervisor.shutdown()
        self._view.stop()

    def _handle(self, command: AppCommand) -> None:
        if isinstance(command, StartAction):
            self._start_action(command)
        elif isinstance(command, CloseSession):
            self._close(command.session_id)
        elif isinstance(command, CancelSession):
            self._cancel(command.session_id)
        elif isinstance(command, CopyResult):
            controller = self._sessions.get(command.session_id)
            if controller and controller.snapshot.content:
                self._output_actions.copy(controller.snapshot.content)
        elif isinstance(command, TogglePin):
            controller = self._sessions.get(command.session_id)
            if controller and controller.snapshot.status == SessionStatus.COMPLETED:
                controller.toggle_pin()
        elif isinstance(command, FollowUp):
            self._follow_up(command)

    def _start_action(self, command: StartAction) -> None:
        previous = self._sessions.get(self._foreground_id or "")
        if previous is not None and not previous.snapshot.pinned:
            previous.cancel()
            self._supervisor.cancel(previous.snapshot.session_id)
        action = self._actions.resolve(command.action_id, command.press_type)
        session_id = uuid.uuid4().hex
        controller = SessionController(
            SessionSnapshot(
                session_id=session_id,
                revision=0,
                status=SessionStatus.CREATED,
                action_id=action.id,
                title=action.name,
                model=self._model,
            ),
            self._view,
        )
        self._sessions[session_id] = controller
        self._session_actions[session_id] = action
        self._foreground_id = session_id
        self._supervisor.submit(
            session_id,
            lambda: self._execute_action.execute(action, controller),
            lambda error: self._handle_unhandled(session_id, error),
        )

    def _follow_up(self, command: FollowUp) -> None:
        controller = self._sessions.get(command.session_id)
        action = self._session_actions.get(command.session_id)
        if controller is None or action is None or not command.text.strip():
            return
        self._supervisor.submit(
            command.session_id,
            lambda: self._execute_action.execute_follow_up(action, command.text, controller),  # type: ignore[arg-type]
            lambda error: self._handle_unhandled(command.session_id, error),
        )

    def _cancel(self, session_id: str) -> None:
        controller = self._sessions.get(session_id)
        if controller:
            controller.cancel()
            self._supervisor.cancel(session_id)

    def _close(self, session_id: str) -> None:
        controller = self._sessions.pop(session_id, None)
        self._session_actions.pop(session_id, None)
        if controller:
            controller.close()
            self._supervisor.cancel(session_id)
        if self._foreground_id == session_id:
            self._foreground_id = None

    def _handle_unhandled(self, session_id: str, error: BaseException) -> None:
        logger.exception("Unhandled session error session_id=%s", session_id, exc_info=error)
        controller = self._sessions.get(session_id)
        if controller:
            controller.fail("ClipAI encountered an unexpected error.")

