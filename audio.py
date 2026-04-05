import asyncio
import io
import subprocess
import tempfile
import threading
import wave

import edge_tts
import numpy as np
import pyaudio
import speech_recognition as sr
from PyQt6.QtCore import QObject, pyqtSignal


CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
MIN_RECORD_FRAMES = 16  # minimum ~1 second of audio


class AudioEngine(QObject):
    amplitude_changed = pyqtSignal(float)
    recording_finished = pyqtSignal(bytes)
    tts_started = pyqtSignal()
    tts_amplitude = pyqtSignal(float)
    tts_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._recording = False
        self._frames: list[bytes] = []
        self._pa: pyaudio.PyAudio | None = None
        self._stream = None
        self._recognizer = sr.Recognizer()
        self._tts_process: subprocess.Popen | None = None

    def start_recording(self):
        self._frames = []
        self._recording = True
        threading.Thread(target=self._record_loop, daemon=True).start()

    def stop_recording(self):
        self._recording = False

    def _record_loop(self):
        try:
            self._pa = pyaudio.PyAudio()
            self._stream = self._pa.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
            )
            while self._recording:
                data = self._stream.read(CHUNK, exception_on_overflow=False)
                self._frames.append(data)
                samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                amplitude = np.sqrt(np.mean(samples ** 2)) / 32768.0
                self.amplitude_changed.emit(min(amplitude * 4.0, 1.0))
        except Exception as e:
            self.error_occurred.emit(f"Recording error: {e}")
        finally:
            if self._stream:
                self._stream.stop_stream()
                self._stream.close()
            if self._pa:
                self._pa.terminate()
            self._pa = None
            self._stream = None
            if len(self._frames) >= MIN_RECORD_FRAMES:
                audio_data = self._build_wav()
                self.recording_finished.emit(audio_data)
            elif self._frames:
                self.error_occurred.emit("Recording too short — hold Space longer")

    def _build_wav(self) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(RATE)
            wf.writeframes(b"".join(self._frames))
        return buf.getvalue()

    def recognize_speech(self, wav_data: bytes) -> str | None:
        try:
            # Parse WAV properly instead of hardcoded header skip
            buf = io.BytesIO(wav_data)
            with wave.open(buf, "rb") as wf:
                raw = wf.readframes(wf.getnframes())
                sample_rate = wf.getframerate()
                sample_width = wf.getsampwidth()

            # Check if audio has actual content
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            rms = np.sqrt(np.mean(samples ** 2))
            print(f"[DEBUG] Audio: {len(raw)} bytes, RMS={rms:.1f}, duration={len(raw)/sample_rate/sample_width:.1f}s")

            if rms < 50:
                self.error_occurred.emit("No speech detected — mic may be muted")
                return None

            audio = sr.AudioData(raw, sample_rate=sample_rate, sample_width=sample_width)
            # Try Portuguese first, fallback to English
            text = None
            for lang in ("pt-BR", "en-US"):
                try:
                    text = self._recognizer.recognize_google(audio, language=lang)
                    print(f"[DEBUG] Recognized ({lang}): {text}")
                    break
                except sr.UnknownValueError:
                    continue
            if not text:
                return None
            return text
        except sr.RequestError as e:
            self.error_occurred.emit(f"STT network error: {e}")
            return None
        except Exception as e:
            self.error_occurred.emit(f"STT error: {e}")
            return None

    def speak(self, text: str):
        threading.Thread(target=self._speak_thread, args=(text,), daemon=True).start()

    def _speak_thread(self, text: str):
        try:
            self.tts_started.emit()

            # Use Edge TTS for natural-sounding voice
            mp3_data = asyncio.run(self._edge_tts_synthesize(text))

            if not mp3_data:
                self.tts_finished.emit()
                return

            # Decode MP3 to WAV using ffmpeg
            proc = subprocess.run(
                ["ffmpeg", "-i", "pipe:0", "-f", "wav", "-acodec", "pcm_s16le",
                 "-ar", "24000", "-ac", "1", "pipe:1"],
                input=mp3_data,
                capture_output=True,
            )
            wav_data = proc.stdout

            if not wav_data or len(wav_data) < 100:
                self.tts_finished.emit()
                return

            # Play audio and emit amplitude
            pa = pyaudio.PyAudio()
            try:
                buf = io.BytesIO(wav_data)
                with wave.open(buf, "rb") as wf:
                    stream = pa.open(
                        format=pa.get_format_from_width(wf.getsampwidth()),
                        channels=wf.getnchannels(),
                        rate=wf.getframerate(),
                        output=True,
                    )
                    chunk_size = 1024
                    data = wf.readframes(chunk_size)
                    while data:
                        stream.write(data)
                        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                        if len(samples) > 0:
                            amp = np.sqrt(np.mean(samples ** 2)) / 32768.0
                            self.tts_amplitude.emit(min(amp * 4.0, 1.0))
                        data = wf.readframes(chunk_size)
                    stream.stop_stream()
                    stream.close()
            finally:
                pa.terminate()
        except Exception as e:
            self.error_occurred.emit(f"TTS error: {e}")
        finally:
            self.tts_finished.emit()

    async def _edge_tts_synthesize(self, text: str) -> bytes:
        # Auto-detect language for voice selection
        voice = "en-US-GuyNeural"  # default English male
        # Simple heuristic: if text has Portuguese characters/patterns, use PT voice
        pt_indicators = ("ã", "õ", "ç", "é", "ê", "á", "ó", "ú", "não", "sim",
                         "como", "que", "para", "uma", "você", "está", "isso")
        if any(ind in text.lower() for ind in pt_indicators):
            voice = "pt-BR-AntonioNeural"

        communicate = edge_tts.Communicate(text, voice, rate="+10%")
        chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
        return b"".join(chunks)
