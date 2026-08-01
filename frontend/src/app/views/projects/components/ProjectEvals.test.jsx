import { render, screen, waitFor, within, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProjectEvals from "./ProjectEvals";
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

jest.mock("recharts", () => {
  const React = require("react");
  const Wrap = ({ children }) => React.createElement("div", null, children);
  return {
    ResponsiveContainer: Wrap,
    LineChart: ({ children, data }) =>
      React.createElement(
        "div",
        { "data-testid": "line-chart", "data-chart": JSON.stringify(data) },
        children
      ),
    Line: () => null,
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
  };
});

const PROJECT = { id: 7, type: "rag", llm: "gpt4", options: {} };

const DATASETS = [
  { id: 1, name: "ds1", description: "regression set", test_case_count: 2 },
];

const RUNS = [
  {
    id: 10,
    status: "completed",
    summary: { answer_relevancy: 0.9, faithfulness: 0.8 },
    completed_at: new Date().toISOString(),
    prompt_version_id: 3,
    prompt_version: 2,
  },
];

const DATASET_DETAIL = {
  id: 1,
  name: "ds1",
  test_cases: [
    { id: 100, question: "What is X?", expected_answer: "X is Y" },
    { id: 101, question: "What is Z?" },
  ],
};

const RUN_DETAIL = {
  id: 10,
  status: "completed",
  summary: { answer_relevancy: 0.9 },
  results: [
    {
      id: 1,
      test_case_id: 100,
      question: "What is X?",
      expected_answer: "X is Y",
      actual_answer: "X is indeed Y",
      metric_name: "answer_relevancy",
      score: 0.9,
      passed: true,
    },
    {
      id: 2,
      test_case_id: 100,
      metric_name: "faithfulness",
      score: 0.4,
      passed: false,
      reason: "not grounded in context",
    },
  ],
};

let datasetsResp;
let runsResp;

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin" } });
  datasetsResp = () => Promise.resolve([...DATASETS]);
  runsResp = () => Promise.resolve([...RUNS]);
  api.get.mockImplementation((path) => {
    if (path === "/projects/7/evals/datasets") return datasetsResp();
    if (path === "/projects/7/evals/runs") return runsResp();
    if (path === "/projects/7/evals/datasets/1") return Promise.resolve({ ...DATASET_DETAIL });
    if (path === "/projects/7/evals/runs/10") return Promise.resolve({ ...RUN_DETAIL });
    return Promise.resolve({});
  });
});

const renderEvals = async (project = PROJECT) => {
  render(<ProjectEvals project={project} />);
  await screen.findByText("ds1");
};

describe("ProjectEvals", () => {
  it("fetches datasets and runs on mount and renders both tables", async () => {
    await renderEvals();
    expect(api.get).toHaveBeenCalledWith("/projects/7/evals/datasets", "tok");
    expect(api.get).toHaveBeenCalledWith("/projects/7/evals/runs", "tok");
    expect(screen.getByText("regression set")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument(); // case count pill
    // run row: id, status pill, prompt-version chip, score bars
    expect(screen.getByText("#10")).toBeInTheDocument();
    expect(screen.getByText("DONE")).toBeInTheDocument();
    expect(screen.getByText("v2")).toBeInTheDocument();
    expect(screen.getByText("90%")).toBeInTheDocument();
    expect(screen.getByText("80%")).toBeInTheDocument();
  });

  it("renders empty states when there are no datasets or runs", async () => {
    datasetsResp = () => Promise.resolve([]);
    runsResp = () => Promise.resolve([]);
    render(<ProjectEvals project={PROJECT} />);
    expect(await screen.findByText("projects.edit.knowledge.evals.noDatasets")).toBeInTheDocument();
    expect(screen.getByText("projects.edit.knowledge.evals.noRuns")).toBeInTheDocument();
  });

  it("creates a dataset then refetches the list and opens its detail", async () => {
    api.post.mockResolvedValue({ id: 1 });
    const user = userEvent.setup();
    await renderEvals();
    await user.click(screen.getByRole("button", { name: "projects.edit.knowledge.evals.newDataset" }));
    const dialog = screen.getByRole("dialog");
    await user.type(
      within(dialog).getByLabelText("projects.edit.knowledge.evals.name"),
      "new-ds"
    );
    await user.type(
      within(dialog).getByLabelText("projects.edit.knowledge.evals.description"),
      "d"
    );
    await user.click(within(dialog).getByRole("button", { name: "common.create" }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/projects/7/evals/datasets",
        { name: "new-ds", description: "d" },
        "tok"
      )
    );
    // refetch + created-detail fetch
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith("/projects/7/evals/datasets/1", "tok")
    );
  });

  it("selecting a dataset loads its test cases", async () => {
    const user = userEvent.setup();
    await renderEvals();
    await user.click(screen.getByText("ds1"));
    expect(await screen.findByText("What is X?")).toBeInTheDocument();
    expect(screen.getByText("X is Y")).toBeInTheDocument();
    expect(screen.getByText("What is Z?")).toBeInTheDocument();
  });

  it("adds a test case via POST and edits one via PATCH", async () => {
    api.post.mockResolvedValue({});
    api.patch.mockResolvedValue({});
    const user = userEvent.setup();
    await renderEvals();
    await user.click(screen.getByText("ds1"));
    await screen.findByText("What is X?");

    // Add
    await user.click(screen.getByRole("button", { name: "projects.edit.knowledge.evals.addCase" }));
    let dialog = screen.getByRole("dialog");
    await user.type(
      within(dialog).getByLabelText("projects.edit.knowledge.evals.question"),
      "New q?"
    );
    await user.click(within(dialog).getByRole("button", { name: "common.add" }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/projects/7/evals/datasets/1/cases",
        { question: "New q?", expected_answer: "" },
        "tok"
      )
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    // Edit the first case — dialog pre-filled with its values.
    await user.click(document.querySelectorAll('svg[data-testid="EditIcon"]')[0].closest("button"));
    dialog = screen.getByRole("dialog");
    expect(within(dialog).getByDisplayValue("What is X?")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "common.save" }));
    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        "/projects/7/evals/datasets/1/cases/100",
        { question: "What is X?", expected_answer: "X is Y" },
        "tok"
      )
    );
  });

  it("deletes a test case and refetches the dataset detail", async () => {
    api.delete.mockResolvedValue({});
    const user = userEvent.setup();
    await renderEvals();
    await user.click(screen.getByText("ds1"));
    await screen.findByText("What is X?");
    api.get.mockClear();
    await user.click(
      document.querySelectorAll('svg[data-testid="DeleteIcon"]')[1].closest("button")
    );
    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith(
        "/projects/7/evals/datasets/1/cases/100",
        "tok"
      )
    );
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith("/projects/7/evals/datasets/1", "tok")
    );
  });

  it("run dialog offers faithfulness for RAG projects and starts a run", async () => {
    api.post.mockResolvedValue({});
    const user = userEvent.setup();
    await renderEvals();
    await user.click(
      document.querySelector('svg[data-testid="PlayArrowIcon"]').closest("button")
    );
    const dialog = screen.getByRole("dialog");
    // Judged-by LLM shown.
    expect(within(dialog).getByText("gpt4")).toBeInTheDocument();
    // All three metrics offered for RAG.
    expect(within(dialog).getByText("projects.edit.knowledge.evals.answerRelevancy")).toBeInTheDocument();
    expect(within(dialog).getByText("projects.edit.knowledge.evals.faithfulness")).toBeInTheDocument();
    expect(within(dialog).getByText("projects.edit.knowledge.evals.correctness")).toBeInTheDocument();
    // answer_relevancy pre-checked; add correctness.
    await user.click(within(dialog).getByText("projects.edit.knowledge.evals.correctness"));
    await user.click(within(dialog).getByRole("button", { name: "projects.edit.knowledge.evals.start" }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/projects/7/evals/runs",
        { dataset_id: 1, metrics: ["answer_relevancy", "correctness"] },
        "tok"
      )
    );
  });

  it("hides faithfulness for non-RAG projects", async () => {
    const user = userEvent.setup();
    await renderEvals({ ...PROJECT, type: "agent" });
    await user.click(
      document.querySelector('svg[data-testid="PlayArrowIcon"]').closest("button")
    );
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).queryByText("projects.edit.knowledge.evals.faithfulness")).not.toBeInTheDocument();
    expect(within(dialog).getByText("projects.edit.knowledge.evals.faithfulnessRagOnly")).toBeInTheDocument();
  });

  it("deleting a run asks for confirmation first", async () => {
    api.delete.mockResolvedValue({});
    const user = userEvent.setup();
    const confirmSpy = jest.spyOn(window, "confirm").mockReturnValue(false);
    await renderEvals();
    // Runs-table delete icon is the last DeleteIcon on the page.
    const deleteIcons = document.querySelectorAll('svg[data-testid="DeleteIcon"]');
    await user.click(deleteIcons[deleteIcons.length - 1].closest("button"));
    expect(api.delete).not.toHaveBeenCalled();

    confirmSpy.mockReturnValue(true);
    await user.click(deleteIcons[deleteIcons.length - 1].closest("button"));
    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith("/projects/7/evals/runs/10", "tok")
    );
    confirmSpy.mockRestore();
  });

  it("clicking a run opens the per-metric results dialog", async () => {
    const user = userEvent.setup();
    await renderEvals();
    await user.click(screen.getByText("#10"));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith("/projects/7/evals/runs/10", "tok")
    );
    const dialog = await screen.findByRole("dialog");
    // Grouped by test case: question + expected/actual answers.
    expect(await within(dialog).findByText("X is indeed Y")).toBeInTheDocument();
    expect(within(dialog).getByText("X is Y")).toBeInTheDocument();
    // Per-metric rows with pass/fail scores and the failure reason.
    expect(within(dialog).getByText("answer relevancy")).toBeInTheDocument();
    expect(within(dialog).getByText("faithfulness")).toBeInTheDocument();
    expect(within(dialog).getByText("40%")).toBeInTheDocument();
    expect(within(dialog).getByText("not grounded in context")).toBeInTheDocument();
  });

  it("shows the trend hero once two completed runs exist and wires the chart data", async () => {
    runsResp = () =>
      Promise.resolve([
        { ...RUNS[0] },
        {
          id: 9,
          status: "completed",
          summary: { answer_relevancy: 0.7 },
          completed_at: new Date().toISOString(),
        },
      ]);
    await renderEvals();
    expect(screen.getByText("projects.edit.knowledge.evals.scoreTrend")).toBeInTheDocument();
    const series = JSON.parse(
      screen.getByTestId("line-chart").getAttribute("data-chart")
    );
    // Reversed to chronological order: oldest (#9) first.
    expect(series).toHaveLength(2);
    expect(series[0].answer_relevancy).toBe(0.7);
    expect(series[1].answer_relevancy).toBe(0.9);
  });

  it("polls runs every 5s while one is running", async () => {
    jest.useFakeTimers();
    try {
      runsResp = () => Promise.resolve([{ id: 12, status: "running" }]);
      render(<ProjectEvals project={PROJECT} />);
      await act(async () => {}); // flush initial fetches
      const runCalls = () =>
        api.get.mock.calls.filter(([p]) => p === "/projects/7/evals/runs").length;
      expect(runCalls()).toBe(1);
      await act(async () => {
        jest.advanceTimersByTime(5000);
      });
      expect(runCalls()).toBe(2);
      await act(async () => {
        jest.advanceTimersByTime(5000);
      });
      expect(runCalls()).toBe(3);
    } finally {
      jest.useRealTimers();
    }
  });

  it("does not poll when no run is in flight", async () => {
    jest.useFakeTimers();
    try {
      render(<ProjectEvals project={PROJECT} />);
      await act(async () => {});
      const runCalls = () =>
        api.get.mock.calls.filter(([p]) => p === "/projects/7/evals/runs").length;
      expect(runCalls()).toBe(1);
      await act(async () => {
        jest.advanceTimersByTime(15000);
      });
      expect(runCalls()).toBe(1);
    } finally {
      jest.useRealTimers();
    }
  });
});
