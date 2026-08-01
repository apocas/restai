import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProjectEditKnowledge from "./ProjectEditKnowledge";
import api from "app/utils/api";
import { toast } from "react-toastify";

jest.setTimeout(20000);

jest.mock("app/utils/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  delete: jest.fn(),
}));
jest.mock("react-toastify", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));

const AUTH = { user: { token: "tok" } };

const JOBS = [
  { id: 1, filename: "manual.pdf", status: "done", documents_count: 3, chunks_count: 42 },
  { id: 2, filename: "broken.docx", status: "error", error_message: "boom: unreadable", documents_count: null, chunks_count: null },
  { id: 3, filename: "next.txt", status: "queued", documents_count: null, chunks_count: null },
];

const makeState = (overrides = {}) => ({
  type: "rag",
  options: { k: 4, score: 0.5, llm_rerank: false },
  ...overrides,
});

const renderKnowledge = (state = makeState(), props = {}) => {
  const setState = jest.fn();
  const handleChange = jest.fn();
  const utils = render(
    <ProjectEditKnowledge
      state={state}
      setState={setState}
      handleChange={handleChange}
      project={{ id: 3, type: "rag" }}
      auth={AUTH}
      info={{ llms: [{ name: "gpt4" }, { name: "mini" }] }}
      {...props}
    />
  );
  return { state, setState, handleChange, ...utils };
};

beforeEach(() => {
  jest.clearAllMocks();
  api.get.mockResolvedValue({ jobs: JOBS });
  api.post.mockResolvedValue({ queued: [7] });
  api.delete.mockResolvedValue({});
});

afterEach(() => {
  jest.useRealTimers();
});

describe("ProjectEditKnowledge", () => {
  it("renders nothing (and never polls) for non-rag projects", () => {
    const { container } = renderKnowledge(makeState({ type: "agent" }));
    expect(container.firstChild).toBeNull();
    expect(api.get).not.toHaveBeenCalled();
  });

  it("loads the bulk ingest job table with status chips and error messages", async () => {
    renderKnowledge();
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith("/projects/3/ingest-bulk?limit=20", "tok", { silent: true })
    );
    expect(await screen.findByText("manual.pdf")).toBeInTheDocument();
    expect(screen.getByText("done")).toBeInTheDocument();
    expect(screen.getByText("queued")).toBeInTheDocument();
    expect(screen.getByText("error")).toBeInTheDocument();
    expect(screen.getByText("boom: unreadable")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("hides the job table entirely when there are no jobs", async () => {
    api.get.mockResolvedValue({ jobs: [] });
    renderKnowledge();
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("polls the job list every 5 seconds and stops after unmount", async () => {
    jest.useFakeTimers();
    const { unmount } = renderKnowledge();

    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));

    act(() => {
      jest.advanceTimersByTime(5000);
    });
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));

    act(() => {
      jest.advanceTimersByTime(10000);
    });
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(4));

    unmount();
    act(() => {
      jest.advanceTimersByTime(20000);
    });
    expect(api.get).toHaveBeenCalledTimes(4);
  });

  it("uploading files POSTs multipart to the bulk endpoint, toasts, and refreshes the table", async () => {
    const { container } = renderKnowledge();
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));

    const input = container.querySelector('input[type="file"]');
    const file = new File(["hello"], "notes.txt", { type: "text/plain" });
    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
    });

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/projects/3/ingest-bulk?method=auto&splitter=sentence&chunks=256",
        expect.any(FormData),
        "tok"
      )
    );
    expect(toast.success).toHaveBeenCalledWith("projects.edit.knowledge.queuedFiles", { position: "top-right" });
    // initial load + post-upload refresh
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
    // input reset so the same file can be re-picked
    expect(input.value).toBe("");
  });

  it("selecting no files does not POST", async () => {
    const { container } = renderKnowledge();
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));
    const input = container.querySelector('input[type="file"]');
    await act(async () => {
      fireEvent.change(input, { target: { files: [] } });
    });
    expect(api.post).not.toHaveBeenCalled();
  });

  it("deleting a job row calls DELETE and refreshes", async () => {
    renderKnowledge();
    expect(await screen.findByText("manual.pdf")).toBeInTheDocument();

    const deleteButtons = screen.getAllByTitle("Delete row");
    fireEvent.click(deleteButtons[1]); // broken.docx → job id 2

    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith("/projects/3/ingest-bulk/2", "tok")
    );
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  });

  it("rerank LLM picker only appears when llm_rerank is on", async () => {
    const { rerender } = render(
      <ProjectEditKnowledge
        state={makeState()}
        setState={jest.fn()}
        handleChange={jest.fn()}
        project={{ id: 3 }}
        auth={AUTH}
        info={{ llms: [{ name: "gpt4" }] }}
      />
    );
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(screen.queryByLabelText("Rerank LLM")).not.toBeInTheDocument();

    rerender(
      <ProjectEditKnowledge
        state={makeState({ options: { k: 4, score: 0.5, llm_rerank: true } })}
        setState={jest.fn()}
        handleChange={jest.fn()}
        project={{ id: 3 }}
        auth={AUTH}
        info={{ llms: [{ name: "gpt4" }] }}
      />
    );
    expect(screen.getByLabelText("Rerank LLM")).toBeInTheDocument();
  });

  it("sync section: Add Source appends a url source, Sync Now triggers the endpoint", async () => {
    const user = userEvent.setup();
    const alertSpy = jest.spyOn(window, "alert").mockImplementation(() => {});
    const state = makeState({
      options: { k: 4, score: 0.5, sync_enabled: true, sync_sources: [] },
    });
    const { setState } = renderKnowledge(state);
    await waitFor(() => expect(api.get).toHaveBeenCalled());

    await user.click(screen.getByRole("button", { name: "Add Source" }));
    expect(setState).toHaveBeenCalledWith({
      ...state,
      options: {
        ...state.options,
        sync_sources: [{ type: "url", name: "", url: "", splitter: "sentence", chunks: 512 }],
      },
    });

    await user.click(screen.getByRole("button", { name: "Sync Now" }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/projects/3/sync/trigger", {}, "tok")
    );
    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith("Sync triggered"));
    alertSpy.mockRestore();
  });

  it("renders existing sync sources with their fields", async () => {
    const state = makeState({
      options: {
        k: 4,
        score: 0.5,
        sync_enabled: true,
        sync_sources: [{ type: "url", name: "docs", url: "https://example.com/docs", splitter: "sentence", sync_interval: 60 }],
      },
    });
    renderKnowledge(state);
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(screen.getByText("Source #1")).toBeInTheDocument();
    expect(screen.getByDisplayValue("https://example.com/docs")).toBeInTheDocument();
    expect(screen.getByDisplayValue("docs")).toBeInTheDocument();
  });
});
