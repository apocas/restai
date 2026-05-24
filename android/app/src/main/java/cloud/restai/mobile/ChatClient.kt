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
            // Disable gzip — OkHttp adds it automatically and its transparent
            // decompression buffers the entire response, killing SSE streaming.
            .header("Accept-Encoding", "identity")
            .header("Cache-Control", "no-cache")
            .build()

        http.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) {
                throw ApiException(resp.code, resp.body?.string().orEmpty())
            }
            val source = resp.body?.source() ?: error("empty body")
            var finalConvId: String? = conversationId
            val fullText = StringBuilder()
            // Buffer for stripping <think>…</think> blocks that may span
            // multiple SSE chunks. While inside a think block, text is
            // silently consumed; only non-think text reaches onDelta.
            var insideThink = false

            while (!source.exhausted()) {
                val line = source.readUtf8Line() ?: break
                if (line.startsWith("event: close")) break
                if (!line.startsWith("data:")) continue
                val payload = line.removePrefix("data:").trim()
                if (payload.isEmpty()) continue
                try {
                    val json = JSONObject(payload)
                    when {
                        // Skip tool/plan/event-only frames — only render
                        // plain text deltas and the final answer.
                        json.has("tool_call_started") ||
                        json.has("tool_call_completed") ||
                        json.has("plan") -> { /* silently skip */ }

                        json.has("text") && !json.has("answer") -> {
                            val chunk = json.getString("text")
                            // Strip <think>…</think> reasoning blocks so the
                            // user only sees the actual output.
                            val cleaned = stripThinkTags(chunk, insideThink)
                            insideThink = cleaned.second
                            val visible = cleaned.first
                            if (visible.isNotEmpty()) {
                                fullText.append(visible)
                                onDelta(visible)
                            }
                        }
                        json.has("answer") -> {
                            finalConvId = json.optString("id", finalConvId ?: "")
                            var answer = json.getString("answer")
                            // Final answer may still contain think tags — strip.
                            answer = answer.replace(Regex("<think>[\\s\\S]*?</think>"), "").trim()
                            if (answer.isNotEmpty()) {
                                fullText.clear()
                                fullText.append(answer)
                            }
                            break
                        }
                    }
                } catch (_: Exception) {
                    // ignore non-JSON keepalive chunks
                }
            }
            return ChatResult(finalConvId, fullText.toString())
        }
    }

    /**
     * Strip `<think>…</think>` blocks from a streaming chunk, handling the
     * case where the open tag arrives in one chunk and the close tag in a
     * later one. Returns (visible_text, still_inside_think).
     */
    private fun stripThinkTags(chunk: String, wasInside: Boolean): Pair<String, Boolean> {
        var inside = wasInside
        val out = StringBuilder()
        var i = 0
        while (i < chunk.length) {
            if (inside) {
                val close = chunk.indexOf("</think>", i)
                if (close == -1) return Pair(out.toString(), true)
                i = close + 8
                inside = false
            } else {
                val open = chunk.indexOf("<think>", i)
                if (open == -1) {
                    out.append(chunk, i, chunk.length)
                    break
                }
                out.append(chunk, i, open)
                i = open + 7
                inside = true
            }
        }
        return Pair(out.toString(), inside)
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
