import requests


class OllamaClient:
    def __init__(self, base_url: str, default_model: str, timeout_sec: int = 60):
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout_sec = timeout_sec

    def chat_completion(self, model: str, messages, temperature: float, max_tokens: int, response_format=None) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": model,
            "stream": False,
            "messages": messages,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        resp = requests.post(url, json=payload, timeout=self.timeout_sec)
        resp.raise_for_status()
        data = resp.json()

        return data["message"]["content"].strip()
