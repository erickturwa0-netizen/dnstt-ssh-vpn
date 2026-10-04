package com.erickturwa.slipnetvpn

import android.app.Activity
import android.content.Intent
import android.net.VpnService
import android.os.Bundle
import android.util.Base64
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.erickturwa.slipnetvpn.databinding.ActivityMainBinding
import com.erickturwa.slipnetvpn.vpn.SlipVpnService
import org.json.JSONObject
import java.nio.charset.StandardCharsets

class MainActivity : AppCompatActivity() {

    private lateinit var b: ActivityMainBinding
    private var slipnetUri: String? = null
    private var slipMeta: JSONObject? = null
    private var connected = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityMainBinding.inflate(layoutInflater)
        setContentView(b.root)

        b.modeGroup.setOnCheckedChangeListener { _, checkedId ->
            val slip = checkedId == b.modeSlipnet.id
            b.panelSlipnet.visibility = if (slip) View.VISIBLE else View.GONE
            b.panelDnstt.visibility = if (slip) View.GONE else View.VISIBLE
        }

        b.btnImport.setOnClickListener { importSlipnet() }
        b.btnConnect.setOnClickListener { toggleConnect() }
        b.btnSave.setOnClickListener { saveProfile() }

        intent?.data?.let { uri ->
            if (uri.scheme == "slipnet") {
                b.modeSlipnet.isChecked = true
                b.inputSlipnet.setText(uri.toString())
                importSlipnet()
            }
        }

        log("Ready.")
    }

    private fun log(msg: String) {
        b.logView.append(msg + "\n")
    }

    private fun importSlipnet() {
        val raw = b.inputSlipnet.text.toString().trim()
        try {
            val meta = parseSlipnet(raw)
            slipnetUri = meta.getString("uri")
            slipMeta = meta
            b.slipInfo.text =
                "Name: ${meta.optString("name")}\nType: ${meta.optString("tunnel_type")}\nDomain: ${meta.optString("domain")}"
            b.profileName.setText(meta.optString("name"))
            log("Imported: ${meta.optString("tunnel_type")} / ${meta.optString("domain")}")
            Toast.makeText(this, "Config imported", Toast.LENGTH_SHORT).show()
        } catch (e: Exception) {
            Toast.makeText(this, e.message ?: "Import failed", Toast.LENGTH_LONG).show()
            log("Import error: ${e.message}")
        }
    }

    private fun parseSlipnet(text: String): JSONObject {
        if (text.isBlank()) throw IllegalArgumentException("Config tupu")
        if (text.startsWith("slipnet-enc://")) {
            throw IllegalArgumentException("Encrypted config haitumiki. Tumia slipnet://")
        }
        val b64 = when {
            text.startsWith("slipnet://") -> text.removePrefix("slipnet://").trim()
            else -> text
        }
        val pad = "=".repeat((4 - b64.length % 4) % 4)
        val decoded = String(Base64.decode(b64 + pad, Base64.DEFAULT), StandardCharsets.UTF_8)
        val f = decoded.split("|")
        if (f.size < 5) throw IllegalArgumentException("Profile fupi mno")
        val uri = if (text.startsWith("slipnet://")) text else "slipnet://$b64"
        return JSONObject()
            .put("uri", uri)
            .put("version", f[0])
            .put("tunnel_type", f.getOrNull(1) ?: "")
            .put("name", f.getOrNull(2) ?: "")
            .put("domain", f.getOrNull(3) ?: "")
            .put("resolvers", f.getOrNull(4) ?: "")
            .put("pubkey", f.getOrNull(11) ?: "")
    }

    private fun toggleConnect() {
        if (connected) {
            val i = Intent(this, SlipVpnService::class.java).apply {
                action = SlipVpnService.ACTION_DISCONNECT
            }
            startService(i)
            connected = false
            b.btnConnect.setText(R.string.connect)
            b.statusText.text = "Disconnected"
            b.statusText.setTextColor(getColor(R.color.red_light))
            log("Disconnected — notification sent")
            return
        }

        val slipMode = b.modeSlipnet.isChecked
        if (slipMode) {
            if (slipnetUri.isNullOrBlank()) {
                Toast.makeText(this, "Import slipnet:// kwanza", Toast.LENGTH_SHORT).show()
                return
            }
        } else {
            if (b.fDomain.text.isNullOrBlank() || b.fPubkey.text.isNullOrBlank()) {
                Toast.makeText(this, "NS na PUBLIC KEY zinahitajika", Toast.LENGTH_SHORT).show()
                return
            }
            if (b.fUser.text.isNullOrBlank()) {
                Toast.makeText(this, "USERNAME inahitajika", Toast.LENGTH_SHORT).show()
                return
            }
        }

        val intentPrep = VpnService.prepare(this)
        if (intentPrep != null) {
            startActivityForResult(intentPrep, REQ_VPN)
        } else {
            startVpn()
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQ_VPN && resultCode == Activity.RESULT_OK) {
            startVpn()
        } else if (requestCode == REQ_VPN) {
            log("VPN permission denied")
        }
    }

    private fun startVpn() {
        val slipMode = b.modeSlipnet.isChecked
        val label = when {
            slipMode -> slipMeta?.optString("name")?.ifBlank { null }
                ?: slipMeta?.optString("domain")
                ?: "SlipNet"
            else -> b.fDomain.text?.toString()?.ifBlank { null } ?: "DNSTT"
        }

        val i = Intent(this, SlipVpnService::class.java).apply {
            action = SlipVpnService.ACTION_CONNECT
            putExtra(SlipVpnService.EXTRA_MODE, if (slipMode) "slipnet" else "dnstt")
            putExtra(SlipVpnService.EXTRA_LABEL, label)
            putExtra(SlipVpnService.EXTRA_SLIPNET_URI, slipnetUri)
            putExtra(SlipVpnService.EXTRA_DOMAIN, b.fDomain.text?.toString())
            putExtra(SlipVpnService.EXTRA_PUBKEY, b.fPubkey.text?.toString())
            putExtra(SlipVpnService.EXTRA_RESOLVER, b.fResolver.text?.toString())
            putExtra(SlipVpnService.EXTRA_USER, b.fUser.text?.toString())
            putExtra(SlipVpnService.EXTRA_PASS, b.fPass.text?.toString())
            putExtra(SlipVpnService.EXTRA_SSH_PORT, b.fSshPort.text?.toString())
        }
        startForegroundService(i)
        connected = true
        b.btnConnect.setText(R.string.disconnect)
        b.statusText.text = "Connected"
        b.statusText.setTextColor(getColor(R.color.green_ok))
        log("Connected — notification: VPN ON")
    }

    private fun saveProfile() {
        val name = b.profileName.text?.toString()?.trim().orEmpty()
        if (name.isEmpty()) {
            Toast.makeText(this, "Andika PROFILE NAME", Toast.LENGTH_SHORT).show()
            return
        }
        val prefs = getSharedPreferences("profiles", MODE_PRIVATE)
        val obj = JSONObject()
            .put("mode", if (b.modeSlipnet.isChecked) "slipnet" else "dnstt")
            .put("uri", slipnetUri)
            .put("domain", b.fDomain.text?.toString())
            .put("pubkey", b.fPubkey.text?.toString())
            .put("user", b.fUser.text?.toString())
        prefs.edit().putString(name, obj.toString()).apply()
        Toast.makeText(this, "Saved: $name", Toast.LENGTH_SHORT).show()
        log("Profile saved: $name")
    }

    companion object {
        private const val REQ_VPN = 1001
    }
}
