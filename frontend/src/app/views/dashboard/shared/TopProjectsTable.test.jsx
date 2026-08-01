import { render, screen, fireEvent } from "@testing-library/react";
import TopProjectsTable from "./TopProjectsTable";

jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (k) => k }),
}));

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

const projects = [
  {
    id: 1,
    name: "leader",
    type: "rag",
    llm: "gpt-4",
    input_tokens: 1000,
    output_tokens: 500,
    total_cost: 0.1234,
  },
  {
    id: 2,
    name: "runner-up",
    type: "agent",
    input_tokens: 300,
    output_tokens: 100,
    total_cost: 0.05,
  },
  { id: 3, name: "third", type: "block", input_tokens: 100, output_tokens: 0, total_cost: 0 },
  { id: 4, name: "fourth", type: "rag", input_tokens: 50, output_tokens: 0, total_cost: 0 },
];

beforeEach(() => {
  jest.clearAllMocks();
});

describe("TopProjectsTable", () => {
  it("shows the empty state when there is no traffic", () => {
    render(<TopProjectsTable projects={[]} />);
    expect(screen.getByText(/no traffic yet/)).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
    // No footer without a leader.
    expect(screen.queryByText(/leader runs/)).not.toBeInTheDocument();
  });

  it("renders ranked rows with compacted token totals and costs", () => {
    render(<TopProjectsTable projects={projects} />);

    expect(screen.getByText("leader")).toBeInTheDocument();
    expect(screen.getByText("runner-up")).toBeInTheDocument();
    // 1500 tokens compacts to 1.5K; sub-1000 stays numeric.
    expect(screen.getByText(/1\.5K/)).toBeInTheDocument();
    expect(screen.getByText(/400/)).toBeInTheDocument();
    // Costs render with three decimals.
    expect(screen.getByText("$0.123")).toBeInTheDocument();
    expect(screen.getByText("$0.050")).toBeInTheDocument();
    // Ranks past the podium show the plain number — "4" appears both as
    // the count badge (4 projects) and the rank medal of the fourth row.
    expect(screen.getAllByText("4")).toHaveLength(2);
  });

  it("renders the footer mini-stat for the leader", () => {
    render(<TopProjectsTable projects={projects} />);
    const footer = screen.getByText(/leader runs/).closest("div");
    expect(footer).toHaveTextContent("1,500");
    expect(footer).toHaveTextContent("$0.123");
  });

  it("uses the EUR symbol when currency is EUR", () => {
    render(<TopProjectsTable projects={[projects[0]]} currency="EUR" />);
    expect(screen.getAllByText(/€0\.123/).length).toBeGreaterThan(0);
  });

  it("navigates to the project on row click", () => {
    render(<TopProjectsTable projects={projects} />);
    fireEvent.click(screen.getByText("runner-up"));
    expect(mockNavigate).toHaveBeenCalledWith("/project/2");
  });
});
