"""
android_main.py — Mobile Application & Holographic HUD for Mark-LIV on Android

Features:
  • Iron Man Arc Reactor animated HUD (pulsing core, audio-reactive rings)
  • Real-time Gemini Live bidirectional audio streaming
  • Background Wake-Word ("Hey Jarvis") toggle and status
  • Push-to-Talk (PTT) and Live Audio Level Visualizer
  • Embedded Local FastAPI Dashboard Server (`http://127.0.0.1:8000`)
  • Auto-request Android Runtime Permissions (Microphone, Storage, Notifications)
  • Complete integration with Mark-LIV core actions, memory, and plugins
"""
from __future__ import annotations

import os
import sys
import math
import time
import json
import queue
import threading
import asyncio
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Kivy Mobile Framework
import kivy
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

# Mark-LIV Core Imports
import numpy as np
from core.android_audio import InputStream, RawOutputStream
from core.action_loader import discover_actions
from core.plugin_loader import discover_plugins
from core.wake_word import WakeWordDetector
from memory.config_manager import (
    load_api_keys, save_api_keys, get_gemini_key, get_assistant_name,
    get_wake_word_enabled, save_wake_word_enabled,
)

IS_ANDROID = sys.platform == "android" or "ANDROID_ARGUMENT" in os.environ


# ─────────────────────────────────────────────────────────────────────────────
# Android Runtime Permissions
# ─────────────────────────────────────────────────────────────────────────────
def request_android_permissions():
    """Request runtime permissions required for Android 6.0+."""
    if not IS_ANDROID:
        return
    try:
        from android.permissions import Permission, request_permissions

        def callback(permissions, grant_results):
            print(f"[Permissions] Granted: {grant_results}")

        request_permissions(
            [
                Permission.RECORD_AUDIO,
                Permission.INTERNET,
                Permission.ACCESS_NETWORK_STATE,
                Permission.POST_NOTIFICATIONS,
            ],
            callback,
        )
    except Exception as e:
        print(f"[Permissions] Request error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Arc Reactor Holographic HUD Widget
# ─────────────────────────────────────────────────────────────────────────────
class ArcReactorHUD(Widget):
    """
    Renders an animated Arc Reactor HUD with glowing concentric rings
    and dynamic audio reactivity that expands and contracts with speech.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.audio_level = 0.0
        self.pulse_phase = 0.0
        self.status_text = "INITIALIZING"
        self.bind(pos=self.redraw, size=self.redraw)
        Clock.schedule_interval(self._tick_animation, 1.0 / 30.0)

    def set_audio_level(self, level: float):
        # Smooth interpolation
        self.audio_level = self.audio_level * 0.4 + max(0.0, min(1.0, level)) * 0.6
        self.redraw()

    def _tick_animation(self, dt):
        self.pulse_phase = (self.pulse_phase + dt * 2.0) % (2.0 * math.pi)
        self.redraw()

    def redraw(self, *args):
        self.canvas.clear()
        cx, cy = self.center_x, self.center_y
        min_dim = min(self.width, self.height)
        radius = (min_dim / 2.0) * 0.75

        with self.canvas:
            # 1. Dark glowing background
            Color(0.02, 0.05, 0.1, 0.8)
            Ellipse(pos=(cx - radius, cy - radius), size=(radius * 2, radius * 2))

            # 2. Outer pulse ring
            pulse_mod = math.sin(self.pulse_phase) * 6.0
            Color(0.0, 0.8, 1.0, 0.4 + 0.3 * self.audio_level)
            Line(circle=(cx, cy, radius + pulse_mod), width=2.0)

            # 3. Audio-reactive waveform ring
            audio_radius = radius * 0.85 + self.audio_level * 25.0
            Color(0.2, 0.9, 1.0, 0.8)
            Line(circle=(cx, cy, audio_radius), width=3.0)

            # 4. Segmented reactor segments (10 arc segments)
            num_segments = 10
            seg_radius = radius * 0.65
            for i in range(num_segments):
                angle_deg = i * (360.0 / num_segments) + (self.pulse_phase * 15.0)
                start_angle = math.radians(angle_deg)
                end_angle = math.radians(angle_deg + 24.0)

                Color(0.0, 0.9, 0.95, 0.7)
                x1 = cx + math.cos(start_angle) * seg_radius
                y1 = cy + math.sin(start_angle) * seg_radius
                x2 = cx + math.cos(end_angle) * seg_radius
                y2 = cy + math.sin(end_angle) * seg_radius
                Line(points=[x1, y1, x2, y2], width=4.0)

            # 5. Glowing inner core
            core_radius = radius * 0.32 + self.audio_level * 15.0
            Color(0.4, 0.95, 1.0, 0.9)
            Ellipse(pos=(cx - core_radius, cy - core_radius), size=(core_radius * 2, core_radius * 2))

            Color(1.0, 1.0, 1.0, 0.95)
            Line(circle=(cx, cy, core_radius), width=2.0)


# ─────────────────────────────────────────────────────────────────────────────
# Main Android Application Window
# ─────────────────────────────────────────────────────────────────────────────
class MarkLIVAndroidApp(App):
    def build(self):
        Window.clearcolor = (0.04, 0.07, 0.12, 1.0)
        self.title = "MARK-LIV — Mobile AI Voice Assistant"

        self.audio_in_queue = queue.Queue(maxsize=100)
        self.is_streaming = False
        self.is_listening = False
        self.wake_detector = None
        self.mic_stream = None
        self.speaker_stream = None
        self.gemini_session = None

        request_android_permissions()
        self._start_dashboard_server()
        self._init_audio_and_plugins()

        # Build UI layout
        root = BoxLayout(orientation="vertical", padding=15, spacing=10)

        # 1. Header Bar
        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=45)
        title_label = Label(
            text="[b]MARK-LIV[/b]  //  JARVIS MOBILE",
            markup=True,
            font_size="18sp",
            color=(0.0, 0.85, 1.0, 1.0),
            halign="left",
        )
        title_label.bind(size=title_label.setter("text_size"))
        header.add_widget(title_label)

        settings_btn = Button(
            text="⚙ SETTINGS",
            size_hint=(None, 1),
            width=110,
            background_color=(0.1, 0.3, 0.5, 1.0),
            color=(1.0, 1.0, 1.0, 1.0),
        )
        settings_btn.bind(on_release=self.show_settings_popup)
        header.add_widget(settings_btn)
        root.add_widget(header)

        # 2. Status Banner
        self.status_label = Label(
            text="SYSTEM READY — TAP 'CONNECT LIVE' OR SAY 'HEY JARVIS'",
            font_size="12sp",
            size_hint_y=None,
            height=25,
            color=(0.6, 0.8, 0.9, 1.0),
        )
        root.add_widget(self.status_label)

        # 3. Holographic Arc Reactor HUD
        self.hud = ArcReactorHUD(size_hint_y=0.45)
        root.add_widget(self.hud)

        # 4. Transcript & Log Scroll Box
        log_scroll = ScrollView(size_hint_y=0.3)
        self.log_text = Label(
            text="[JARVIS Mobile Engine Initialized]\nWaiting for audio stream...",
            font_size="12sp",
            color=(0.7, 0.85, 0.95, 1.0),
            size_hint_y=None,
            halign="left",
            valign="top",
        )
        self.log_text.bind(
            width=lambda *x: setattr(self.log_text, "text_size", (self.log_text.width, None)),
            texture_size=lambda *x: setattr(self.log_text, "height", self.log_text.texture_size[1]),
        )
        log_scroll.add_widget(self.log_text)
        root.add_widget(log_scroll)

        # 5. Primary Control Bar
        controls = BoxLayout(orientation="horizontal", size_hint_y=None, height=50, spacing=8)

        self.stream_btn = Button(
            text="CONNECT LIVE",
            background_color=(0.0, 0.6, 0.9, 1.0),
            color=(1.0, 1.0, 1.0, 1.0),
            font_size="13sp",
            bold=True,
        )
        self.stream_btn.bind(on_release=self.toggle_live_stream)
        controls.add_widget(self.stream_btn)

        self.wake_btn = Button(
            text="WAKE WORD: OFF",
            background_color=(0.2, 0.2, 0.2, 1.0),
            color=(0.8, 0.8, 0.8, 1.0),
            font_size="13sp",
        )
        self.wake_btn.bind(on_release=self.toggle_wake_word)
        controls.add_widget(self.wake_btn)

        dashboard_btn = Button(
            text="WEB DASHBOARD",
            background_color=(0.1, 0.4, 0.4, 1.0),
            color=(0.2, 1.0, 0.8, 1.0),
            font_size="13sp",
        )
        dashboard_btn.bind(on_release=self.open_web_dashboard)
        controls.add_widget(dashboard_btn)

        root.add_widget(controls)

        # 6. Push-to-Talk Button
        self.ptt_btn = Button(
            text="🎤 HOLD TO SPEAK (PUSH-TO-TALK)",
            size_hint_y=None,
            height=52,
            background_color=(0.0, 0.4, 0.7, 1.0),
            color=(1.0, 1.0, 1.0, 1.0),
            font_size="14sp",
            bold=True,
        )
        self.ptt_btn.bind(on_press=self.on_ptt_down, on_release=self.on_ptt_up)
        root.add_widget(self.ptt_btn)

        # Refresh wake word state
        if get_wake_word_enabled():
            self.toggle_wake_word()

        return root

    # ─────────────────────────────────────────────────────────────────────────
    # Audio & Core Engine Setup
    # ─────────────────────────────────────────────────────────────────────────
    def _init_audio_and_plugins(self):
        """Discover tools, plugins and prepare audio streams."""
        try:
            discover_actions()
            discover_plugins()
            self.write_log("Core actions and plugins loaded successfully.")
        except Exception as e:
            self.write_log(f"Warning loading plugins: {e}")

        def mic_callback(indata, frames, time_info, status):
            try:
                # Level calculation for HUD
                x = np.asarray(indata, dtype=np.float32)
                rms = float(np.sqrt(np.mean(x * x))) if x.size > 0 else 0.0
                norm_level = min(1.0, max(0.0, (rms - 60.0) / 2500.0))
                Clock.schedule_once(lambda dt: self.hud.set_audio_level(norm_level), 0)

                # Feed Wake Word if active
                if self.wake_detector and self.wake_detector.is_running:
                    self.wake_detector.feed(indata)

                # Feed Live Stream Queue if active
                if self.is_streaming:
                    if not self.audio_in_queue.full():
                        self.audio_in_queue.put_nowait(indata.tobytes())
            except Exception:
                pass

        self.mic_stream = InputStream(
            samplerate=16000,
            channels=1,
            dtype="int16",
            blocksize=1024,
            callback=mic_callback,
        )
        self.mic_stream.start()

        self.speaker_stream = RawOutputStream(
            samplerate=24000,
            channels=1,
            dtype="int16",
            blocksize=1024,
        )
        self.speaker_stream.start()

    def _start_dashboard_server(self):
        """Start Mark-LIV's local FastAPI dashboard server in a background thread."""
        def run_server():
            try:
                from dashboard.server import PORT
                import uvicorn
                uvicorn.run("dashboard.server:app", host="127.0.0.1", port=PORT, log_level="warning")
            except Exception as e:
                print(f"[DashboardServer] Init error: {e}")

        server_thread = threading.Thread(target=run_server, daemon=True, name="markliv-dash")
        server_thread.start()

    # ─────────────────────────────────────────────────────────────────────────
    # Live Gemini Session
    # ─────────────────────────────────────────────────────────────────────────
    def toggle_live_stream(self, *args):
        if not self.is_streaming:
            key = get_gemini_key()
            if not key or len(key) < 10:
                self.show_settings_popup()
                self.write_log("⚠️ Please enter a valid Gemini API Key in Settings.")
                return

            self.is_streaming = True
            self.stream_btn.text = "DISCONNECT LIVE"
            self.stream_btn.background_color = (0.8, 0.2, 0.2, 1.0)
            self.status_label.text = "STATUS: CONNECTED TO GEMINI LIVE (STREAMING)"
            self.write_log("[Gemini Live] Starting live voice connection...")
            threading.Thread(target=self._run_live_loop, daemon=True).start()
        else:
            self.is_streaming = False
            self.stream_btn.text = "CONNECT LIVE"
            self.stream_btn.background_color = (0.0, 0.6, 0.9, 1.0)
            self.status_label.text = "STATUS: DISCONNECTED"
            self.write_log("[Gemini Live] Session disconnected.")

    def _run_live_loop(self):
        """Connects to Gemini Live Multimodal API."""
        try:
            from google import genai
            from google.genai import types

            api_key = get_gemini_key()
            client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})

            async def _session():
                async with client.aio.live.connect(
                    model="models/gemini-2.0-flash-exp",
                    config=types.LiveConnectConfig(
                        response_modalities=[types.LiveModality.AUDIO],
                    ),
                ) as session:
                    self.write_log("[Gemini Live] Connected! Voice link active.")

                    async def send_audio():
                        while self.is_streaming:
                            try:
                                chunk = await asyncio.get_event_loop().run_in_executor(
                                    None, lambda: self.audio_in_queue.get(timeout=0.2)
                                )
                                await session.send(
                                    input=types.LiveClientRealtimeInput(
                                        media_chunks=[
                                            types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                                        ]
                                    )
                                )
                            except queue.Empty:
                                pass
                            except Exception:
                                break

                    async def receive_audio():
                        async for response in session.receive():
                            server_content = response.server_content
                            if server_content is None:
                                continue
                            model_turn = server_content.model_turn
                            if model_turn:
                                for part in model_turn.parts:
                                    if part.inline_data:
                                        self.speaker_stream.write(part.inline_data.data)
                                    if part.text:
                                        self.write_log(f"JARVIS: {part.text}")

                    await asyncio.gather(send_audio(), receive_audio())

            asyncio.run(_session())
        except Exception as e:
            self.write_log(f"[Gemini Live Error] {e}")
            Clock.schedule_once(lambda dt: self.toggle_live_stream(), 0)

    # ─────────────────────────────────────────────────────────────────────────
    # Wake-Word Management
    # ─────────────────────────────────────────────────────────────────────────
    def toggle_wake_word(self, *args):
        if self.wake_detector and self.wake_detector.is_running:
            self.wake_detector.stop()
            self.wake_btn.text = "WAKE WORD: OFF"
            self.wake_btn.background_color = (0.2, 0.2, 0.2, 1.0)
            self.write_log("Wake word listener deactivated.")
            save_wake_word_enabled(False)
        else:
            def on_wake():
                self.write_log("⚡ 'Hey Jarvis' detected!")
                if not self.is_streaming:
                    Clock.schedule_once(lambda dt: self.toggle_live_stream(), 0)

            self.wake_detector = WakeWordDetector(on_detected=on_wake)
            self.wake_detector.start()
            self.wake_btn.text = "WAKE WORD: ON"
            self.wake_btn.background_color = (0.1, 0.7, 0.4, 1.0)
            self.write_log("Wake word listener activated ('Hey Jarvis').")
            save_wake_word_enabled(True)

    # ─────────────────────────────────────────────────────────────────────────
    # Push-to-Talk Controls
    # ─────────────────────────────────────────────────────────────────────────
    def on_ptt_down(self, *args):
        self.ptt_btn.background_color = (0.9, 0.2, 0.2, 1.0)
        self.ptt_btn.text = "RECORDING (RELEASE TO SEND)"
        if not self.is_streaming:
            self.toggle_live_stream()

    def on_ptt_up(self, *args):
        self.ptt_btn.background_color = (0.0, 0.4, 0.7, 1.0)
        self.ptt_btn.text = "🎤 HOLD TO SPEAK (PUSH-TO-TALK)"

    # ─────────────────────────────────────────────────────────────────────────
    # Web Dashboard Trigger
    # ─────────────────────────────────────────────────────────────────────────
    def open_web_dashboard(self, *args):
        url = "http://127.0.0.1:8000"
        self.write_log(f"Opening Local Dashboard: {url}")
        import webbrowser
        webbrowser.open(url)

    # ─────────────────────────────────────────────────────────────────────────
    # UI Helpers & Settings Popup
    # ─────────────────────────────────────────────────────────────────────────
    def write_log(self, text: str):
        def _append(dt):
            ts = time.strftime("%H:%M:%S")
            self.log_text.text += f"\n[{ts}] {text}"
        Clock.schedule_once(_append, 0)

    def show_settings_popup(self, *args):
        content = BoxLayout(orientation="vertical", padding=10, spacing=10)
        content.add_widget(Label(text="Gemini API Key:", size_hint_y=None, height=30))
        key_input = TextInput(text=get_gemini_key() or "", multiline=False, size_hint_y=None, height=40)
        content.add_widget(key_input)

        save_btn = Button(text="SAVE CONFIG", size_hint_y=None, height=45, background_color=(0.1, 0.6, 0.3, 1.0))
        content.add_widget(save_btn)

        popup = Popup(title="MARK-LIV SETTINGS", content=content, size_hint=(0.85, 0.5))

        def _save(*_):
            save_api_keys(key_input.text.strip())
            self.write_log("API Key saved successfully.")
            popup.dismiss()

        save_btn.bind(on_release=_save)
        popup.open()


if __name__ == "__main__":
    MarkLIVAndroidApp().run()
