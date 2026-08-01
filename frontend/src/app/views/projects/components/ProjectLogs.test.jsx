import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProjectLogs from "./ProjectLogs";
import api from "app/utils/api";

jest.mock("app/utils/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  delete: jest.fn(),
}));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

// ChatReplayDialog pulls PlaygroundLanes -> react-markdown (ESM-only,
// breaks CRA's Jest transform) — stub it and assert the wiring props.
jest.mock("./ChatReplayDialog", () => (props) => {
  const React = require("react");
  if (!props.open) return null;
  return React.createElement(
    "div",
    { "data-testid": "replay-dialog" },
    `replay:${props.chatId}:project:${props.projectId}`
  );
});

jest.mock("@microlink/react-json-view", () => (props) => {
  const React = require("react");
  return React.createElement("div", {
    "data-testid": "react-json",
    "data-src-id": props.src && props.src.id,
  });
});

const LOGS = [
  {
    id: 1,
    status: null, // treated as success
    date: new Date().toISOString(),
    question: "What is the capital of France?",
    answer: "Paris",
    latency_ms: 850,
    input_tokens: 100,
    output_tokens: 50,
    chat_id: "chat-abc",
    llm: "gpt4",
    system_prompt: "You are helpful",
    context: JSON.stringify({ source: "kb" }),
    attachments: JSON.stringify([{ name: "report.pdf", size: 2048 }]),
    tool_trace: JSON.stringify([
      { tool: "search_knowledge", args: '{"q":"capital"}', latency_ms: 120, status: "ok" },
      { tool: "browser_goto", args: "", latency_ms: 6000, status: "error", error: "connection refused" },
    ]),
  },
  {
    id: 2,
    status: "error",
    date: new Date().toISOString(),
    question: "broken request",
    answer: null,
    error: "LLM timeout after 60s",
    latency_ms: 6200,
    input_tokens: 0,
    output_tokens: 0,
  },
  {
    id: 3,
    status: "guard_block",
    date: new Date().toISOString(),
    question: "something naughty",
    answer: "Blocked by guard",
    latency_ms: 300,
    input_tokens: 10,
    output_tokens: 5,
  },
];

let logsResp;

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin" } });
  logsResp = () => Promise.resolve({ logs: LOGS });
  api.get.mockImplementation((path) => {
    if (path.includes("/logs")) return logsResp();
    return Promise.resolve({});
  });
});

const renderLogs = async () => {
  render(<ProjectLogs project={{ id: 7, name: "proj" }} />);
  await screen.findByText("What is the capital of France?");
};

describe("ProjectLogs", () => {
  it("shows a spinner while loading", () => {
    logsResp = () => new Promise(() => {});
    render(<ProjectLogs project={{ id: 7 }} />);
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("fetches the first page and renders rows with status pills, latency and tokens", async () => {
    await renderLogs();
    expect(api.get).toHaveBeenCalledWith("/projects/7/logs?start=0&end=25", "tok");
    expect(screen.getByText("3 entries on page 1")).toBeInTheDocument();
    // Status pills: null status coerced to OK; error + guard mapped.
    expect(screen.getByText("OK")).toBeInTheDocument();
    expect(screen.getByText("ERROR")).toBeInTheDocument();
    expect(screen.getByText("GUARD")).toBeInTheDocument();
    // Latency badges (ms below 1s, seconds above).
    expect(screen.getByText("850ms")).toBeInTheDocument();
    expect(screen.getByText("6.2s")).toBeInTheDocument();
    // Token total = input + output.
    expect(screen.getByText("150")).toBeInTheDocument();
    // Attachment chip visible inline on the question cell.
    expect(screen.getAllByText(/report\.pdf/).length).toBeGreaterThanOrEqual(1);
  });

  it("renders the empty state when there are no logs", async () => {
    logsResp = () => Promise.resolve({ logs: [] });
    render(<ProjectLogs project={{ id: 7 }} />);
    expect(
      await screen.findByText("No logs yet — run an inference to see it here.")
    ).toBeInTheDocument();
  });

  it("parses and renders the tool trace, error and context in the expanded panel", async () => {
    await renderLogs();
    // Collapse keeps children mounted; the parsed trace should be wired in.
    expect(screen.getByText("TOOL TRACE · 2 CALLS")).toBeInTheDocument();
    expect(screen.getByText("search_knowledge")).toBeInTheDocument();
    expect(screen.getByText('{"q":"capital"}')).toBeInTheDocument();
    expect(screen.getByText("browser_goto")).toBeInTheDocument();
    expect(screen.getByText("(no args)")).toBeInTheDocument();
    // Failing step surfaces its error text.
    expect(screen.getByText("connection refused")).toBeInTheDocument();
    // Error log block for the failed inference.
    expect(screen.getByText("LLM timeout after 60s")).toBeInTheDocument();
    // Context entries become chips.
    expect(screen.getByText("source: kb")).toBeInTheDocument();
    // System prompt terminal block.
    expect(screen.getByText("You are helpful")).toBeInTheDocument();
    // Raw JSON viewers get the log object.
    expect(
      screen.getAllByTestId("react-json").map((n) => n.getAttribute("data-src-id"))
    ).toEqual(expect.arrayContaining(["1", "2", "3"]));
  });

  it("filters rows by free-text search", async () => {
    const user = userEvent.setup();
    await renderLogs();
    await user.type(
      screen.getByPlaceholderText("Search question, answer, LLM or error…"),
      "broken"
    );
    expect(screen.getByText("broken request")).toBeInTheDocument();
    expect(screen.queryByText("What is the capital of France?")).not.toBeInTheDocument();
    expect(screen.queryByText("something naughty")).not.toBeInTheDocument();
  });

  it("filters rows by status (failures hides successes)", async () => {
    const user = userEvent.setup();
    await renderLogs();
    await user.click(screen.getByLabelText("Status"));
    await user.click(await screen.findByRole("option", { name: "Failures" }));
    expect(screen.queryByText("What is the capital of France?")).not.toBeInTheDocument();
    expect(screen.getByText("broken request")).toBeInTheDocument();
    expect(screen.getByText("something naughty")).toBeInTheDocument();
  });

  it("opens the replay dialog only for rows with a chat_id", async () => {
    const user = userEvent.setup();
    await renderLogs();
    const replayIcons = document.querySelectorAll('svg[data-testid="PlayCircleOutlineIcon"]');
    expect(replayIcons).toHaveLength(1); // only log 1 has chat_id
    await user.click(replayIcons[0].closest("button"));
    expect(screen.getByTestId("replay-dialog")).toHaveTextContent(
      "replay:chat-abc:project:7"
    );
  });

  it("paginates: next fetches the next slice, prev is disabled on page one", async () => {
    const fullPage = Array.from({ length: 25 }, (_, i) => ({
      id: i + 1,
      date: new Date().toISOString(),
      question: `q${i + 1}`,
      answer: "a",
      latency_ms: 100,
    }));
    logsResp = () => Promise.resolve({ logs: fullPage });
    const user = userEvent.setup();
    render(<ProjectLogs project={{ id: 7 }} />);
    await screen.findByText("q1");

    const prevBtn = document
      .querySelector('svg[data-testid="ChevronLeftIcon"]')
      .closest("button");
    expect(prevBtn).toBeDisabled();

    await user.click(
      document.querySelector('svg[data-testid="ChevronRightIcon"]').closest("button")
    );
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith("/projects/7/logs?start=25&end=50", "tok")
    );
    expect(await screen.findByText("Page 2")).toBeInTheDocument();
  });

  it("next is disabled when the page is shorter than the page size", async () => {
    await renderLogs();
    expect(
      document.querySelector('svg[data-testid="ChevronRightIcon"]').closest("button")
    ).toBeDisabled();
  });

  it("changing rows-per-page refetches from the start", async () => {
    const user = userEvent.setup();
    await renderLogs();
    await user.click(screen.getByLabelText("Per page"));
    await user.click(await screen.findByRole("option", { name: "10" }));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith("/projects/7/logs?start=0&end=10", "tok")
    );
  });
});
