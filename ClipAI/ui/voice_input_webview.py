from __future__ import annotations

import argparse
import base64
import logging
from typing import Any

from clipai.actions import load_config
from clipai.platform.clipboard import write_clipboard_text
from clipai.services.voice_transcription import OpenAITranscriptionClient, OpenAITranscriptionConfig

logger = logging.getLogger("clipai.voice_input")


HTML = r"""
<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root { color-scheme: light dark; font-family: "Segoe UI", "Microsoft JhengHei", sans-serif; }
    body { margin: 0; background: #f7f7f8; color: #15171a; }
    main { display: grid; grid-template-rows: auto 1fr auto; height: 100vh; }
    header { display: flex; align-items: center; gap: 8px; padding: 12px; border-bottom: 1px solid #dadde2; background: #ffffff; }
    button, select { height: 34px; border: 1px solid #b9c0ca; background: #fff; color: #15171a; border-radius: 6px; padding: 0 10px; font-size: 13px; }
    button.primary { background: #0f6cbd; color: #fff; border-color: #0f6cbd; }
    button.danger { background: #c42b1c; color: #fff; border-color: #c42b1c; }
    textarea { resize: none; width: calc(100% - 24px); height: calc(100% - 24px); margin: 12px; box-sizing: border-box; border: 1px solid #c8ccd3; border-radius: 6px; padding: 12px; font-size: 17px; line-height: 1.55; background: #fff; color: #15171a; }
    footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 12px; border-top: 1px solid #dadde2; background: #ffffff; font-size: 12px; color: #4f5965; }
    .status { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    @media (prefers-color-scheme: dark) {
      body { background: #1b1d21; color: #f2f3f5; }
      header, footer, textarea, button, select { background: #24272d; color: #f2f3f5; border-color: #3b414b; }
      button.primary { background: #2d7dcb; border-color: #2d7dcb; }
      button.danger { background: #d13438; border-color: #d13438; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <button id="start" class="primary">Start</button>
      <button id="stop" class="danger">Stop</button>
      <select id="mode">
        <option value="google">Google Web Speech</option>
        <option value="openai">OpenAI Whisper</option>
      </select>
      <button id="clear">Clear</button>
    </header>
    <textarea id="text" spellcheck="false"></textarea>
    <footer>
      <span id="status" class="status">Ready</span>
      <span id="count">0 chars</span>
    </footer>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);
    const text = $("text");
    const status = $("status");
    const count = $("count");
    const mode = $("mode");
    let recognition = null;
    let recorder = null;
    let stream = null;
    let finalText = "";
    let manualStop = false;
    let busy = false;

    function setStatus(value) { status.textContent = value; }
    function updateText(value) {
      finalText = value;
      text.value = finalText;
      count.textContent = `${finalText.length} chars`;
      window.pywebview.api.set_clipboard(finalText);
    }
    function appendText(value) {
      const chunk = (value || "").trim();
      if (!chunk) return;
      const separator = finalText && !finalText.endsWith("\n") ? "\n" : "";
      updateText(finalText + separator + chunk);
    }
    function getSpeechRecognition() {
      return window.SpeechRecognition || window.webkitSpeechRecognition;
    }
    async function startGoogle() {
      const SpeechRecognition = getSpeechRecognition();
      if (!SpeechRecognition) {
        setStatus("This WebView does not expose SpeechRecognition. Try OpenAI Whisper mode.");
        return;
      }
      manualStop = false;
      recognition = new SpeechRecognition();
      recognition.lang = "zh-TW";
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.onstart = () => setStatus("Listening with Google Web Speech");
      recognition.onerror = (event) => setStatus(`Speech error: ${event.error || "unknown"}`);
      recognition.onend = () => {
        if (!manualStop) {
          try { recognition.start(); } catch (error) { setStatus(String(error)); }
        } else {
          setStatus("Stopped");
        }
      };
      recognition.onresult = (event) => {
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcript = event.results[i][0].transcript;
          if (event.results[i].isFinal) appendText(transcript);
          else interim += transcript;
        }
        if (interim) setStatus(`Listening: ${interim}`);
      };
      recognition.start();
    }
    function blobToDataUrl(blob) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(blob);
      });
    }
    async function startOpenAI() {
      manualStop = false;
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      recorder.onstart = () => setStatus("Listening with OpenAI Whisper");
      recorder.onerror = (event) => setStatus(`Recorder error: ${event.error || "unknown"}`);
      recorder.ondataavailable = async (event) => {
        if (!event.data || event.data.size < 1024 || busy) return;
        busy = true;
        try {
          setStatus("Transcribing...");
          const dataUrl = await blobToDataUrl(event.data);
          const transcript = await window.pywebview.api.transcribe_audio(dataUrl);
          appendText(transcript);
          setStatus("Listening with OpenAI Whisper");
        } catch (error) {
          setStatus(String(error));
        } finally {
          busy = false;
        }
      };
      recorder.start(8000);
    }
    async function start() {
      if (mode.value === "google") await startGoogle();
      else await startOpenAI();
    }
    function stop() {
      manualStop = true;
      if (recognition) recognition.stop();
      if (recorder && recorder.state !== "inactive") recorder.stop();
      if (stream) stream.getTracks().forEach((track) => track.stop());
      setStatus("Stopped");
    }
    $("start").addEventListener("click", start);
    $("stop").addEventListener("click", stop);
    $("clear").addEventListener("click", () => updateText(""));
    text.addEventListener("input", () => updateText(text.value));
    window.addEventListener("pywebviewready", async () => {
      const cfg = await window.pywebview.api.get_config();
      mode.value = cfg.mode || "google";
      if (cfg.auto_start) start();
    });
  </script>
</body>
</html>
"""


class VoiceInputApi:
    def __init__(self, cfg: dict[str, Any]) -> None:
        voice_cfg = dict(cfg.get("voice_input", {}) or {})
        openai_cfg = OpenAITranscriptionConfig.from_mapping(voice_cfg.get("openai"))
        self._client = OpenAITranscriptionClient(openai_cfg)
        backend = str(voice_cfg.get("backend") or "").lower()
        default_mode = "openai" if backend in {"openai", "openai_transcribe"} else "google"
        self._mode = str(voice_cfg.get("mode") or default_mode).lower()
        self._auto_start = bool(voice_cfg.get("auto_start", True))

    def get_config(self) -> dict[str, Any]:
        return {"mode": self._mode, "auto_start": self._auto_start}

    def set_clipboard(self, text: str) -> bool:
        write_clipboard_text(text or "")
        return True

    def transcribe_audio(self, data_url: str) -> str:
        _, _, payload = str(data_url or "").partition(",")
        audio_bytes = base64.b64decode(payload)
        return self._client.transcribe_webm(audio_bytes)


def run_voice_input_window(config_path: str) -> None:
    try:
        import webview
    except ImportError as exc:
        raise RuntimeError("pywebview is required for voice input WebView. Install it with: pip install pywebview") from exc

    cfg = load_config(config_path)
    api = VoiceInputApi(cfg)
    webview.create_window("ClipAI Voice Input", html=HTML, js_api=api, width=620, height=520, resizable=True)
    webview.start(http_server=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/config.yaml")
    args = parser.parse_args()
    run_voice_input_window(args.config)


if __name__ == "__main__":
    main()
