import {
  buildLiveTimeline,
  estimateTokens,
  formatMs,
  traceToSegments,
} from "./runTelemetry";

describe("estimateTokens", () => {
  it("approximates 4 chars per token with a floor of 1", () => {
    expect(estimateTokens(0)).toBe(0);
    expect(estimateTokens(2)).toBe(1);
    expect(estimateTokens(400)).toBe(100);
  });
});

describe("formatMs", () => {
  it("formats across the ranges", () => {
    expect(formatMs(null)).toBe("—");
    expect(formatMs(250)).toBe("250ms");
    expect(formatMs(2500)).toBe("2.5s");
    expect(formatMs(42000)).toBe("42s");
    expect(formatMs(125000)).toBe("2m 5s");
  });
});

describe("buildLiveTimeline", () => {
  const t0 = 1_000_000;

  it("positions completed and running calls on the run clock", () => {
    const calls = [
      { id: "a", tool: "search", status: "ok", latency_ms: 1000, startedAt: t0 + 1000 },
      { id: "b", tool: "terminal", status: "running", startedAt: t0 + 3000 },
    ];
    const { rows, spanMs, errors, running } = buildLiveTimeline(calls, t0, t0 + 4000);
    expect(spanMs).toBe(4000);
    expect(errors).toBe(0);
    expect(running).toBe(1);

    const search = rows.find((r) => r.id === "a");
    expect(search.startPct).toBeCloseTo(25);
    expect(search.widthPct).toBeCloseTo(25);
    expect(search.status).toBe("ok");

    const term = rows.find((r) => r.id === "b");
    expect(term.status).toBe("running");
    expect(term.durationMs).toBe(1000); // still growing: now - startedAt
  });

  it("counts errors and clips durations to the span", () => {
    const calls = [
      { id: "a", tool: "x", status: "error", latency_ms: 99999, startedAt: t0 + 500 },
    ];
    const { rows, errors } = buildLiveTimeline(calls, t0, t0 + 2000);
    expect(errors).toBe(1);
    expect(rows[0].startPct + rows[0].widthPct).toBeLessThanOrEqual(100.001);
  });

  it("tolerates missing start times and empty input", () => {
    expect(buildLiveTimeline([], t0, t0 + 1000).rows).toEqual([]);
    expect(buildLiveTimeline([{ id: "x", tool: "t" }], t0, t0 + 1000).rows).toEqual([]);
  });
});

describe("traceToSegments", () => {
  it("lays out llm and tool segments sequentially by duration", () => {
    const { spanMs, segments } = traceToSegments([
      { tool: "llm_turn", args: '{"turn":1,"llm":"gpt"}', latency_ms: 900, status: "ok" },
      { tool: "search", args: "{}", latency_ms: 100, status: "ok" },
      { tool: "llm_fallback", args: "{}", latency_ms: null, status: "ok" },
      { tool: "llm_turn", args: "not json", latency_ms: 1000, status: "ok" },
    ]);
    expect(spanMs).toBe(2000);
    expect(segments[0]).toMatchObject({ kind: "llm", label: "LLM (gpt)", startPct: 0 });
    expect(segments[0].widthPct).toBeCloseTo(45);
    expect(segments[1]).toMatchObject({ kind: "tool", label: "search" });
    expect(segments[1].startPct).toBeCloseTo(45);
    expect(segments[2]).toMatchObject({ kind: "fallback", widthPct: 0 });
    expect(segments[3].label).toBe("LLM turn"); // args parse failure fallback
  });

  it("marks error segments and survives junk rows", () => {
    const { segments } = traceToSegments([
      { tool: "boom", latency_ms: 50, status: "error", error: "dead" },
      null,
      "junk",
    ]);
    expect(segments).toHaveLength(1);
    expect(segments[0].status).toBe("error");
    expect(segments[0].error).toBe("dead");
  });

  it("returns empty for empty traces", () => {
    expect(traceToSegments([]).segments).toEqual([]);
    expect(traceToSegments(null).segments).toEqual([]);
  });
});
