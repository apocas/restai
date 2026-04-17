package cloud.restai.mobile

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
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

    data class ChatResult(val conversationId: String?, val answer: String)

    /**
     * Sends [text] and calls [onDelta] for each streamed text chunk. Returns
     * a [ChatResult] with the conversation id and the full answer text.
     * Throws on HTTP error (e.g. 401 after a key rotation).
     */
    fun sendMessage(
        text: String,
        conversationId: String?,
        attachments: List<Attachment> = emptyList(),
        onDelta: (String) -> Unit,
    ): ChatResult {
        val body = JSONObject().apply {
            put("question", text)
            put("stream", true)
            if (conversationId != null) put("id", conversationId)
            if (attachments.isNotEmpty()) {
                // Single image → use the "image" field (base64 data URL)
                val img = attachments.firstOrNull { it.isImage }
                if (img != null) {
                    put("image", "data:${img.mimeType};base64,${img.base64}")
                }
                // All files → use the "files" array
                put("files", JSONArray().apply {
                    attachments.forEach { a ->
                        put(JSONObject().apply {
                            put("name", a.name)
                            put("content", a.base64)
                            put("mime_type", a.mimeType)
                        })
                    }
                })
            }
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
            val fullText = StringBuilder()

            while (!source.exhausted()) {
                val line = source.readUtf8Line() ?: break
                if (line.startsWith("event: close")) break
                if (!line.startsWith("data:")) continue
                val payload = line.removePrefix("data:").trim()
                if (payload.isEmpty()) continue
                try {
                    val json = JSONObject(payload)
                    when {
                        json.has("text") -> {
                            val chunk = json.getString("text")
                            fullText.append(chunk)
                            onDelta(chunk)
                        }
                        json.has("answer") -> {
                            finalConvId = json.optString("id", finalConvId ?: "")
                            val answer = json.getString("answer")
                            if (answer.isNotEmpty()) {
                                fullText.clear()
                                fullText.append(answer)
                            }
                        }
                    }
                } catch (_: Exception) {
                    // ignore non-JSON keepalive chunks
                }
            }
            return ChatResult(finalConvId, fullText.toString())
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
