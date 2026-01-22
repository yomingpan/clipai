import os
import requests


class AzureOpenAIClient:
    def __init__(self, endpoint: str, api_key_env: str, deployment: str, api_version: str, timeout_sec: int = 30):
        self.endpoint = endpoint.rstrip("/")
        self.api_key = os.getenv(api_key_env, "") if api_key_env else ""
        self.deployment = deployment
        self.api_version = api_version
        self.timeout_sec = timeout_sec

        if api_key_env and not self.api_key:
            raise RuntimeError(f"Missing API key in env var: {api_key_env}")

    def chat_completion(self, model: str, messages, temperature: float, max_tokens: int, response_format=None) -> str:
        # model is ignored for Azure; deployment is used instead
        url = f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions"
        params = {"api-version": self.api_version}
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if response_format:
            payload["response_format"] = response_format

        resp = requests.post(url, headers=headers, params=params, json=payload, timeout=self.timeout_sec)
        resp.raise_for_status()
        data = resp.json()

        return data["choices"][0]["message"]["content"].strip()
