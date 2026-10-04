package com.erickturwa.slipnetvpn.vpn

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.net.VpnService
import android.os.Build
import android.os.ParcelFileDescriptor
import androidx.core.app.NotificationCompat
import com.erickturwa.slipnetvpn.MainActivity
import java.io.FileInputStream
import java.io.FileOutputStream
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

class SlipVpnService : VpnService() {

    private var tun: ParcelFileDescriptor? = null
    private val running = AtomicBoolean(false)

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_CONNECT -> {
                val mode = intent.getStringExtra(EXTRA_MODE) ?: "dnstt"
                val label = intent.getStringExtra(EXTRA_LABEL) ?: mode
                ensureChannels()
                startForeground(NOTIF_ID, buildOngoingNotification("Connecting…", label))
                startTun(mode, label)
            }
            ACTION_DISCONNECT -> {
                showStatusNotification("Disconnected", "VPN imezimwa")
                stopSelfSafe()
            }
            else -> stopSelfSafe()
        }
        return START_STICKY
    }

    private fun startTun(mode: String, label: String) {
        if (running.getAndSet(true)) return

        val builder = Builder()
            .setSession("SlipNet VPN")
            .addAddress("10.0.0.2", 32)
            .addRoute("0.0.0.0", 0)
            .addDnsServer("8.8.8.8")
            .setMtu(1500)

        try {
            builder.addDisallowedApplication(packageName)
        } catch (_: Exception) {
        }

        tun = builder.establish()
        if (tun == null) {
            running.set(false)
            showStatusNotification("Disconnected", "VPN haikuanzishwa")
            stopSelf()
            return
        }

        // Persistent notification while connected
        updateOngoing("Connected", label)
        showStatusNotification("Connected", "VPN ON — $label")

        val fd = tun!!
        thread(name = "tun-loop", isDaemon = true) {
            val input = FileInputStream(fd.fileDescriptor)
            val output = FileOutputStream(fd.fileDescriptor)
            val buf = ByteBuffer.allocate(32767)
            try {
                while (running.get()) {
                    buf.clear()
                    val n = input.channel.read(buf)
                    when {
                        n > 0 -> buf.flip()
                        n < 0 -> break
                        else -> Thread.sleep(10)
                    }
                }
            } catch (_: Exception) {
            } finally {
                try {
                    input.close()
                    output.close()
                } catch (_: Exception) {
                }
            }
        }
    }

    private fun stopSelfSafe() {
        val was = running.getAndSet(false)
        try {
            tun?.close()
        } catch (_: Exception) {
        }
        tun = null
        if (was) {
            showStatusNotification("Disconnected", "VPN imezimwa")
        }
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        if (running.get()) {
            showStatusNotification("Disconnected", "VPN imezimwa")
        }
        stopSelfSafe()
        super.onDestroy()
    }

    private fun ensureChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(
                CHANNEL_ONGOING,
                "VPN status",
                NotificationManager.IMPORTANCE_LOW
            ).apply { description = "Connected VPN ongoing" }
        )
        nm.createNotificationChannel(
            NotificationChannel(
                CHANNEL_ALERT,
                "VPN alerts",
                NotificationManager.IMPORTANCE_DEFAULT
            ).apply { description = "Connected / Disconnected alerts" }
        )
    }

    private fun openAppIntent(): PendingIntent {
        return PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }

    private fun buildOngoingNotification(title: String, body: String): Notification {
        ensureChannels()
        return NotificationCompat.Builder(this, CHANNEL_ONGOING)
            .setContentTitle("SlipNet VPN — $title")
            .setContentText(body)
            .setSmallIcon(android.R.drawable.ic_lock_lock)
            .setContentIntent(openAppIntent())
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .build()
    }

    private fun updateOngoing(title: String, body: String) {
        val nm = getSystemService(NotificationManager::class.java)
        nm.notify(NOTIF_ID, buildOngoingNotification(title, body))
    }

    /** One-shot alert: Connected / Disconnected */
    private fun showStatusNotification(title: String, body: String) {
        ensureChannels()
        val nm = getSystemService(NotificationManager::class.java)
        val n = NotificationCompat.Builder(this, CHANNEL_ALERT)
            .setContentTitle("SlipNet VPN — $title")
            .setContentText(body)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentIntent(openAppIntent())
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setCategory(NotificationCompat.CATEGORY_STATUS)
            .build()
        nm.notify(NOTIF_ALERT_ID, n)
    }

    companion object {
        const val ACTION_CONNECT = "com.erickturwa.slipnetvpn.CONNECT"
        const val ACTION_DISCONNECT = "com.erickturwa.slipnetvpn.DISCONNECT"
        const val EXTRA_MODE = "mode"
        const val EXTRA_LABEL = "label"
        const val EXTRA_SLIPNET_URI = "slipnet_uri"
        const val EXTRA_DOMAIN = "domain"
        const val EXTRA_PUBKEY = "pubkey"
        const val EXTRA_RESOLVER = "resolver"
        const val EXTRA_USER = "user"
        const val EXTRA_PASS = "pass"
        const val EXTRA_SSH_PORT = "ssh_port"
        private const val CHANNEL_ONGOING = "slipnet_vpn_ongoing"
        private const val CHANNEL_ALERT = "slipnet_vpn_alert"
        private const val NOTIF_ID = 42
        private const val NOTIF_ALERT_ID = 43
    }
}
