"""
actions/android_actions.py — Native Android Controls for Mark-LIV

Provides device automation tools on Android via PyJNIus:
  • Flashlight / Torch toggle
  • Device Haptic / Vibration
  • Battery Status & Charging readouts
  • Launch Installed Apps via Android Intent
"""
from __future__ import annotations

import sys
import os

IS_ANDROID = sys.platform == "android" or "ANDROID_ARGUMENT" in os.environ


def _get_android_context():
    """Retrieve the Android Activity / Context via PyJNIus or PythonActivity."""
    if not IS_ANDROID:
        return None
    try:
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        return PythonActivity.mActivity
    except Exception:
        try:
            from jnius import autoclass
            PythonService = autoclass("org.kivy.android.PythonService")
            return PythonService.mService
        except Exception:
            return None


def android_device_action(parameters: dict, player=None, speak=None) -> str:
    """Execute mobile-native device controls."""
    action = parameters.get("action", "").lower().strip()
    arg = parameters.get("argument", "")

    if not IS_ANDROID:
        msg = f"[Android Action Simulated] Action: '{action}' with argument: '{arg}'"
        _log(msg, player)
        return msg

    activity = _get_android_context()
    if not activity:
        return "Sir, I am unable to access the Android system service context."

    try:
        from jnius import autoclass, cast

        if action in ("flashlight", "torch"):
            # Turn torch on/off
            CameraManager = autoclass("android.hardware.camera2.CameraManager")
            Context = autoclass("android.content.Context")
            cam_manager = cast(CameraManager, activity.getSystemService(Context.CAMERA_SERVICE))
            cam_ids = cam_manager.getCameraIdList()
            if cam_ids:
                cam_id = cam_ids[0]
                turn_on = arg.lower() in ("on", "true", "enable", "1")
                cam_manager.setTorchMode(cam_id, turn_on)
                state = "enabled" if turn_on else "disabled"
                msg = f"Flashlight has been {state}, sir."
                _log(msg, player)
                return msg

        elif action in ("vibrate", "haptic"):
            Context = autoclass("android.content.Context")
            Vibrator = autoclass("android.os.Vibrator")
            vibrator = cast(Vibrator, activity.getSystemService(Context.VIBRATOR_SERVICE))
            duration = int(arg) if str(arg).isdigit() else 300
            vibrator.vibrate(duration)
            msg = f"Haptic pulse triggered ({duration}ms), sir."
            _log(msg, player)
            return msg

        elif action in ("battery", "battery_status"):
            IntentFilter = autoclass("android.content.IntentFilter")
            Intent = autoclass("android.content.Intent")
            BatteryManager = autoclass("android.os.BatteryManager")
            ifilter = IntentFilter(Intent.ACTION_BATTERY_CHANGED)
            battery_intent = activity.registerReceiver(None, ifilter)
            level = battery_intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
            scale = battery_intent.getIntExtra(BatteryManager.EXTRA_SCALE, -1)
            status = battery_intent.getIntExtra(BatteryManager.EXTRA_STATUS, -1)
            is_charging = status in (BatteryManager.BATTERY_STATUS_CHARGING, BatteryManager.BATTERY_STATUS_FULL)
            pct = int((level / float(scale)) * 100) if scale > 0 else level
            charging_str = "charging" if is_charging else "on battery power"
            msg = f"Device power is at {pct} percent and currently {charging_str}, sir."
            _log(msg, player)
            return msg

        elif action in ("launch_app", "open_app"):
            pkg_name = str(arg).strip()
            pm = activity.getPackageManager()
            launch_intent = pm.getLaunchIntentForPackage(pkg_name)
            if launch_intent:
                activity.startActivity(launch_intent)
                msg = f"Launching {pkg_name}, sir."
                _log(msg, player)
                return msg
            else:
                return f"Sir, I could not find an installed app matching package '{pkg_name}'."

    except Exception as e:
        err = f"Failed to execute Android device action '{action}': {e}"
        _log(err, player)
        return err

    return f"Sir, the Android device action '{action}' is not recognized."


def _log(message: str, player=None):
    print(f"[AndroidAction] {message}")
    if player and hasattr(player, "write_log"):
        try:
            player.write_log(f"JARVIS: {message}")
        except Exception:
            pass


TOOL = {
    "name": "android_device_control",
    "description": "Control Android device hardware: flashlight/torch (on/off), vibration, battery status, or launch Android apps.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action to perform: 'torch', 'vibrate', 'battery', or 'launch_app'",
            },
            "argument": {
                "type": "STRING",
                "description": "Argument for the action, e.g. 'on'/'off' for torch, '500' for vibration ms, or package name for launch_app",
            },
        },
        "required": ["action"],
    },
    "handler": android_device_action,
}
