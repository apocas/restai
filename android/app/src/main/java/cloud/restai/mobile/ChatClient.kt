package cloud.restai.mobile

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Minimal streaming client for RESTai's /projects/{id}/chat endpoint.
 *
 * Uses SSE-style response parsing (event: close, data: {...}) but over a
 * plain OkHttp request — no extra dependency required.
 */
class ChatClient(private val cred: QrPayload) {

    private val http = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS) // no read timeout on streaming body
        .connectTimeout(20, TimeUnit.SECONDS)
        .build()

    /**
     * Sends [text] and calls [onDelta] for each streamed text chunk. Returns
     * the conversation id so the next call can be threaded to the same
     * session. Throws on HTTP error (e.g. 401 after a key rotation).
     */
    fun sendMessage(
        text: String,
        conversationId: String?,
        onDelta: (String) -> Unit,
    ): String? {
        val body = JSONObject().apply {
            put("question", text)
            put("stream", true)
            if (conversationId != null) put("id", conversationId)
        }.toString().toRequestBody("application/json".toMediaType())

        val req = Request.Builder()
            .url("${cred.host}/projects/${cred.projectId}/chat")
            .post(body)
            .header("Authorization", "Bearer ${cred.apiKey}")
            .header("Accept", "text/event-stream")
            .build()

        http.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) {
                throw ApiException(resp.code, resp.body?.string().orEmpty())
            }
            val source = resp.body?.source() ?: error("empty body")
            var finalConvId: String? = conversationId

            while (!source.exhausted()) {
                val line = source.readUtf8Line() ?: break
                if (line.startsWith("event: close")) break
                if (!line.startsWith("data:")) continue
                val payload = line.removePrefix("data:").trim()
                if (payload.isEmpty()) continue
                try {
                    val json = JSONObject(payload)
                    // Two shapes come down the wire:
                    //   { "text": "..." }           — streamed chunk
                    //   { "answer": "...", "id":"…"} — final summary
                    if (json.has("text")) {
                        onDelta(json.getString("text"))
                    } else if (json.has("id")) {
                        finalConvId = json.optString("id", finalConvId ?: "")
                    }
                } catch (_: Exception) {
                    // ignore non-JSON keepalive chunks
                }
            }
            return finalConvId
        }
    }

    /** Lightweight probe to confirm the stored credentials still work. */
    fun whoami(): Boolean = try {
        val req = Request.Builder()
            .url("${cred.host}/auth/whoami")
            .header("Authorization", "Bearer ${cred.apiKey}")
            .build()
        http.newCall(req).execute().use { it.isSuccessful }
    } catch (_: Exception) { false }
}

class ApiException(val code: Int, val body: String) :
    RuntimeException("HTTP $code: ${body.take(200)}") {
    val isUnauthorized get() = code == 401 || code == 403
}
