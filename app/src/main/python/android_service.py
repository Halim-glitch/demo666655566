"""
android_service.py — Android Background Foreground Service for Mark-LIV

Runs a continuous background service on Android to keep the "Hey Jarvis"
wake-word listener active even when the screen is locked or the app is minimized.
"""
import time
import os
import sys

# Ensure project root is on sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.android_audio import InputStream
from core.wake_word import WakeWordDetector, is_ready as wake_is_ready


def setup_foreground_notification():
    """Setup Android Foreground Notification to satisfy Android 8+ background limits."""
    try:
        from jnius import autoclass
        PythonService = autoclass("org.kivy.android.PythonService")
        service = PythonService.mService
        Context = autoclass("android.content.Context")
        NotificationBuilder = autoclass("android.app.Notification$Builder")
        NotificationManager = autoclass("android.app.NotificationManager")
        NotificationChannel = autoclass("android.app.NotificationChannel")

        CHANNEL_ID = "markliv_service_channel"
        chan = NotificationChannel(
            CHANNEL_ID,
            "Mark-LIV Background Listener",
            NotificationManager.IMPORTANCE_LOW,
        )
        chan.setDescription("Keeps Jarvis wake-word detector active")
        manager = service.getSystemService(Context.NOTIFICATION_SERVICE)
        manager.createNotificationChannel(chan)

        builder = NotificationBuilder(service, CHANNEL_ID)
        builder.setContentTitle("Mark-LIV Voice Assistant")
        builder.setContentText("Listening for 'Hey Jarvis'...")
        builder.setSmallIcon(service.getApplicationInfo().icon)
        notification = builder.build()

        # Start as foreground service (ID 1001)
        service.startForeground(1001, notification)
        print("[Service] Foreground notification established")
    except Exception as e:
        print(f"[Service] Notification setup: {e}")


def on_wake_detected():
    print("[Service] ⚡ Wake word 'Hey Jarvis' detected in background!")
    try:
        from jnius import autoclass
        PythonService = autoclass("org.kivy.android.PythonService")
        service = PythonService.mService
        Intent = autoclass("android.content.Intent")
        
        # Bring main app activity to foreground
        pm = service.getPackageManager()
        launch_intent = pm.getLaunchIntentForPackage(service.getPackageName())
        if launch_intent:
            launch_intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP)
            launch_intent.putExtra("WAKE_TRIGGERED", True)
            service.startActivity(launch_intent)
    except Exception as e:
        print(f"[Service] Failed to bring activity to front: {e}")


def run_service():
    print("[Service] Mark-LIV Background Service initializing...")
    setup_foreground_notification()

    detector = WakeWordDetector(on_detected=on_wake_detected)

    def audio_callback(indata, frames, time_info, status):
        if detector.is_running:
            detector.feed(indata)

    detector.start()
    stream = InputStream(
        samplerate=16000,
        channels=1,
        dtype="int16",
        blocksize=1024,
        callback=audio_callback,
    )
    stream.start()
    print("[Service] Mark-LIV background microphone loop active")

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop()
        detector.stop()
        print("[Service] Service stopped")


if __name__ == "__main__":
    run_service()
