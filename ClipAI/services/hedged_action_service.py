from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from clipai.core.cancellation import CancellationController
from clipai.core.constants import (
    EVENT_ACTION_COMPLETE,
    EVENT_ACTION_ERROR,
    EVENT_ACTION_START,
    EVENT_PIPELINE_UPDATE,
)
from clipai.core.event_bus import EventBus
from clipai.services.action_config import ResolvedActionConfig
from clipai.services.action_service import ActionRunResult


@dataclass(frozen=True)
class HedgeRoute:
    name: str
    provider: Any
    model: str
    provider_name: str


class HedgedActionService:
    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    def run_action(
        self,
        config: ResolvedActionConfig,
        messages: list[dict[str, Any]],
        primary: HedgeRoute,
        fallback: HedgeRoute,
        *,
        temperature: float,
        stream: bool,
        source_meta: dict[str, Any] | None = None,
        on_chunk: Callable[[str], None] | None = None,
        hedge_delay_ms: int = 150,
    ) -> ActionRunResult:
        source_meta = source_meta or {}
        started = time.time()
        self._event_bus.publish(
            EVENT_ACTION_START,
            {
                "action_id": config.action_id,
                "action_name": config.action_name,
                "mode": config.mode,
                "ts": int(started * 1000),
            },
        )

        ctrls = {primary.name: CancellationController(), fallback.name: CancellationController()}
        events: queue.Queue[tuple[str, str, Any]] = queue.Queue()
        route_results: dict[str, list[str]] = {primary.name: [], fallback.name: []}
        route_errors: dict[str, Exception] = {}
        route_done: set[str] = set()
        winner_name: str | None = None
        winner_route: HedgeRoute | None = None

        def worker(route: HedgeRoute, start_delay_ms: int = 0) -> None:
            if start_delay_ms > 0:
                time.sleep(start_delay_ms / 1000)
            if ctrls[route.name].is_cancelled():
                events.put(("done", route.name, None))
                return
            try:
                iterator = route.provider.chat_completion(
                    messages=messages,
                    model=route.model,
                    stream=stream,
                    temperature=temperature,
                    image_base64=source_meta.get("image_base64"),
                    cancellation_token=ctrls[route.name].token,
                )
                for chunk in iterator:
                    ctrls[route.name].token.throw_if_cancelled()
                    route_results[route.name].append(chunk.content)
                    events.put(("chunk", route.name, chunk.content))
                events.put(("done", route.name, None))
            except Exception as exc:
                events.put(("error", route.name, exc))

        threads = [
            threading.Thread(target=worker, args=(primary, 0), daemon=True),
            threading.Thread(target=worker, args=(fallback, max(0, hedge_delay_ms)), daemon=True),
        ]
        for thread in threads:
            thread.start()

        try:
            while len(route_done) < 2:
                event_type, route_name, payload = events.get()
                if event_type == "chunk":
                    if winner_name is None:
                        winner_name = route_name
                        winner_route = primary if route_name == primary.name else fallback
                        for other_name, ctrl in ctrls.items():
                            if other_name != winner_name:
                                ctrl.cancel("hedge loser")
                    if route_name != winner_name:
                        continue
                    self._event_bus.publish(
                        EVENT_PIPELINE_UPDATE,
                        {
                            "content": payload,
                            "source_meta": {
                                **source_meta,
                                "winner_provider": winner_route.provider_name if winner_route else config.provider,
                                "winner_model": winner_route.model if winner_route else config.model,
                            },
                            "action_id": config.action_id,
                            "ts": int(time.time() * 1000),
                        },
                    )
                    if on_chunk is not None:
                        on_chunk(payload)
                    continue

                route_done.add(route_name)
                if event_type == "error":
                    route_errors[route_name] = payload
                    if winner_name == route_name:
                        raise payload
                    if winner_name is None and len(route_errors) == 2:
                        raise payload
                    continue

                if winner_name is None and route_results[route_name]:
                    winner_name = route_name
                    winner_route = primary if route_name == primary.name else fallback
                    for other_name, ctrl in ctrls.items():
                        if other_name != winner_name:
                            ctrl.cancel("hedge loser")

            if winner_name is None:
                exc = route_errors.get(primary.name) or route_errors.get(fallback.name) or RuntimeError("hedged request failed")
                raise exc

            duration_ms = int((time.time() - started) * 1000)
            final_content = "".join(route_results[winner_name])
            self._event_bus.publish(
                EVENT_ACTION_COMPLETE,
                {
                    "action_id": config.action_id,
                    "summary": final_content[:120],
                    "duration_ms": duration_ms,
                    "ts": int(time.time() * 1000),
                    "provider": winner_route.provider_name if winner_route else config.provider,
                    "model": winner_route.model if winner_route else config.model,
                },
            )
            return ActionRunResult(
                action_id=config.action_id,
                content=final_content,
                provider_name=winner_route.provider_name if winner_route else config.provider,
                model_name=winner_route.model if winner_route else config.model,
            )
            
        except Exception as exc:
            self._event_bus.publish(
                EVENT_ACTION_ERROR,
                {
                    "action_id": config.action_id,
                    "error_type": exc.__class__.__name__,
                    "message": str(exc),
                    "ts": int(time.time() * 1000),
                },
            )
            raise
        finally:
            for ctrl in ctrls.values():
                ctrl.cancel("hedged request cleanup")
