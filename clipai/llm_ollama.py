import requests


class OllamaClient:
    def __init__(self, base_url: str, default_model: str, timeout_sec: int = 60):
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout_sec = timeout_sec

    def chat_completion(self, model: str, system_prompt: str, user_prompt: str, temperature: float, max_tokens: int) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        resp = requests.post(url, json=payload, timeout=self.timeout_sec)
        resp.raise_for_status()
        data = resp.json()

        return data["message"]["content"].strip()
