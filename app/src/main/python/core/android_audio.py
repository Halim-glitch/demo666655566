"""
core/android_audio.py — Android Audio I/O Driver for Mark-LIV

Provides drop-in sounddevice-compatible InputStream and RawOutputStream
implementations for Android using PyJNIus to bridge to native:
  • android.media.AudioRecord (16kHz, 16-bit PCM Mono Mic input)
  • android.media.AudioTrack (24kHz, 16-bit PCM Mono Speaker output)

This eliminates the dependency on PortAudio / sounddevice C-libraries
which fail to compile or link on standard Android Python distributions.
"""
from __future__ import annotations

import sys
import os
import time
import threading
import queue
from typing import Callable, Optional

import numpy as np

IS_ANDROID = sys.platform == "android" or "ANDROID_ARGUMENT" in os.environ

# PyJNIus native classes (lazy loaded on Android)
_AudioRecord = None
_AudioTrack = None
_AudioFormat = None
_MediaRecorder = None
_AudioManager = None


def _init_jnius():
    global _AudioRecord, _AudioTrack, _AudioFormat, _MediaRecorder, _AudioManager
    if not IS_ANDROID:
        return False
    try:
        from jnius import autoclass
        _AudioRecord = autoclass("android.media.AudioRecord")
        _AudioTrack = autoclass("android.media.AudioTrack")
        _AudioFormat = autoclass("android.media.AudioFormat")
        _MediaRecorder = autoclass("android.media.MediaRecorder")
        _AudioManager = autoclass("android.media.AudioManager")
        return True
    except Exception as e:
        print(f"[AndroidAudio] PyJNIus init error: {e}")
        return False


class InputStream:
    """
    sounddevice.InputStream drop-in replacement using android.media.AudioRecord.
    Feeds real-time 16-bit PCM audio blocks into the provided callback.
    """
    def __init__(
        self,
        samplerate: int = 16000,
        channels: int = 1,
        dtype: str = "int16",
        blocksize: int = 1024,
        device=None,
        callback: Optional[Callable] = None,
    ):
        self.samplerate = int(samplerate)
        self.channels = int(channels)
        self.blocksize = int(blocksize)
        self.callback = callback
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._record = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        self.close()

    def start(self):
        if self._running:
            return
        self._running = True

        if IS_ANDROID and _init_jnius():
            self._start_android_record()
        else:
            # Fallback simulator for non-Android dev environments without PortAudio
            self._thread = threading.Thread(target=self._dummy_mic_loop, daemon=True)
            self._thread.start()

    def _start_android_record(self):
        try:
            # AudioFormat.CHANNEL_IN_MONO = 16
            channel_cfg = 16 if self.channels == 1 else 12
            # AudioFormat.ENCODING_PCM_16BIT = 2
            encoding = 2
            # MediaRecorder.AudioSource.MIC = 1
            audio_source = 1

            min_buf = _AudioRecord.getMinBufferSize(self.samplerate, channel_cfg, encoding)
            buf_size = max(min_buf, self.blocksize * 2 * 4)

            self._record = _AudioRecord(
                audio_source,
                self.samplerate,
                channel_cfg,
                encoding,
                buf_size,
            )
            self._record.startRecording()
            self._thread = threading.Thread(target=self._record_loop, daemon=True)
            self._thread.start()
            print("[AndroidAudio] 🎤 AudioRecord stream started successfully")
        except Exception as e:
            print(f"[AndroidAudio] ❌ AudioRecord failed: {e}")
            self._thread = threading.Thread(target=self._dummy_mic_loop, daemon=True)
            self._thread.start()

    def _record_loop(self):
        from jnius import autoclass
        # Allocate Java short array of size blocksize
        j_shorts = [0] * self.blocksize
        while self._running:
            try:
                read_count = self._record.read(j_shorts, 0, self.blocksize)
                if read_count > 0 and self.callback:
                    data_np = np.array(j_shorts[:read_count], dtype=np.int16).reshape(-1, self.channels)
                    self.callback(data_np, read_count, None, None)
            except Exception as e:
                time.sleep(0.05)

    def _dummy_mic_loop(self):
        """Generates room silence when native recording is unavailable."""
        silence = np.zeros((self.blocksize, self.channels), dtype=np.int16)
        interval = self.blocksize / float(self.samplerate)
        while self._running:
            start_t = time.time()
            if self.callback:
                self.callback(silence, self.blocksize, None, None)
            elapsed = time.time() - start_t
            if interval > elapsed:
                time.sleep(interval - elapsed)

    def stop(self):
        self._running = False
        if self._record:
            try:
                self._record.stop()
            except Exception:
                pass

    def close(self):
        self.stop()
        if self._record:
            try:
                self._record.release()
            except Exception:
                pass
            self._record = None


class RawOutputStream:
    """
    sounddevice.RawOutputStream drop-in replacement using android.media.AudioTrack.
    Outputs low-latency PCM audio chunks directly to device speakers.
    """
    def __init__(
        self,
        samplerate: int = 24000,
        channels: int = 1,
        dtype: str = "int16",
        blocksize: int = 1024,
        device=None,
    ):
        self.samplerate = int(samplerate)
        self.channels = int(channels)
        self.blocksize = int(blocksize)
        self.latency = 0.050  # ~50 ms estimated Android latency
        self._track = None
        self._running = False

    def start(self):
        self._running = True
        if IS_ANDROID and _init_jnius():
            try:
                # AudioFormat.CHANNEL_OUT_MONO = 4
                channel_cfg = 4 if self.channels == 1 else 12
                # AudioFormat.ENCODING_PCM_16BIT = 2
                encoding = 2
                # AudioManager.STREAM_MUSIC = 3
                stream_type = 3
                # AudioTrack.MODE_STREAM = 1
                mode = 1

                min_buf = _AudioTrack.getMinBufferSize(self.samplerate, channel_cfg, encoding)
                buf_size = max(min_buf, self.blocksize * 4)

                self._track = _AudioTrack(
                    stream_type,
                    self.samplerate,
                    channel_cfg,
                    encoding,
                    buf_size,
                    mode,
                )
                self._track.play()
                print("[AndroidAudio] 🔊 AudioTrack stream started")
            except Exception as e:
                print(f"[AndroidAudio] ❌ AudioTrack init error: {e}")

    def write(self, data: bytes):
        """Write raw PCM byte buffer to AudioTrack."""
        if not self._running:
            return
        if self._track:
            try:
                # AudioTrack.write(byte[], int offset, int size)
                self._track.write(data, 0, len(data))
            except Exception as e:
                pass

    def stop(self):
        self._running = False
        if self._track:
            try:
                self._track.stop()
            except Exception:
                pass

    def close(self):
        self.stop()
        if self._track:
            try:
                self._track.release()
            except Exception:
                pass
            self._track = None


# Module-level helpers mimicking sounddevice module
def play(data: np.ndarray, samplerate: int = 24000):
    """Play audio numpy array via AudioTrack or system."""
    pcm_bytes = (data.astype(np.int16)).tobytes()
    out = RawOutputStream(samplerate=samplerate, channels=1)
    out.start()
    out.write(pcm_bytes)
    out.close()


def stop():
    pass


def wait():
    pass
