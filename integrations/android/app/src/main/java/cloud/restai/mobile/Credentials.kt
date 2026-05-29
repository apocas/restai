package cloud.restai.mobile

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/** Stores the paired project credentials encrypted on-device. */
object Credentials {
    private const val FILE = "restai-credentials"
    private const val K_HOST = "host"
    private const val K_KEY = "api_key"
    private const val K_PID = "project_id"
    private const val K_PNAME = "project_name"

    private fun prefs(ctx: Context) = EncryptedSharedPreferences.create(
        ctx,
        FILE,
        MasterKey.Builder(ctx).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )

    fun load(ctx: Context): QrPayload? {
        val p = prefs(ctx)
        val host = p.getString(K_HOST, null) ?: return null
        val key = p.getString(K_KEY, null) ?: return null
        val pid = p.getInt(K_PID, -1).takeIf { it > 0 } ?: return null
        val pname = p.getString(K_PNAME, "project $pid") ?: "project $pid"
        return QrPayload(host, pid, pname, key)
    }

    fun save(ctx: Context, q: QrPayload) {
        prefs(ctx).edit()
            .putString(K_HOST, q.host)
            .putString(K_KEY, q.apiKey)
            .putInt(K_PID, q.projectId)
            .putString(K_PNAME, q.projectName)
            .apply()
    }

    fun clear(ctx: Context) {
        prefs(ctx).edit().clear().apply()
    }
}
