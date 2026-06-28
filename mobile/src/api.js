import { fetchEventSource } from "@microsoft/fetch-event-source";

// Raised on 401/403 so the UI can clear creds and return to pairing.
export class AuthError extends Error {}
// Internal sentinel used to stop fetchEventSource cleanly (no auto-retry).
class DoneSignal extends Error {}

/**
 * Stream a chat turn. POST {host}/projects/{id}/chat with the Bearer key, parse
 * the SSE frames: `{text}` deltas (onDelta), the final `{answer,id}` frame
 * (onFinal), ignoring tool-call and plan frames, ending on `event: close`.
 * Returns the conversation id to reuse on the next turn.
 */
export async function streamChat({
  host, projectId, apiKey, question, id, image, files, signal, onDelta, onFinal,
}) {
  const body = { question, stream: true };
  if (id) body.id = id;
  if (image) body.image = image;
  if (files && files.length) body.files = files;

  let finalId = id || null;

  try {
    await fetchEventSource(`${host}/projects/${projectId}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
        Accept: "text/event-stream",
      },
      body: JSON.stringify(body),
      signal,
      openWhenHidden: true, // keep streaming if the screen locks / app backgrounds
      async onopen(res) {
        if (res.ok) return;
        if (res.status === 401 || res.status === 403) throw new AuthError("unauthorized");
        throw new Error(`HTTP ${res.status}`);
      },
      onmessage(ev) {
        if (ev.event === "close") throw new DoneSignal();
        if (!ev.data) return;
        let j;
        try {
          j = JSON.parse(ev.data);
        } catch {
          return; // keepalive / non-JSON line
        }
        if (j.tool_call_started || j.tool_call_completed || j.plan) return; // hidden agent activity
        if (j.answer !== undefined) {
          if (j.id) finalId = j.id;
          onFinal(j.answer, finalId);
          throw new DoneSignal();
        }
        if (j.text !== undefined) onDelta(j.text);
      },
      onclose() {
        // Server closed the stream — stop, do not auto-reconnect.
        throw new DoneSignal();
      },
      onerror(err) {
        throw err; // never retry; propagate
      },
    });
  } catch (e) {
    if (e instanceof DoneSignal) return finalId; // normal completion
    throw e; // AuthError, abort, network/HTTP
  }
  return finalId;
}
