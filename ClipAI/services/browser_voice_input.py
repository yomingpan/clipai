from __future__ import annotations

import json
import logging
import socket
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from clipai.platform.clipboard import write_clipboard_text

logger = logging.getLogger("clipai.browser_voice_input")


@dataclass(frozen=True)
class BrowserVoiceInputConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    language: str = "zh-TW"
    auto_start: bool = False
    clipboard_mode: str = "replace_full_text"
    allow_port_fallback: bool = True

    @classmethod
    def from_mapping(cls, cfg: dict[str, Any] | None) -> "BrowserVoiceInputConfig":
        raw = cfg or {}
        return cls(
            host=str(raw.get("host") or "127.0.0.1"),
            port=int(raw.get("port") or 8765),
            language=str(raw.get("language") or "zh-TW"),
            auto_start=bool(raw.get("auto_start", False)),
            clipboard_mode=str(raw.get("clipboard_mode") or "replace_full_text"),
            allow_port_fallback=bool(raw.get("allow_port_fallback", True)),
        )


class BrowserVoiceInputState:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._text = ""

    @property
    def text(self) -> str:
        with self._lock:
            return self._text

    def append_transcript(self, transcript: str) -> str:
        chunk = transcript.strip()
        if not chunk:
            return self.text
        with self._lock:
            separator = "\n" if self._text and not self._text.endswith("\n") else ""
            self._text = f"{self._text}{separator}{chunk}"
            write_clipboard_text(self._text)
            return self._text

    def replace_text(self, text: str) -> str:
        with self._lock:
            self._text = text
            write_clipboard_text(self._text)
            return self._text

    def clear(self) -> None:
        self.replace_text("")


HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ClipAI Voice Input</title>
  <style>
    :root { color-scheme: light dark; font-family: "Segoe UI", "Microsoft JhengHei", Arial, sans-serif; background: #f6f7f9; color: #16181d; }
    body { margin: 0; min-height: 100vh; display: grid; grid-template-rows: auto 1fr auto; }
    header { display: flex; align-items: center; gap: 8px; padding: 12px; background: #fff; border-bottom: 1px solid #d8dde6; }
    button { height: 34px; padding: 0 12px; border: 1px solid #b9c0ca; border-radius: 6px; background: #fff; color: #16181d; font-size: 14px; cursor: pointer; }
    button.primary { background: #0f6cbd; border-color: #0f6cbd; color: #fff; }
    button.danger { background: #c42b1c; border-color: #c42b1c; color: #fff; }
    main { display: grid; grid-template-rows: auto 1fr; gap: 10px; padding: 12px; min-height: 0; }
    .interim { min-height: 34px; padding: 8px 10px; border: 1px solid #d0d6df; border-radius: 6px; background: #fffbe6; color: #5b4b00; font-size: 15px; line-height: 1.4; }
    textarea { width: 100%; height: 100%; min-height: 320px; box-sizing: border-box; resize: none; border: 1px solid #c8ced8; border-radius: 6px; padding: 12px; font-size: 18px; line-height: 1.55; background: #fff; color: #16181d; }
    footer { display: flex; justify-content: space-between; gap: 12px; padding: 10px 12px; border-top: 1px solid #d8dde6; background: #fff; color: #4e5968; font-size: 13px; }
    #status { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    @media (prefers-color-scheme: dark) {
      :root { background: #1c1f24; color: #f2f4f7; }
      header, footer, textarea, button { background: #262a31; color: #f2f4f7; border-color: #414852; }
      .interim { background: #302b18; border-color: #62562a; color: #ffe08a; }
      button.primary { background: #2d7dcb; border-color: #2d7dcb; }
      button.danger { background: #d13438; border-color: #d13438; }
    }
  </style>
</head>
<body>
  <header>
    <button id="start" class="primary">Start</button>
    <button id="stop" class="danger">Stop</button>
    <button id="copy">Copy</button>
    <button id="clear">Clear</button>
  </header>
  <main>
    <div id="interim" class="interim"></div>
    <textarea id="text" spellcheck="false"></textarea>
  </main>
  <footer>
    <span id="status">Ready</span>
    <span id="count">0 chars</span>
  </footer>
  <script>
    const CONFIG = __CONFIG__;
    const startButton = document.getElementById("start");
    const stopButton = document.getElementById("stop");
    const copyButton = document.getElementById("copy");
    const clearButton = document.getElementById("clear");
    const interimBox = document.getElementById("interim");
    const textBox = document.getElementById("text");
    const statusBox = document.getElementById("status");
    const countBox = document.getElementById("count");
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let recognition = null;
    let manualStop = false;
    let listening = false;

    function setStatus(value) { statusBox.textContent = value; }
    function updateCount() { countBox.textContent = `${textBox.value.length} chars`; }

    async function postJson(url, payload) {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    }

    async function appendFinal(transcript) {
      const value = transcript.trim();
      if (!value) return;
      const data = await postJson("/api/transcript", { text: value });
      textBox.value = data.text || "";
      updateCount();
    }

    function createRecognition() {
      const instance = new SpeechRecognition();
      instance.lang = CONFIG.language || "zh-TW";
      instance.continuous = true;
      instance.interimResults = true;
      instance.maxAlternatives = 1;
      instance.onstart = () => { listening = true; setStatus("Listening"); };
      instance.onerror = (event) => { setStatus(`Error: ${event.error || "unknown"}`); };
      instance.onend = () => {
        listening = false;
        interimBox.textContent = "";
        if (!manualStop) {
          setStatus("Restarting");
          window.setTimeout(() => {
            try { recognition.start(); } catch (error) { setStatus(String(error)); }
          }, 250);
          return;
        }
        setStatus("Stopped");
      };
      instance.onresult = (event) => {
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const result = event.results[i];
          const transcript = result[0].transcript;
          if (result.isFinal) appendFinal(transcript).catch((error) => setStatus(String(error)));
          else interim += transcript;
        }
        interimBox.textContent = interim;
        if (interim) setStatus("Listening");
      };
      return instance;
    }

    function start() {
      if (!SpeechRecognition) {
        setStatus("SpeechRecognition is not available. Use Chrome or Edge.");
        return;
      }
      if (listening) return;
      manualStop = false;
      recognition = recognition || createRecognition();
      try { recognition.start(); } catch (error) { setStatus(String(error)); }
    }

    startButton.addEventListener("click", start);
    stopButton.addEventListener("click", () => {
      manualStop = true;
      if (recognition) recognition.stop();
    });
    copyButton.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(textBox.value);
        setStatus("Copied");
      } catch (error) {
        textBox.select();
        document.execCommand("copy");
        setStatus("Copied with fallback");
      }
    });
    clearButton.addEventListener("click", async () => {
      await postJson("/api/clear", {});
      textBox.value = "";
      interimBox.textContent = "";
      updateCount();
      setStatus("Cleared");
    });
    textBox.addEventListener("input", async () => {
      updateCount();
      await postJson("/api/text", { text: textBox.value });
    });

    fetch("/api/state")
      .then((response) => response.json())
      .then((data) => { textBox.value = data.text || ""; updateCount(); })
      .catch((error) => setStatus(String(error)));

    if (!SpeechRecognition) setStatus("SpeechRecognition is not available. Use Chrome or Edge.");
    if (CONFIG.auto_start) window.setTimeout(start, 400);
  </script>
</body>
</html>
"""


def _json_response(handler: BaseHTTPRequestHandler, status: HTTPStatus, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status.value)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class BrowserVoiceInputServer:
    def __init__(
        self,
        config: BrowserVoiceInputConfig,
        *,
        state: BrowserVoiceInputState | None = None,
    ) -> None:
        self.config = config
        self.state = state or BrowserVoiceInputState()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._server is not None

    @property
    def url(self) -> str:
        server = self._server
        if server is None:
            return ""
        host, port = server.server_address[:2]
        return f"http://{host}:{port}/voice"

    def start(self) -> str:
        if self._server is not None:
            return self.url

        handler_cls = self._build_handler()
        try:
            server = ThreadingHTTPServer((self.config.host, self.config.port), handler_cls)
        except OSError:
            if not self.config.allow_port_fallback:
                raise
            server = ThreadingHTTPServer((self.config.host, 0), handler_cls)

        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._thread.start()
        logger.info("[clipai] Browser voice input server started: %s", self.url)
        return self.url

    def stop(self) -> None:
        server = self._server
        if server is None:
            return
        server.shutdown()
        server.server_close()
        self._server = None
        self._thread = None

    def _build_handler(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args) -> None:
                logger.debug("[clipai] Voice input HTTP: " + fmt, *args)

            def do_GET(self) -> None:
                if self.path in {"/", "/voice", "/voice/"}:
                    config_json = json.dumps(
                        {
                            "language": owner.config.language,
                            "auto_start": owner.config.auto_start,
                        }
                    )
                    body = HTML_TEMPLATE.replace("__CONFIG__", config_json).encode("utf-8")
                    self.send_response(HTTPStatus.OK.value)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/api/state":
                    _json_response(self, HTTPStatus.OK, {"text": owner.state.text})
                    return
                self.send_error(HTTPStatus.NOT_FOUND.value)

            def do_POST(self) -> None:
                try:
                    length = int(self.headers.get("Content-Length") or "0")
                    payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                    if self.path == "/api/transcript":
                        text = owner.state.append_transcript(str(payload.get("text") or ""))
                        _json_response(self, HTTPStatus.OK, {"text": text})
                        return
                    if self.path == "/api/text":
                        text = owner.state.replace_text(str(payload.get("text") or ""))
                        _json_response(self, HTTPStatus.OK, {"text": text})
                        return
                    if self.path == "/api/clear":
                        owner.state.clear()
                        _json_response(self, HTTPStatus.OK, {"text": ""})
                        return
                except Exception as exc:
                    logger.exception("[clipai] Voice input request failed: %s", exc)
                    _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                    return
                self.send_error(HTTPStatus.NOT_FOUND.value)

        return Handler


def is_local_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0
