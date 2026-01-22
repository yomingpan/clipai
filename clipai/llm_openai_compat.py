import os
import requests


class OpenAICompatClient:
    def __init__(self, base_url: str, api_key_env: str, default_model: str, timeout_sec: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = os.getenv(api_key_env, "")
        self.default_model = default_model
        self.timeout_sec = timeout_sec

        if not self.api_key:
            raise RuntimeError(f"Missing API key in env var: {api_key_env}")

    def chat_completion(self, model: str, system_prompt: str, user_prompt: str, temperature: float, max_tokens: int) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout_sec)
        resp.raise_for_status()
        data = resp.json()

        return data["choices"][0]["message"]["content"].strip()
