import time
from clipai.actions import load_config, build_action_map
from clipai.hotkeys import register_hotkeys
from clipai.llm_openai_compat import OpenAICompatClient
from clipai.llm_ollama import OllamaClient
from clipai.clipboard import read_clipboard_text, write_clipboard_text
from clipai.output import maybe_auto_paste
from clipai.safety import should_block_send
try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


def handle_action(action, client, app_cfg):
    text = read_clipboard_text()
    if not text.strip():
        print("[clipai] Clipboard is empty.")
        return

    if should_block_send(text):
        print("[clipai] Blocked: possible sensitive content detected.")
        return

    prompt = action["prompt"].strip()
    model = action.get("model") or client.default_model
    temperature = float(action.get("temperature", 0.3))
    max_tokens = int(action.get("max_tokens", 800))

    user_msg = f"=== Input ===\n{text}"

    print(f"[clipai] Action: {action['name']} | model={model}")
    try:
        result = client.chat_completion(
            model=model,
            system_prompt="You are a helpful assistant.",
            user_prompt=f"{prompt}\n\n{user_msg}",
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as e:
        print(f"[clipai] LLM call failed: {e}")
        return

    if app_cfg.get("add_result_header", False):
        result = f"[{action['name']}]\n{result}"

    write_clipboard_text(result)
    print("[clipai] ✅ Result copied to clipboard.")

    auto_paste = action.get("auto_paste", app_cfg.get("auto_paste_default", False))
    if auto_paste:
        maybe_auto_paste()


def main():
    if load_dotenv:
        load_dotenv()

    cfg = load_config("config.yaml")
    provider_cfg = cfg["provider"]
    app_cfg = cfg.get("app", {})

    provider_type = provider_cfg.get("type", "openai_compat").lower()
    if provider_type == "ollama":
        client = OllamaClient(
            base_url=provider_cfg.get("base_url", "http://localhost:11434"),
            default_model=provider_cfg.get("default_model", "gemma3:1b"),
            timeout_sec=int(provider_cfg.get("timeout_sec", 60)),
        )
    else:
        client = OpenAICompatClient(
            base_url=provider_cfg["base_url"],
            api_key_env=provider_cfg["api_key_env"],
            default_model=provider_cfg.get("default_model", "gpt-4o-mini"),
            timeout_sec=int(provider_cfg.get("timeout_sec", 30)),
        )

    action_map = build_action_map(cfg["actions"])

    def dispatcher(action_id):
        action = action_map[action_id]
        handle_action(action, client, app_cfg)

    register_hotkeys(action_map, dispatcher)

    print("[clipai] ✅ Running... Press Ctrl+C to stop.")
    while True:
        time.sleep(0.5)


if __name__ == "__main__":
    main()
