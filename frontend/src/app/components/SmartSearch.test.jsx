import { render, screen, fireEvent, act } from "@testing-library/react";
import SmartSearch from "./SmartSearch";
import api from "app/utils/api";

jest.mock("app/utils/api", () => ({ get: jest.fn(), post: jest.fn() }));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

// SmartSearch enforces a MIN_LOADING_MS of 800ms before applying results,
// rotates loading messages on a 1400ms interval, and focuses the input on a
// 100ms timeout — fake timers keep all of that deterministic.
const flushPromises = () => act(async () => {});
const advance = (ms) => act(() => jest.advanceTimersByTime(ms));

// Type into the search box and press Enter.
const typeAndSearch = (text) => {
  const input = screen.getByPlaceholderText(/Search anything/i);
  fireEvent.change(input, { target: { value: text } });
  fireEvent.keyDown(input, { key: "Enter" });
};

// Resolve the in-flight api promise, then jump past the min-loading delay.
const settleSearch = async () => {
  await flushPromises();
  advance(800);
};

const renderSearch = (props = {}) =>
  render(<SmartSearch open onClose={jest.fn()} {...props} />);

beforeEach(() => {
  jest.useFakeTimers();
  jest.clearAllMocks();
  useAuth.mockReturnValue({
    user: { token: "tok", is_admin: true, username: "admin" },
  });
  api.post.mockResolvedValue({ results: [] });
});

afterEach(() => {
  act(() => jest.runOnlyPendingTimers());
  jest.useRealTimers();
});

describe("SmartSearch", () => {
  it("renders nothing when closed", () => {
    render(<SmartSearch open={false} onClose={jest.fn()} />);
    expect(screen.queryByText("Smart Search")).not.toBeInTheDocument();
  });

  it("shows suggestion chips in the initial empty state", () => {
    renderSearch();
    expect(screen.getByText("Smart Search")).toBeInTheDocument();
    expect(screen.getByText("Try")).toBeInTheDocument();
    expect(screen.getByText("rag projects using gpt-4")).toBeInTheDocument();
    expect(screen.getByText("restricted users")).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it("does not search on Enter when the query is empty or whitespace", () => {
    renderSearch();
    const input = screen.getByPlaceholderText(/Search anything/i);
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.change(input, { target: { value: "   " } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(api.post).not.toHaveBeenCalled();
  });

  it("posts the query on Enter, shows loading, then renders results", async () => {
    api.post.mockResolvedValue({
      results: [
        {
          entity: "projects",
          id: 1,
          name: "support-bot",
          subtitle: "rag · gpt-4",
          path: "/project/1",
        },
        { entity: "users", id: 2, name: "alice", path: "/user/alice" },
      ],
    });
    renderSearch();
    typeAndSearch("rag projects");

    expect(api.post).toHaveBeenCalledWith(
      "/search",
      { query: "rag projects" },
      "tok"
    );
    // Loading state shown while the request + min-loading window are pending.
    expect(screen.getByText("Asking the AI...")).toBeInTheDocument();

    await settleSearch();

    expect(screen.queryByText("Asking the AI...")).not.toBeInTheDocument();
    expect(screen.getByText("support-bot")).toBeInTheDocument();
    expect(screen.getByText("rag · gpt-4")).toBeInTheDocument();
    expect(screen.getByText("alice")).toBeInTheDocument();
    // Entity chips use friendly labels.
    expect(screen.getByText("Project")).toBeInTheDocument();
    expect(screen.getByText("User")).toBeInTheDocument();
  });

  it("holds results until the 800ms minimum loading window elapses", async () => {
    api.post.mockResolvedValue({
      results: [{ entity: "teams", id: 3, name: "engineering", path: "/team/3" }],
    });
    renderSearch();
    typeAndSearch("teams");

    await flushPromises();
    // API already resolved, but min-loading window not elapsed yet.
    advance(500);
    expect(screen.queryByText("engineering")).not.toBeInTheDocument();
    expect(screen.getByText(/Asking the AI|Translating your query|Understanding what you mean|Searching the database/)).toBeInTheDocument();

    advance(300);
    expect(screen.getByText("engineering")).toBeInTheDocument();
  });

  it("rotates the loading message while waiting", async () => {
    // Keep the request pending forever so loading stays on.
    api.post.mockReturnValue(new Promise(() => {}));
    renderSearch();
    typeAndSearch("anything");

    expect(screen.getByText("Asking the AI...")).toBeInTheDocument();
    advance(1400);
    expect(screen.getByText("Translating your query...")).toBeInTheDocument();
    advance(1400);
    expect(screen.getByText("Understanding what you mean...")).toBeInTheDocument();
  });

  it("runs a search when a suggestion chip is clicked", async () => {
    renderSearch();
    fireEvent.click(screen.getByText("restricted users"));
    expect(api.post).toHaveBeenCalledWith(
      "/search",
      { query: "restricted users" },
      "tok"
    );
    await settleSearch();
  });

  it("renders the structured-query header, note and warnings", async () => {
    api.post.mockResolvedValue({
      results: [{ entity: "projects", id: 1, name: "p1", path: "/project/1" }],
      query: {
        entity: "projects",
        filters: [
          { field: "type", op: "=", value: "rag" },
          { field: "llm", op: "contains", value: "gpt" },
        ],
      },
      note: "Interpreted loosely",
      warnings: ["Ignored unknown field 'foo'"],
    });
    renderSearch();
    typeAndSearch("rag projects using gpt");
    await settleSearch();

    expect(screen.getByText("projects")).toBeInTheDocument();
    expect(screen.getByText('type = "rag"')).toBeInTheDocument();
    expect(screen.getByText(/AND\s+llm contains "gpt"/)).toBeInTheDocument();
    expect(screen.getByText("Interpreted loosely")).toBeInTheDocument();
    expect(screen.getByText("Ignored unknown field 'foo'")).toBeInTheDocument();
  });

  it("shows the empty state when a structured query returns no rows", async () => {
    api.post.mockResolvedValue({
      results: [],
      query: { entity: "users", filters: [] },
    });
    renderSearch();
    typeAndSearch("users named zorp");
    await settleSearch();
    expect(
      screen.getByText("No results matching your query.")
    ).toBeInTheDocument();
  });

  it("shows the API error detail on failure", async () => {
    api.post.mockRejectedValue({ detail: "System LLM not configured" });
    renderSearch();
    typeAndSearch("anything");
    await settleSearch();
    expect(screen.getByText("System LLM not configured")).toBeInTheDocument();
  });

  it("falls back to a generic error message when detail is missing", async () => {
    api.post.mockRejectedValue(new Error("network down"));
    renderSearch();
    typeAndSearch("anything");
    await settleSearch();
    expect(screen.getByText("Search failed")).toBeInTheDocument();
  });

  it("navigates to a result's path and closes the dialog on click", async () => {
    const onClose = jest.fn();
    api.post.mockResolvedValue({
      results: [
        { entity: "llms", id: 9, name: "gpt-4o", path: "/llms" },
      ],
    });
    renderSearch({ onClose });
    typeAndSearch("public llms");
    await settleSearch();

    fireEvent.click(screen.getByText("gpt-4o"));
    expect(onClose).toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith("/llms");
  });
});
