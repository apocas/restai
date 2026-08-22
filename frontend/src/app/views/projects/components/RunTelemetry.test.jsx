import { render, screen } from "@testing-library/react";
import RunTelemetry, { TraceTimelineBar, TimelineLegend } from "./RunTelemetry";

describe("RunTelemetry (live strip)", () => {
  it("renders the run clock, tool rows, and error labeling", () => {
    const t0 = Date.now() - 5000;
    render(
      <RunTelemetry
        active
        startedAt={t0}
        toolCalls={[
          { id: "a", tool: "search_knowledge", status: "ok", latency_ms: 1200, startedAt: t0 + 500 },
          { id: "b", tool: "terminal", status: "error", latency_ms: 300, startedAt: t0 + 2000 },
          { id: "c", tool: "browser_goto", status: "running", startedAt: t0 + 3000 },
        ]}
        outputChars={800}
        fallbacks={1}
      />
    );
    expect(screen.getByText("RUN TELEMETRY")).toBeInTheDocument();
    expect(screen.getByText("search_knowledge")).toBeInTheDocument();
    expect(screen.getByText("terminal")).toBeInTheDocument();
    // Error is labeled in text, never color alone.
    expect(screen.getByText(/err$/)).toBeInTheDocument();
    expect(screen.getByText("ERRORS")).toBeInTheDocument();
    expect(screen.getByText("LLM FALLBACKS")).toBeInTheDocument();
    // 800 chars ≈ 200 tokens.
    expect(screen.getByText("200")).toBeInTheDocument();
    expect(screen.getByText(/3 \(1 live\)/)).toBeInTheDocument();
  });

  it("renders nothing without a start time", () => {
    const { container } = render(<RunTelemetry active={false} startedAt={null} toolCalls={[]} outputChars={0} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("TraceTimelineBar", () => {
  it("renders llm/tool segments and total span from a persisted trace", () => {
    render(
      <TraceTimelineBar
        trace={[
          { tool: "llm_turn", args: '{"turn":1,"llm":"gpt"}', latency_ms: 900, status: "ok" },
          { tool: "search", args: "{}", latency_ms: 1100, status: "error", error: "x" },
        ]}
      />
    );
    expect(screen.getByText("2.0s")).toBeInTheDocument(); // 2000ms span
  });

  it("renders nothing for an empty trace", () => {
    const { container } = render(<TraceTimelineBar trace={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("TimelineLegend", () => {
  it("names every series in text", () => {
    render(<TimelineLegend />);
    expect(screen.getByText("LLM")).toBeInTheDocument();
    expect(screen.getByText("Tool")).toBeInTheDocument();
    expect(screen.getByText("Error")).toBeInTheDocument();
  });
});
