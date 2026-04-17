package cloud.restai.mobile

import org.json.JSONObject

/**
 * QR payload. Matches the JSON produced by /projects/{id}/android/enable:
 *
 *   { "host", "project_id", "project_name", "api_key" }
 */
data class QrPayload(
    val host: String,
    val projectId: Int,
    val projectName: String,
    val apiKey: String,
) {
    companion object {
        fun parse(raw: String): QrPayload? = try {
            val j = JSONObject(raw.trim())
            QrPayload(
                host = j.getString("host").trimEnd('/'),
                projectId = j.getInt("project_id"),
                projectName = j.optString("project_name", "project ${j.getInt("project_id")}"),
                apiKey = j.getString("api_key"),
            )
        } catch (_: Exception) { null }
    }
}

/** One chat turn shown in the UI. */
data class Message(
    val role: Role,
    var text: String,
) {
    enum class Role { USER, ASSISTANT }
}
