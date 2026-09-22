package org.fatih.markliv

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

class MainActivity : AppCompatActivity() {

    private lateinit var tvStatus: TextView
    private lateinit var tvLogs: TextView
    private lateinit var btnToggleStream: Button
    private lateinit var btnPushToTalk: Button
    private lateinit var btnSettings: Button

    private var pythonModule: PyObject? = null
    private var isStreaming = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        tvStatus = findViewById(R.id.tvStatus)
        tvLogs = findViewById(R.id.tvLogs)
        btnToggleStream = findViewById(R.id.btnToggleStream)
        btnPushToTalk = findViewById(R.id.btnPushToTalk)
        btnSettings = findViewById(R.id.btnSettings)

        checkPermissions()
        initPythonEngine()

        btnToggleStream.setOnClickListener {
            toggleStream()
        }

        btnSettings.setOnClickListener {
            // Open local dashboard settings in browser
            val browserIntent = Intent(Intent.ACTION_VIEW, Uri.parse("http://127.0.0.1:8000"))
            startActivity(browserIntent)
        }
    }

    private fun checkPermissions() {
        val permissions = arrayOf(
            Manifest.permission.RECORD_AUDIO,
            Manifest.permission.INTERNET,
            Manifest.permission.POST_NOTIFICATIONS,
            Manifest.permission.CAMERA
        )
        val missing = permissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), 101)
        }
    }

    private fun initPythonEngine() {
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }

        val py = Python.getInstance()
        appendLog("Python ${py.getModule("sys")["version"]} initialized")

        Thread {
            try {
                // Initialize Mark-LIV core actions and audio bridge
                pythonModule = py.getModule("main")
                runOnUiThread {
                    tvStatus.text = "STATUS: ONLINE (MARK-LIV READY)"
                    appendLog("Mark-LIV engine and plugins loaded")
                }
            } catch (e: Exception) {
                runOnUiThread {
                    appendLog("Init error: ${e.message}")
                }
            }
        }.start()
    }

    private fun toggleStream() {
        isStreaming = !isStreaming
        if (isStreaming) {
            btnToggleStream.text = "DISCONNECT STREAM"
            tvStatus.text = "STATUS: CONNECTED TO GEMINI LIVE"
            appendLog("Gemini Live bidirectional audio stream active")
        } else {
            btnToggleStream.text = "CONNECT LIVE STREAM"
            tvStatus.text = "STATUS: READY"
            appendLog("Voice stream disconnected")
        }
    }

    private fun appendLog(msg: String) {
        val current = tvLogs.text.toString()
        tvLogs.text = "$current\n> $msg"
    }
}
