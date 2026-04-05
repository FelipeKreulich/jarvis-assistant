#!/usr/bin/env python3
"""Jarvis — AI Voice Assistant with animated orb interface."""

import ctypes
import os
import subprocess
import sys
import threading

# Suppress ALSA/JACK errors before anything else loads
os.environ["JACK_NO_START_SERVER"] = "1"
os.environ["JACK_NO_AUDIO_RESERVATION"] = "1"
try:
    _ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(
        None, ctypes.c_char_p, ctypes.c_int,
        ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p
    )
    _alsa_error_handler = _ERROR_HANDLER_FUNC(lambda *_: None)
    _asound = ctypes.cdll.LoadLibrary("libasound.so.2")
    _asound.snd_lib_error_set_handler(_alsa_error_handler)
except Exception:
    pass

from PyQt6.QtCore import Qt, QPoint, pyqtSignal, pyqtSlot, QSize
from PyQt6.QtGui import QColor, QIcon, QPainter, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QInputDialog,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from audio import AudioEngine
from config import get_api_key, set_api_key
from gemini_client import GeminiClient
from orb_widget import OrbWidget


class TitleBarButton(QPushButton):
    def __init__(self, text: str, color: str, hover_color: str, parent=None):
        super().__init__(text, parent)
        self.setFixedSize(32, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 16px;
                color: {color};
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {hover_color};
                color: white;
            }}
        """)


class MainWindow(QMainWindow):
    # Signals for cross-thread UI updates
    _set_state_sig = pyqtSignal(str)
    _set_amplitude_sig = pyqtSignal(float)
    _speak_sig = pyqtSignal(str)
    _error_sig = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jarvis")
        self.setMinimumSize(400, 400)
        self.resize(600, 600)

        # Frameless window
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        # For window dragging
        self._drag_pos: QPoint | None = None
        # For resizing
        self._resize_edge: str | None = None
        self._resize_start_pos: QPoint | None = None
        self._resize_start_geom = None
        self.setMouseTracking(True)

        # Central widget
        central = QWidget()
        central.setStyleSheet("background: #050810;")
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Title bar area with buttons
        title_bar = QWidget()
        title_bar.setFixedHeight(44)
        title_bar.setStyleSheet("background: transparent;")
        title_bar.setMouseTracking(True)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(12, 8, 12, 0)
        title_layout.addStretch()

        btn_min = TitleBarButton("—", "rgba(255,255,255,0.4)", "rgba(255,255,255,0.15)")
        btn_min.clicked.connect(self.showMinimized)
        title_layout.addWidget(btn_min)

        btn_close = TitleBarButton("×", "rgba(255,255,255,0.4)", "rgba(220,50,50,0.7)")
        btn_close.clicked.connect(self.close)
        title_layout.addWidget(btn_close)

        layout.addWidget(title_bar)

        # Orb
        self.orb = OrbWidget()
        self.orb.setStyleSheet("background: #050810;")
        layout.addWidget(self.orb, stretch=1)

        # Status label area
        self.status_label = QPushButton("Press SPACE to talk")
        self.status_label.setFlat(True)
        self.status_label.setEnabled(False)
        self.status_label.setFixedHeight(36)
        self.status_label.setStyleSheet("""
            QPushButton {
                color: rgba(255,255,255,0.25);
                background: transparent;
                border: none;
                font-size: 12px;
                font-family: monospace;
            }
        """)
        layout.addWidget(self.status_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Center on screen
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(
                geo.center().x() - self.width() // 2,
                geo.center().y() - self.height() // 2,
            )

        # Audio engine
        self.audio = AudioEngine()
        self.audio.amplitude_changed.connect(self._on_mic_amplitude)
        self.audio.recording_finished.connect(self._on_recording_finished)
        self.audio.tts_started.connect(lambda: self._set_state("speaking"))
        self.audio.tts_amplitude.connect(self._on_tts_amplitude)
        self.audio.tts_finished.connect(lambda: self._set_state("idle"))
        self.audio.error_occurred.connect(self._on_error)

        # Internal signals
        self._set_state_sig.connect(self._apply_state)
        self._set_amplitude_sig.connect(self.orb.set_amplitude)
        self._speak_sig.connect(self._do_speak)
        self._error_sig.connect(self._on_error)

        # Gemini client
        self.gemini: GeminiClient | None = None
        self._state = "idle"
        self._recording = False

        # Init API key
        self._init_gemini()

    def _init_gemini(self):
        key = get_api_key()
        if not key:
            key, ok = QInputDialog.getText(
                self,
                "Jarvis — API Key",
                "Enter your Groq API key:",
            )
            if ok and key.strip():
                set_api_key(key.strip())
            else:
                sys.exit(0)
        self.gemini = GeminiClient(key)

    # ── State management ──

    def _set_state(self, state: str):
        self._set_state_sig.emit(state)

    @pyqtSlot(str)
    def _apply_state(self, state: str):
        self._state = state
        self.orb.set_state(state)
        labels = {
            "idle": "Press SPACE to talk",
            "listening": "Listening...",
            "thinking": "Thinking...",
            "speaking": "Speaking...",
            "error": "Error occurred",
        }
        self.status_label.setText(labels.get(state, ""))

    # ── Audio callbacks ──

    @pyqtSlot(float)
    def _on_mic_amplitude(self, amp: float):
        self._set_amplitude_sig.emit(amp)

    @pyqtSlot(float)
    def _on_tts_amplitude(self, amp: float):
        self._set_amplitude_sig.emit(amp)

    @pyqtSlot(bytes)
    def _on_recording_finished(self, wav_data: bytes):
        self._set_state("thinking")
        threading.Thread(target=self._process_speech, args=(wav_data,), daemon=True).start()

    def _process_speech(self, wav_data: bytes):
        text = self.audio.recognize_speech(wav_data)
        if not text:
            self._error_sig.emit("Could not understand audio")
            return

        try:
            response = self.gemini.send_message(text)
        except Exception as e:
            self._error_sig.emit(f"Gemini error: {e}")
            return

        # Extract ACTION:RUN: from anywhere in the response
        import re
        match = re.search(r"ACTION:RUN:(.+)", response)
        if match:
            cmd = match.group(1).strip()
            print(f"[CMD] Executing: {cmd}")
            try:
                # GUI apps (ending with &) — launch detached, don't wait
                if cmd.endswith("&"):
                    subprocess.Popen(
                        cmd, shell=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    self._speak_sig.emit("Pronto.")
                else:
                    result = subprocess.run(
                        cmd, shell=True, capture_output=True, text=True, timeout=15
                    )
                    output = result.stdout.strip() or result.stderr.strip() or "Pronto."
                    if len(output) > 300:
                        output = output[:300]
                    self._speak_sig.emit(output)
            except subprocess.TimeoutExpired:
                self._speak_sig.emit("O comando demorou demais.")
            except Exception as e:
                self._speak_sig.emit(f"Erro ao executar: {e}")
        else:
            self._speak_sig.emit(response)

    @pyqtSlot(str)
    def _do_speak(self, text: str):
        self.audio.speak(text)

    @pyqtSlot(str)
    def _on_error(self, msg: str):
        print(f"[ERROR] {msg}", file=sys.stderr)
        self._set_state("error")
        # Return to idle after a short delay
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(1500, lambda: self._set_state("idle"))

    # ── Input handling ──

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            if not self._recording and self._state in ("idle",):
                self._recording = True
                self._set_state("listening")
                self.audio.start_recording()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            if self._recording:
                self._recording = False
                self.audio.stop_recording()
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._get_resize_edge(event.pos())
            if edge:
                self._resize_edge = edge
                self._resize_start_pos = event.globalPosition().toPoint()
                self._resize_start_geom = self.geometry()
            else:
                # Click on orb area to toggle recording
                orb_center_y = self.height() // 2
                click_y = event.pos().y()
                if abs(click_y - orb_center_y) < self.height() * 0.4:
                    if not self._recording and self._state == "idle":
                        self._recording = True
                        self._set_state("listening")
                        self.audio.start_recording()
                    elif self._recording:
                        self._recording = False
                        self.audio.stop_recording()
                    else:
                        self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                else:
                    self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resize_edge and self._resize_start_pos:
            self._do_resize(event.globalPosition().toPoint())
        elif self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        else:
            edge = self._get_resize_edge(event.pos())
            if edge in ("left", "right"):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif edge in ("top", "bottom"):
                self.setCursor(Qt.CursorShape.SizeVerCursor)
            elif edge in ("top-left", "bottom-right"):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif edge in ("top-right", "bottom-left"):
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self._resize_edge = None
        self._resize_start_pos = None
        self._resize_start_geom = None
        super().mouseReleaseEvent(event)

    def _get_resize_edge(self, pos: QPoint) -> str | None:
        margin = 8
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        left = x < margin
        right = x > w - margin
        top = y < margin
        bottom = y > h - margin
        if top and left: return "top-left"
        if top and right: return "top-right"
        if bottom and left: return "bottom-left"
        if bottom and right: return "bottom-right"
        if left: return "left"
        if right: return "right"
        if top: return "top"
        if bottom: return "bottom"
        return None

    def _do_resize(self, global_pos: QPoint):
        dx = global_pos.x() - self._resize_start_pos.x()
        dy = global_pos.y() - self._resize_start_pos.y()
        g = self._resize_start_geom
        new_x, new_y, new_w, new_h = g.x(), g.y(), g.width(), g.height()
        min_w, min_h = self.minimumWidth(), self.minimumHeight()
        edge = self._resize_edge
        if "right" in edge:
            new_w = max(min_w, g.width() + dx)
        if "bottom" in edge:
            new_h = max(min_h, g.height() + dy)
        if "left" in edge:
            new_w = max(min_w, g.width() - dx)
            if new_w != min_w:
                new_x = g.x() + dx
        if "top" in edge:
            new_h = max(min_h, g.height() - dy)
            if new_h != min_h:
                new_y = g.y() + dy
        self.setGeometry(new_x, new_y, new_w, new_h)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Jarvis")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
