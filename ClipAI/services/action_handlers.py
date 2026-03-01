from __future__ import annotations

from typing import Callable

Handler = Callable[[str, str], list[dict[str, str]]]


def _summarize_handler(input_text: str, template: str) -> list[dict[str, str]]:
    prompt = template.format(input=input_text)
    return [
        {"role": "system", "content": "You summarize clearly and concisely."},
        {"role": "user", "content": prompt},
    ]


def _translate_handler(input_text: str, template: str) -> list[dict[str, str]]:
    prompt = template.format(input=input_text)
    return [
        {"role": "system", "content": "You are a translation assistant."},
        {"role": "user", "content": prompt},
    ]


def _custom_prompt_handler(input_text: str, template: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": template.format(input=input_text)}]


HANDLERS: dict[str, Handler] = {
    "summarize": _summarize_handler,
    "translate": _translate_handler,
    "custom_prompt": _custom_prompt_handler,
}


def build_messages(action_type: str, input_text: str, template: str) -> list[dict[str, str]]:
    handler = HANDLERS.get(action_type, _custom_prompt_handler)
    return handler(input_text, template)
