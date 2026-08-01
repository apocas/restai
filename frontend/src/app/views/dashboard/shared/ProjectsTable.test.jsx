import { render, screen, fireEvent } from "@testing-library/react";
import ProjectsTable from "./ProjectsTable";

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

const projects = [
  {
    id: 5,
    name: "alpha",
    type: "rag",
    llm: "gpt-4",
    team: { name: "engineering" },
    users: [
      { id: 1, username: "alice" },
      { id: 2, username: "bob" },
    ],
  },
  {
    id: 7,
    name: "beta",
    type: "agent",
    users: [],
  },
];

beforeEach(() => {
  jest.clearAllMocks();
});

describe("ProjectsTable", () => {
  it("shows the empty state when there are no projects", () => {
    render(<ProjectsTable projects={[]} />);
    expect(screen.getByText(/no projects yet/)).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
  });

  it("renders the title, count badge and one row per project", () => {
    render(<ProjectsTable projects={projects} title="Latest" />);
    expect(screen.getByText("Latest")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("beta")).toBeInTheDocument();
    // Type pills, LLM and team metadata.
    expect(screen.getByText("rag")).toBeInTheDocument();
    expect(screen.getByText("agent")).toBeInTheDocument();
    expect(screen.getByText(/gpt-4/)).toBeInTheDocument();
    expect(screen.getByText(/engineering/)).toBeInTheDocument();
  });

  it("navigates to the project when a row is clicked", () => {
    render(<ProjectsTable projects={projects} />);
    fireEvent.click(screen.getByText("alpha"));
    expect(mockNavigate).toHaveBeenCalledWith("/project/5");
  });

  it("navigates to /projects/new from the New project button", () => {
    render(<ProjectsTable projects={[]} />);
    fireEvent.click(screen.getByRole("button", { name: /new project/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/projects/new");
  });

  it("hides the New project button in compact mode", () => {
    render(<ProjectsTable projects={[]} compact />);
    expect(
      screen.queryByRole("button", { name: /new project/i })
    ).not.toBeInTheDocument();
  });

  it("opens the playground without also triggering the row click", () => {
    // Compact mode: the only buttons are the per-row action icons
    // (playground first, open-project second).
    render(<ProjectsTable projects={[projects[0]]} compact />);
    const [playgroundBtn, openBtn] = screen.getAllByRole("button");

    fireEvent.click(playgroundBtn);
    expect(mockNavigate).toHaveBeenCalledTimes(1);
    expect(mockNavigate).toHaveBeenCalledWith("/project/5/playground");

    fireEvent.click(openBtn);
    expect(mockNavigate).toHaveBeenCalledTimes(2);
    expect(mockNavigate).toHaveBeenLastCalledWith("/project/5");
  });

  it("collapses more than three members into a +N overflow badge", () => {
    const manyUsers = {
      id: 9,
      name: "crowded",
      type: "block",
      users: [
        { id: 1, username: "u1" },
        { id: 2, username: "u2" },
        { id: 3, username: "u3" },
        { id: 4, username: "u4" },
        { id: 5, username: "u5" },
      ],
    };
    render(<ProjectsTable projects={[manyUsers]} />);
    expect(screen.getByText("+2")).toBeInTheDocument();
  });
});
