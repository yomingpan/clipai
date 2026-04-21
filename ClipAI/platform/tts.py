
import asyncio
import hashlib
import io
import logging
import os
import threading
import time
from typing import Callable

import edge_tts
from langdetect import DetectorFactory, detect

try:
    import miniaudio
except ImportError:  # pragma: no cover - optional runtime dependency
    miniaudio = None

try:
    import pygame.mixer
except ImportError:  # pragma: no cover - optional runtime dependency
    pygame = None

# Ensure consistent language detection results
DetectorFactory.seed = 0

logger = logging.getLogger(__name__)

# Initialize pygame.mixer once at module level for fallback playback.
_mixer_initialized = False
STREAM_START_MIN_BYTES = 16 * 1024


class _QueuedStreamSource:
    def __init__(self, stop_event: threading.Event) -> None:
        self._stop_event = stop_event
        self._condition = threading.Condition()
        self._buffer = bytearray()
        self._eof = False
        self._closed = False
        # miniaudio.stream_any() expects StreamableSource-like state on the object.
        self.ffi_handle = getattr(miniaudio, "ffi", None).NULL if miniaudio is not None else None
        self.error_in_readcallback = None

    def feed(self, data: bytes) -> None:
        if not data:
            return
        with self._condition:
            if self._closed:
                return
            self._buffer.extend(data)
            self._condition.notify_all()

    def finish(self) -> None:
        with self._condition:
            self._eof = True
            self._condition.notify_all()

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def read(self, num_bytes: int) -> bytes:
        with self._condition:
            while (
                not self._buffer
                and not self._eof
                and not self._closed
                and not self._stop_event.is_set()
            ):
                self._condition.wait(timeout=0.1)
            if self._stop_event.is_set():
                self._closed = True
                return b""
            if self._buffer:
                chunk_size = min(num_bytes, len(self._buffer))
                data = bytes(self._buffer[:chunk_size])
                del self._buffer[:chunk_size]
                return data
            return b""

    def seek(self, offset: int, origin: int) -> bool:
        del offset, origin
        return False


def _ensure_mixer_initialized():
    """Lazily initialize pygame.mixer on first use."""
    global _mixer_initialized
    if pygame is None:
        raise RuntimeError("pygame-ce is not available for fallback TTS playback.")
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
        "en": "en-US-AndrewMultilingualNeural",
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
        self._playback_device = None
        self._playback_device_lock = threading.Lock()
        self._stream_source = None
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
            selected = self.VOICE_MAP[self.current_mode]
            logger.info("TTS voice resolved by manual mode: mode=%s voice=%s", self.current_mode, selected)
            return selected
        try:
            lang = detect(text)
            selected = self.VOICE_MAP.get(lang, self.VOICE_MAP.get(lang.split('-')[0], self.default_voice))
            logger.info("TTS voice resolved by auto detect: detected_lang=%s voice=%s", lang, selected)
            return selected
        except Exception as exc:
            logger.warning("TTS language detection failed, using default voice %s: %s", self.default_voice, exc)
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

    @staticmethod
    def _prime_generator(generator):
        next(generator)
        return generator

    def _wrap_miniaudio_stream(self, decoded_stream, speak_id: int, completion: threading.Event):
        def producer():
            required_frames = yield b""
            try:
                while not self._stop_event.is_set() and speak_id == self._speak_id:
                    try:
                        chunk = decoded_stream.send(required_frames)
                    except StopIteration:
                        break
                    required_frames = yield chunk
            finally:
                completion.set()
                close_fn = getattr(decoded_stream, "close", None)
                if callable(close_fn):
                    try:
                        close_fn()
                    except Exception:
                        pass

        return self._prime_generator(producer())

    def _start_miniaudio_playback(
        self,
        stream_factory: Callable[[threading.Event], object],
        speak_id: int,
        *,
        on_start: Callable[[], None] | None = None,
        stream_source: _QueuedStreamSource | None = None,
    ) -> dict[str, object]:
        done = threading.Event()
        error_holder: dict[str, Exception] = {}
        completion = threading.Event()

        def worker() -> None:
            device = None
            try:
                producer = stream_factory(completion)
                device = miniaudio.PlaybackDevice()
                with self._playback_device_lock:
                    if self._stop_event.is_set() or speak_id != self._speak_id:
                        completion.set()
                        return
                    self._playback_device = device
                    self._stream_source = stream_source
                device.start(producer)
                if on_start:
                    on_start()
                while not completion.wait(0.1):
                    if self._stop_event.is_set() or speak_id != self._speak_id:
                        try:
                            device.stop()
                        except Exception:
                            pass
                        break
            except Exception as exc:
                error_holder["error"] = exc
            finally:
                if stream_source is not None:
                    stream_source.close()
                if device is not None:
                    try:
                        device.close()
                    except Exception:
                        pass
                with self._playback_device_lock:
                    if self._playback_device is device:
                        self._playback_device = None
                    if self._stream_source is stream_source:
                        self._stream_source = None
                done.set()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        self._playback_thread = thread
        return {"thread": thread, "done": done, "error_holder": error_holder}

    async def _wait_for_playback(self, handle: dict[str, object], speak_id: int) -> None:
        done = handle["done"]
        error_holder = handle["error_holder"]
        while not done.is_set():
            if self._stop_event.is_set() or speak_id != self._speak_id:
                break
            await asyncio.sleep(0.05)
        error = error_holder.get("error")
        if error is not None:
            raise error

    async def _play_cached_with_miniaudio(
        self,
        path: str,
        speak_id: int,
        *,
        on_start: Callable[[], None] | None = None,
    ) -> None:
        handle = self._start_miniaudio_playback(
            lambda completion: self._wrap_miniaudio_stream(
                self._prime_generator(miniaudio.stream_file(path)),
                speak_id,
                completion,
            ),
            speak_id,
            on_start=on_start,
        )
        await self._wait_for_playback(handle, speak_id)

    async def _stream_synthesize_and_play(
        self,
        text: str,
        voice: str,
        cached_path: str,
        speak_id: int,
        *,
        on_request: Callable[[], None] | None = None,
        on_buffering: Callable[[], None] | None = None,
        on_start: Callable[[], None] | None = None,
    ) -> None:
        if on_request:
            on_request()
        logger.info("TTS synthesize request: voice=%s chars=%s streaming=miniaudio", voice, len(text))
        stream_source = _QueuedStreamSource(self._stop_event)
        playback_handle = None
        bytes_written = 0
        buffering_emitted = False
        communicate = edge_tts.Communicate(
            text,
            voice,
            rate=self.rate,
            volume=self.volume,
            proxy=self.proxy,
        )
        temp_path = f"{cached_path}.partial"
        try:
            with open(temp_path, "wb") as stream_file:
                async for chunk in communicate.stream():
                    if self._stop_event.is_set() or speak_id != self._speak_id:
                        stream_source.close()
                        self._cleanup_temp_file(temp_path)
                        return
                    if chunk["type"] != "audio":
                        continue
                    data = chunk.get("data")
                    if not data:
                        continue
                    if not buffering_emitted:
                        buffering_emitted = True
                        if on_buffering:
                            on_buffering()
                    stream_file.write(data)
                    stream_file.flush()
                    stream_source.feed(data)
                    bytes_written += len(data)
                    if playback_handle is None and bytes_written >= STREAM_START_MIN_BYTES:
                        playback_handle = self._start_miniaudio_playback(
                            lambda completion: self._wrap_miniaudio_stream(
                                self._prime_generator(
                                    miniaudio.stream_any(
                                        stream_source,
                                        source_format=miniaudio.FileFormat.MP3,
                                    )
                                ),
                                speak_id,
                                completion,
                            ),
                            speak_id,
                            on_start=on_start,
                            stream_source=stream_source,
                        )
            stream_source.finish()
            if bytes_written == 0:
                raise RuntimeError(f"No audio was received for voice {voice}.")
            if playback_handle is None:
                playback_handle = self._start_miniaudio_playback(
                    lambda completion: self._wrap_miniaudio_stream(
                        self._prime_generator(
                            miniaudio.stream_any(
                                stream_source,
                                source_format=miniaudio.FileFormat.MP3,
                            )
                        ),
                        speak_id,
                        completion,
                    ),
                    speak_id,
                    on_start=on_start,
                    stream_source=stream_source,
                )
            await self._wait_for_playback(playback_handle, speak_id)
            if not self._stop_event.is_set() and speak_id == self._speak_id:
                os.replace(temp_path, cached_path)
        except Exception:
            stream_source.close()
            self._cleanup_temp_file(temp_path)
            raise
        else:
            if self._stop_event.is_set() or speak_id != self._speak_id:
                self._cleanup_temp_file(temp_path)

    async def _generate_and_play_text(
        self,
        text,
        speak_id,
        *,
        on_request: Callable[[], None] | None = None,
        on_buffering: Callable[[], None] | None = None,
        on_start: Callable[[], None] | None = None,
    ):
        """Generate audio for full text and play it with cache/stop support.

        On cache miss, uses edge_tts streaming (communicate.stream()) so that
        the download can be cancelled mid-stream via _stop_event, reducing
        perceived latency on long texts.
        """
        if self._stop_event.is_set() or speak_id != self._speak_id:
            return

        try:
            voice = self._detect_voice(text)
            cache_key = f"{voice}|{self.rate}|{self.volume}|{text}".encode("utf-8")
            cache_hash = hashlib.md5(cache_key).hexdigest()
            cached_path = os.path.abspath(os.path.join(self.cache_dir, f"{cache_hash}.mp3"))
            if os.path.exists(cached_path):
                logger.info("TTS cache hit: voice=%s path=%s", voice, cached_path)
                if miniaudio is not None:
                    await self._play_cached_with_miniaudio(cached_path, speak_id, on_start=on_start)
                    return
                output_path = cached_path
                delete_after = False
            elif miniaudio is not None:
                await self._stream_synthesize_and_play(
                    text,
                    voice,
                    cached_path,
                    speak_id,
                    on_request=on_request,
                    on_buffering=on_buffering,
                    on_start=on_start,
                )
                return
            else:
                output_path, delete_after = await self._resolve_audio_path(text, speak_id)
            if output_path is None:
                return

            if self._stop_event.is_set() or speak_id != self._speak_id:
                return

            if os.path.exists(output_path):
                if on_request and output_path != cached_path:
                    on_request()
                if on_buffering and output_path != cached_path:
                    on_buffering()
                if on_start:
                    on_start()
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
            raise

    async def _resolve_audio_path(self, text, speak_id):
        voice = self._detect_voice(text)
        if self._stop_event.is_set() or speak_id != self._speak_id:
            return None, False

        cache_key = f"{voice}|{self.rate}|{self.volume}|{text}".encode("utf-8")
        cache_hash = hashlib.md5(cache_key).hexdigest()
        cached_path = os.path.abspath(os.path.join(self.cache_dir, f"{cache_hash}.mp3"))
        if os.path.exists(cached_path):
            logger.info("TTS cache hit: voice=%s path=%s", voice, cached_path)
            return cached_path, False

        timestamp = int(time.time() * 1000)
        output_path = os.path.abspath(os.path.join(self.temp_dir, f"tts_{timestamp}.mp3"))
        try:
            generated = await self._synthesize_voice_to_path(text, voice, output_path, speak_id)
        except Exception:
            self._cleanup_temp_file(output_path)
            raise

        if generated is None:
            return None, False
        if generated:
            try:
                os.replace(output_path, cached_path)
                return cached_path, False
            except Exception:
                return output_path, True

        self._cleanup_temp_file(output_path)
        raise RuntimeError(f"No audio was received for voice {voice}.")

    async def _synthesize_voice_to_path(self, text, voice, output_path, speak_id):
        logger.info("TTS synthesize request: voice=%s chars=%s", voice, len(text))
        communicate = edge_tts.Communicate(
            text,
            voice,
            rate=self.rate,
            volume=self.volume,
            proxy=self.proxy,
        )

        audio_buffer = io.BytesIO()
        async for chunk in communicate.stream():
            if self._stop_event.is_set() or speak_id != self._speak_id:
                return None
            if chunk["type"] == "audio":
                data = chunk.get("data")
                if data:
                    audio_buffer.write(data)

        audio_data = audio_buffer.getvalue()
        if not audio_data:
            return False

        with open(output_path, "wb") as f:
            f.write(audio_data)
        return True

    @staticmethod
    def _cleanup_temp_file(path):
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    def is_speaking(self):
        if self._playback_thread is not None and self._playback_thread.is_alive():
            return True
        with self._playback_device_lock:
            if self._playback_device is not None:
                return True
        try:
            if pygame is not None and _mixer_initialized and pygame.mixer.music.get_busy():
                return True
        except Exception:
            pass
        return False

    def stop(self):
        stopped = False
        self._stop_event.set()
        with self._playback_device_lock:
            playback_device = self._playback_device
            self._playback_device = None
            stream_source = self._stream_source
            self._stream_source = None
        if stream_source is not None:
            stream_source.close()
            stopped = True
        if playback_device is not None:
            try:
                playback_device.stop()
            except Exception:
                pass
            try:
                playback_device.close()
            except Exception:
                pass
            stopped = True
        try:
            if pygame is not None and _mixer_initialized and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
                stopped = True
        except Exception:
            pass
        if self._playback_thread is not None and self._playback_thread.is_alive():
            self._playback_thread.join(timeout=0.5)
            stopped = True
        self._playback_thread = None
        return stopped

    def speak(self, text, on_request=None, on_buffering=None, on_start=None, on_end=None):
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
            completed = False
            try:
                await self._generate_and_play_text(
                    text,
                    speak_id,
                    on_request=on_request,
                    on_buffering=on_buffering,
                    on_start=on_start,
                )
                completed = True
            finally:
                if completed and on_end:
                    on_end()

        asyncio.run_coroutine_threadsafe(_run_with_callbacks(), self._loop)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = TTSEngine()
    test_text = "這是第一句話。這是第二句話！反應速度應該會變快。這是一個長句子的測試，看看流暢度如何。"
    engine.speak(test_text)
    time.sleep(10)
