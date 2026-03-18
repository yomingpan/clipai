from __future__ import annotations

import queue

from clipai.providers.gemini import GeminiProvider


def test_handle_stream_event_accepts_sse_json() -> None:
    q: queue.Queue[tuple[str, object]] = queue.Queue()
    done = GeminiProvider._handle_stream_event(
        'data: {"candidates":[{"content":{"parts":[{"text":"hello"}]}}]}',
        q,
    )

    assert done is False
    assert q.get_nowait() == ("chunk", "hello")


def test_handle_stream_event_accepts_json_array_payload() -> None:
    q: queue.Queue[tuple[str, object]] = queue.Queue()
    done = GeminiProvider._handle_stream_event(
        '[{"candidates":[{"content":{"parts":[{"text":"a"}]}}]}, {"candidates":[{"content":{"parts":[{"text":"b"}]}}]}]',
        q,
    )

    assert done is False
    assert q.get_nowait() == ("chunk", "ab")


def test_handle_stream_event_accepts_multiple_sse_data_lines() -> None:
    q: queue.Queue[tuple[str, object]] = queue.Queue()
    done = GeminiProvider._handle_stream_event(
        'data: {"candidates":[{"content":{"parts":[{"text":"a"}]}}]}\n'
        'data: {"candidates":[{"content":{"parts":[{"text":"b"}]}}]}',
        q,
    )

    assert done is False
    assert q.get_nowait() == ("chunk", "a")
    assert q.get_nowait() == ("chunk", "b")
