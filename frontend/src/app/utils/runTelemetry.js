// Pure derivations behind the observability visuals: the live playground
// run-telemetry strip and the conversation-details trace timelines. Kept out
// of the components so they're unit-testable (components importing
// react-markdown break under CRA's Jest transform — see CLAUDE.md).

// Rough chars→tokens estimate for the live output counter (≈4 chars/token
// for English-ish text). Display-only; real counts arrive with the final frame.
export function estimateTokens(chars) {
  if (!chars || chars <= 0) return 0;
  return Math.max(1, Math.round(chars / 4));
}

// Live view: lay out the in-flight tool calls (ChatPanel's streamingToolCalls
// entries: {id, tool, status, latency_ms?, startedAt}) against the run clock.
// Returns rows with % offsets/widths on a 0..spanMs axis plus totals.
export function buildLiveTimeline(toolCalls, runStartedAt, nowMs) {
  const startedAt = runStartedAt || nowMs;
  const spanMs = Math.max(1000, nowMs - startedAt);
  const rows = (toolCalls || [])
    .filter((c) => c && c.startedAt)
    .map((c) => {
      const startOffset = Math.max(0, c.startedAt - startedAt);
      const running = c.status === "running" || c.latency_ms == null;
      const duration = running
        ? Math.max(0, nowMs - c.startedAt)
        : Math.max(0, c.latency_ms);
      const clippedDuration = Math.min(duration, spanMs - startOffset);
      return {
        id: c.id,
        tool: c.tool || "tool",
        status: running ? "running" : (c.status === "error" ? "error" : "ok"),
        startPct: (startOffset / spanMs) * 100,
        widthPct: Math.max(0.75, (clippedDuration / spanMs) * 100),
        durationMs: Math.round(duration),
      };
    });
  const errors = rows.filter((r) => r.status === "error").length;
  const running = rows.filter((r) => r.status === "running").length;
  return { rows, spanMs, errors, running };
}

// Persisted-trace view: the stored tool_trace has durations but no start
// offsets, so lay rows out sequentially in recorded order. llm_turn rows
// render as "llm" segments, llm_fallback as zero-width markers, tools as
// their own segments. Returns segments with % offsets over the summed span.
export function traceToSegments(traceRows) {
  const rows = (traceRows || []).filter((r) => r && typeof r === "object");
  const segments = [];
  let cursor = 0;
  for (const row of rows) {
    const latency = typeof row.latency_ms === "number" ? Math.max(0, row.latency_ms) : 0;
    if (row.tool === "llm_fallback") {
      segments.push({ kind: "fallback", label: "LLM fallback", start: cursor, duration: 0, status: "warning" });
      continue;
    }
    const kind = row.tool === "llm_turn" ? "llm" : "tool";
    let label = row.tool;
    if (kind === "llm") {
      try {
        const parsed = JSON.parse(row.args || "{}");
        label = parsed.llm ? `LLM (${parsed.llm})` : "LLM turn";
      } catch {
        label = "LLM turn";
      }
    }
    segments.push({
      kind,
      label,
      start: cursor,
      duration: latency,
      status: row.status === "error" ? "error" : "ok",
      error: row.error || null,
    });
    cursor += latency;
  }
  const spanMs = Math.max(1, cursor);
  return {
    spanMs,
    segments: segments.map((s) => ({
      ...s,
      startPct: (s.start / spanMs) * 100,
      widthPct: s.duration > 0 ? Math.max(0.75, (s.duration / spanMs) * 100) : 0,
    })),
  };
}

export function formatMs(ms) {
  if (ms == null) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)}s`;
  const mins = Math.floor(ms / 60000);
  const secs = Math.round((ms % 60000) / 1000);
  return `${mins}m ${secs}s`;
}
