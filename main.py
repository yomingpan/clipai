import time
from time import perf_counter
from clipai.actions import load_config, build_action_map
from clipai.hotkeys import register_hotkeys
from clipai.llm_openai_compat import OpenAICompatClient
from clipai.llm_ollama import OllamaClient
from clipai.llm_azure_openai import AzureOpenAIClient
from clipai.clipboard import read_clipboard_text, read_clipboard_image, ocr_image_to_text, write_clipboard_text
from clipai.output import maybe_auto_paste, save_to_file
from clipai.safety import apply_safety
from clipai.templates import render_template
from clipai.logging_utils import log_event

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


def _build_messages(action, app_cfg, input_text):
    context = {
        "input": input_text,
        "action_name": action.get("name", ""),
        "action_id": action.get("id", ""),
        "group": action.get("group", ""),
        "description": action.get("description", ""),
    }

    if action.get("messages"):
        msgs = []
        for msg in action["messages"]:
            content = render_template(msg.get("content", ""), context)
            msgs.append({"role": msg.get("role", "user"), "content": content})
        return msgs

    system_prompt = action.get("system_prompt") or app_cfg.get("system_prompt") or "You are a helpful assistant."
    prompt = render_template(action.get("prompt", ""), context).strip()

    if "{{input}}" in action.get("prompt", ""):
        user_content = prompt
    else:
        user_content = f"{prompt}\n\n=== Input ===\n{input_text}".strip()

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def _get_input_text(action, app_cfg):
    input_type = (action.get("input_type") or "text").lower()
    if input_type == "image":
        image = read_clipboard_image()
        if image is None:
            return None, "Clipboard image not found."

        image_cfg = app_cfg.get("image", {})
        mode = (image_cfg.get("mode") or "ocr").lower()
        if mode != "ocr":
            return None, f"Image mode '{mode}' not supported in MVP."

        try:
            text = ocr_image_to_text(image)
        except Exception as e:
            return None, f"OCR failed: {e}"

        return text, None

    text = read_clipboard_text()
    if not text.strip():
        return None, "Clipboard is empty."
    return text, None


def handle_action(action, client, app_cfg, provider_cfg):
    started = perf_counter()
    input_text, input_err = _get_input_text(action, app_cfg)
    if input_err:
        print(f"[clipai] {input_err}")
        log_event({"event": "input_error", "action_id": action.get("id"), "error": input_err})
        return

    safety_cfg = app_cfg.get("safety", {})
    safety_mode = safety_cfg.get("mode", "block")
    patterns = safety_cfg.get("patterns")
    safety_result = apply_safety(input_text, safety_mode, patterns)
    if safety_result["action"] == "block":
        print("[clipai] Blocked: possible sensitive content detected.")
        log_event({"event": "blocked", "action_id": action.get("id"), "hits": safety_result.get("hits", [])})
        return

    input_text = safety_result["text"]

    model = action.get("model") or client.default_model
    temperature = float(action.get("temperature", app_cfg.get("temperature", 0.3)))
    max_tokens = int(action.get("max_tokens", app_cfg.get("max_tokens", 800)))
    response_format = action.get("response_format")

    messages = _build_messages(action, app_cfg, input_text)

    print(f"[clipai] Action: {action.get('name')} | model={model}")

    retries = int(provider_cfg.get("retries", 0))
    backoff = float(provider_cfg.get("retry_backoff_sec", 0.5))

    last_error = None
    for attempt in range(retries + 1):
        try:
            result = client.chat_completion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )
            break
        except Exception as e:
            last_error = e
            if attempt >= retries:
                print(f"[clipai] LLM call failed: {e}")
                log_event({"event": "llm_error", "action_id": action.get("id"), "error": str(e)})
                return
            time.sleep(backoff * (2 ** attempt))

    if app_cfg.get("add_result_header", False):
        result = f"[{action.get('name')}]\n{result}"

    output_cfg = action.get("output", {})
    copy_enabled = output_cfg.get("copy", True)
    if copy_enabled:
        write_clipboard_text(result)
        print("[clipai] ✅ Result copied to clipboard.")

    auto_paste = output_cfg.get("auto_paste", app_cfg.get("auto_paste_default", False))
    if auto_paste:
        maybe_auto_paste()

    save_path = output_cfg.get("save_path")
    if save_path:
        context = {
            "action_name": action.get("name", ""),
            "action_id": action.get("id", ""),
        }
        save_to_file(render_template(save_path, context), result)

    duration_ms = int((perf_counter() - started) * 1000)
    log_event({
        "event": "success",
        "action_id": action.get("id"),
        "action_name": action.get("name"),
        "model": model,
        "duration_ms": duration_ms,
        "input_len": len(input_text),
        "output_len": len(result),
    })


def _build_client(provider_cfg):
    provider_type = provider_cfg.get("type", "openai_compat").lower()
    if provider_type == "ollama":
        return OllamaClient(
            base_url=provider_cfg.get("base_url", "http://localhost:11434"),
            default_model=provider_cfg.get("default_model", "gemma3:1b"),
            timeout_sec=int(provider_cfg.get("timeout_sec", 60)),
        )
    if provider_type == "azure_openai":
        return AzureOpenAIClient(
            endpoint=provider_cfg.get("endpoint", ""),
            api_key_env=provider_cfg.get("api_key_env", "AZURE_OPENAI_API_KEY"),
            deployment=provider_cfg.get("deployment", ""),
            api_version=provider_cfg.get("api_version", "2024-02-01"),
            timeout_sec=int(provider_cfg.get("timeout_sec", 30)),
        )

    extra_headers = provider_cfg.get("headers") or {}
    return OpenAICompatClient(
        base_url=provider_cfg.get("base_url", ""),
        api_key_env=provider_cfg.get("api_key_env", "LLM_API_KEY"),
        default_model=provider_cfg.get("default_model", "gpt-4o-mini"),
        timeout_sec=int(provider_cfg.get("timeout_sec", 30)),
        extra_headers=extra_headers,
    )


def main():
    if load_dotenv:
        load_dotenv()

    cfg = load_config("config.yaml")
    provider_cfg = cfg.get("provider", {})
    app_cfg = cfg.get("app", {})

    client = _build_client(provider_cfg)
    action_map = build_action_map(cfg.get("actions", []))

    def dispatcher(action_id):
        action = action_map[action_id]
        handle_action(action, client, app_cfg, provider_cfg)

    register_hotkeys(action_map, dispatcher)

    print("[clipai] ✅ Running... Press Ctrl+C to stop.")
    while True:
        time.sleep(0.5)


if __name__ == "__main__":
    main()
