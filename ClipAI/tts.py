
import asyncio
import edge_tts
import io
import os
import logging
import time
import hashlib
import threading
from langdetect import detect, DetectorFactory
import pygame.mixer

# Ensure consistent language detection results
DetectorFactory.seed = 0

logger = logging.getLogger(__name__)

# Initialize pygame.mixer once at module level
_mixer_initialized = False

def _ensure_mixer_initialized():
    """Lazily initialize pygame.mixer on first use."""
    global _mixer_initialized
    if not _mixer_initialized:
        try:
            pygame.mixer.init()
            _mixer_initialized = True
            logger.info("pygame.mixer initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize pygame.mixer: {e}")
            raise

class TTSEngine:
    VOICE_MAP = {
        "zh-tw": "zh-TW-HsiaoChenNeural",
        "en": "en-US-GuyNeural",
        "ja": "ja-JP-NanamiNeural",
    }

    def __init__(self, voice="zh-TW-HsiaoChenNeural", rate="+0%", volume="+0%", proxy=None):
        self.default_voice = voice
        self.rate = rate
        self.volume = volume
        self.proxy = proxy
        self.temp_dir = "temp_audio"
        self.cache_dir = os.path.join(self.temp_dir, "tts_cache")
        self._playback_thread = None
        self.current_mode = "auto"
        self._stop_event = threading.Event()
        self._speak_id = 0
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

        # Phase 3: Persistent asyncio event loop
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._loop.run_forever, daemon=True
        )
        self._loop_thread.start()

    def set_mode(self, mode):
        if mode == "auto" or mode in self.VOICE_MAP:
            self.current_mode = mode
            logger.info(f"TTS mode set to: {mode}")

    def _detect_voice(self, text):
        if self.current_mode != "auto" and self.current_mode in self.VOICE_MAP:
            return self.VOICE_MAP[self.current_mode]
        try:
            lang = detect(text)
            return self.VOICE_MAP.get(lang, self.VOICE_MAP.get(lang.split('-')[0], self.default_voice))
        except:
            return self.default_voice

    def _play_audio_thread(self, output_path, delete_after, speak_id):
        """Play audio using pygame.mixer in a thread."""
        try:
            _ensure_mixer_initialized()
            pygame.mixer.music.load(output_path)
            pygame.mixer.music.play()

            while pygame.mixer.music.get_busy():
                if self._stop_event.is_set() or speak_id != self._speak_id:
                    pygame.mixer.music.stop()
                    break
                time.sleep(0.1)
        except Exception as e:
            logger.error(f"Playback error: {e}")
        finally:
            # Unload the music to release the file handle
            try:
                pygame.mixer.music.unload()
            except Exception:
                pass
            if delete_after:
                try:
                    if os.path.exists(output_path):
                        os.remove(output_path)
                except Exception:
                    pass

    async def _generate_and_play_text(self, text, speak_id):
        """Generate audio for full text and play it with cache/stop support.

        On cache miss, uses edge_tts streaming (communicate.stream()) so that
        the download can be cancelled mid-stream via _stop_event, reducing
        perceived latency on long texts.
        """
        if self._stop_event.is_set() or speak_id != self._speak_id:
            return

        selected_voice = self._detect_voice(text)
        cache_key = f"{selected_voice}|{self.rate}|{self.volume}|{text}".encode("utf-8")
        cache_hash = hashlib.md5(cache_key).hexdigest()
        cached_path = os.path.abspath(os.path.join(self.cache_dir, f"{cache_hash}.mp3"))

        output_path = cached_path
        delete_after = False

        try:
            if not os.path.exists(cached_path):
                # Phase 1: Stream audio chunks instead of communicate.save()
                timestamp = int(time.time() * 1000)
                output_path = os.path.abspath(os.path.join(self.temp_dir, f"tts_{timestamp}.mp3"))
                delete_after = True
                communicate = edge_tts.Communicate(
                    text,
                    selected_voice,
                    rate=self.rate,
                    volume=self.volume,
                    proxy=self.proxy
                )

                audio_buffer = io.BytesIO()
                stream_cancelled = False

                async for chunk in communicate.stream():
                    if self._stop_event.is_set() or speak_id != self._speak_id:
                        stream_cancelled = True
                        break
                    if chunk["type"] == "audio":
                        data = chunk.get("data")
                        if data:
                            audio_buffer.write(data)

                if stream_cancelled:
                    return

                # Write the streamed audio to the temp file
                audio_data = audio_buffer.getvalue()
                if audio_data:
                    with open(output_path, "wb") as f:
                        f.write(audio_data)

                    # Move to cache for future use
                    try:
                        os.replace(output_path, cached_path)
                        output_path = cached_path
                        delete_after = False
                    except Exception:
                        # Keep using temp file if cache move fails
                        pass

            if self._stop_event.is_set() or speak_id != self._speak_id:
                return

            if os.path.exists(output_path):
                t = threading.Thread(
                    target=self._play_audio_thread,
                    args=(output_path, delete_after, speak_id),
                    daemon=True,
                )
                t.start()
                self._playback_thread = t
                while t.is_alive():
                    if self._stop_event.is_set() or speak_id != self._speak_id:
                        pygame.mixer.music.stop()
                        t.join(timeout=0.5)
                        break
                    await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Error in TTS: {e}")

    def is_speaking(self):
        if self._playback_thread is not None and self._playback_thread.is_alive():
            return True
        try:
            if _mixer_initialized and pygame.mixer.music.get_busy():
                return True
        except Exception:
            pass
        return False

    def stop(self):
        stopped = False
        self._stop_event.set()
        try:
            if _mixer_initialized and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
                stopped = True
        except Exception:
            pass
        if self._playback_thread is not None and self._playback_thread.is_alive():
            self._playback_thread.join(timeout=0.5)
            stopped = True
        self._playback_thread = None
        return stopped

    def speak(self, text, on_start=None, on_end=None):
        """
        Speak full text (single request) with cache and stop support.

        Uses the persistent asyncio event loop (Phase 3) instead of creating
        a new thread + event loop per call.
        """
        self.stop()
        self._stop_event.clear()
        self._speak_id += 1
        speak_id = self._speak_id

        async def _run_with_callbacks():
            if on_start:
                on_start()
            try:
                await self._generate_and_play_text(text, speak_id)
            finally:
                if on_end:
                    on_end()

        asyncio.run_coroutine_threadsafe(_run_with_callbacks(), self._loop)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = TTSEngine()
    test_text = "這是第一句話。這是第二句話！反應速度應該會變快。這是一個長句子的測試，看看流暢度如何。"
    engine.speak(test_text)
    time.sleep(10)



