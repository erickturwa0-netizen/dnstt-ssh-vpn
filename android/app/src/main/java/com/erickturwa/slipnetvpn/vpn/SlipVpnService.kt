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
import com.erickturwa.slipnetvpn.R
import java.io.FileInputStream
import java.io.FileOutputStream
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

/**
 * System TUN interface (Android VpnService).
 * Establishes a VPN network on the device so traffic can be captured.
 * Full DNSTT/SlipNet protocol engines require native binaries (same as official SlipNet APK);
 * this service provides the Android VPN shell + config plumbing matching the Linux GUI.
 */
class SlipVpnService : VpnService() {

    private var tun: ParcelFileDescriptor? = null
    private val running = AtomicBoolean(false)

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_CONNECT -> {
                val mode = intent.getStringExtra(EXTRA_MODE) ?: "dnstt"
                startForeground(NOTIF_ID, buildNotification("Connecting ($mode)…"))
                startTun(mode)
            }
            ACTION_DISCONNECT, null -> stopSelfSafe()
        }
        return START_STICKY
    }

    private fun startTun(mode: String) {
        if (running.getAndSet(true)) return

        val builder = Builder()
            .setSession("SlipNet VPN")
            .addAddress("10.0.0.2", 32)
            .addRoute("0.0.0.0", 0)
            .addDnsServer("8.8.8.8")
            .setMtu(1500)

        // Avoid routing our own process into a black hole before engine is ready
        try {
            builder.addDisallowedApplication(packageName)
        } catch (_: Exception) {
        }

        tun = builder.establish()
        if (tun == null) {
            running.set(false)
            stopSelf()
            return
        }

        updateNotification("VPN ON ($mode)")

        // Drain/loop TUN so interface stays alive (packets idle until native engine plugged in)
        val fd = tun!!
        thread(name = "tun-loop", isDaemon = true) {
            val input = FileInputStream(fd.fileDescriptor)
            val output = FileOutputStream(fd.fileDescriptor)
            val buf = ByteBuffer.allocate(32767)
            try {
                while (running.get()) {
                    buf.clear()
                    val n = input.channel.read(buf)
                    if (n > 0) {
                        // Packet received from device — would forward to tunnel engine
                        buf.flip()
                        // Echo drop: without backend, discard (prevents buffer fill)
                    } else if (n < 0) {
                        break
                    } else {
                        Thread.sleep(10)
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
        running.set(false)
        try {
            tun?.close()
        } catch (_: Exception) {
        }
        tun = null
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        stopSelfSafe()
        super.onDestroy()
    }

    private fun buildNotification(text: String): Notification {
        val channelId = "slipnet_vpn"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(
                NotificationChannel(channelId, "SlipNet VPN", NotificationManager.IMPORTANCE_LOW)
            )
        }
        val pi = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, channelId)
            .setContentTitle("SlipNet VPN")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_lock_lock)
            .setContentIntent(pi)
            .setOngoing(true)
            .build()
    }

    private fun updateNotification(text: String) {
        val nm = getSystemService(NotificationManager::class.java)
        nm.notify(NOTIF_ID, buildNotification(text))
    }

    companion object {
        const val ACTION_CONNECT = "com.erickturwa.slipnetvpn.CONNECT"
        const val ACTION_DISCONNECT = "com.erickturwa.slipnetvpn.DISCONNECT"
        const val EXTRA_MODE = "mode"
        const val EXTRA_SLIPNET_URI = "slipnet_uri"
        const val EXTRA_DOMAIN = "domain"
        const val EXTRA_PUBKEY = "pubkey"
        const val EXTRA_RESOLVER = "resolver"
        const val EXTRA_USER = "user"
        const val EXTRA_PASS = "pass"
        const val EXTRA_SSH_PORT = "ssh_port"
        private const val NOTIF_ID = 42
    }
}
