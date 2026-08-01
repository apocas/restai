import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Library from "./Library";
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

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({ useNavigate: () => mockNavigate }));

jest.mock("boring-avatars", () => () => {
  const React = require("react");
  return React.createElement("div", { "data-testid": "avatar" });
});

// The component reverses the fetched list (newest first), so kb-search is
// listed first in the payload and helper-bot renders as the first card.
const PROJECTS = [
  { id: 2, name: "kb-search", type: "rag" },
  {
    id: 1,
    name: "helper-bot",
    human_name: "Helper Bot",
    type: "agent",
    llm: "gpt4",
    human_description: "Helps with things",
    system: "You are a helpful assistant",
  },
];

const TEMPLATES = [
  {
    id: 5,
    name: "Support Bot",
    project_type: "agent",
    visibility: "public",
    use_count: 3,
    description: "Ready-made support agent",
    creator_username: "bob",
    suggested_llm: "gpt4",
  },
  {
    id: 6,
    name: "Doc RAG",
    project_type: "rag",
    visibility: "team",
    use_count: 0,
  },
];

let teamsResp;

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin" } });
  teamsResp = { teams: [{ id: 4, name: "acme" }, { id: 9, name: "beta" }] };
  api.get.mockImplementation((path) => {
    if (path.startsWith("/projects")) return Promise.resolve({ projects: [...PROJECTS] });
    if (path.startsWith("/templates")) return Promise.resolve([...TEMPLATES]);
    if (path.startsWith("/teams")) return Promise.resolve(teamsResp);
    if (path.startsWith("/info")) return Promise.resolve({ llms: [{ id: 1, name: "gpt4" }, { id: 2, name: "llama" }] });
    return Promise.resolve({});
  });
});

const renderLibrary = async () => {
  render(<Library />);
  await screen.findByText("Helper Bot");
  await screen.findByText("Support Bot");
};

describe("Library", () => {
  it("fetches public projects, templates, teams and llms on mount", async () => {
    await renderLibrary();
    expect(api.get).toHaveBeenCalledWith("/projects?filter=public", "tok");
    expect(api.get).toHaveBeenCalledWith("/templates", "tok");
    expect(api.get).toHaveBeenCalledWith("/teams", "tok");
    expect(api.get).toHaveBeenCalledWith("/info", "tok");
    // shared project cards
    expect(screen.getByText("Helper Bot")).toBeInTheDocument();
    expect(screen.getByText("kb-search")).toBeInTheDocument();
    expect(screen.getByText("Helps with things")).toBeInTheDocument();
    expect(screen.getByText("You are a helpful assistant")).toBeInTheDocument();
    // hero stats
    expect(screen.getByText("2 shared")).toBeInTheDocument();
    expect(screen.getByText("2 templates")).toBeInTheDocument();
    // template cards
    expect(screen.getByText("Doc RAG")).toBeInTheDocument();
    expect(screen.getByText("projects.library.uses")).toBeInTheDocument(); // use_count > 0 chip
    expect(screen.getByText("projects.library.by")).toBeInTheDocument(); // author byline
  });

  it("type filter narrows both projects and templates", async () => {
    const user = userEvent.setup();
    await renderLibrary();
    await user.click(screen.getByText("Rag"));
    expect(screen.queryByText("Helper Bot")).not.toBeInTheDocument();
    expect(screen.getByText("kb-search")).toBeInTheDocument();
    expect(screen.queryByText("Support Bot")).not.toBeInTheDocument();
    expect(screen.getByText("Doc RAG")).toBeInTheDocument();
  });

  it("shows empty states when nothing is shared", async () => {
    api.get.mockImplementation((path) => {
      if (path.startsWith("/projects")) return Promise.resolve({ projects: [] });
      if (path.startsWith("/templates")) return Promise.resolve([]);
      if (path.startsWith("/teams")) return Promise.resolve({ teams: [] });
      return Promise.resolve({});
    });
    render(<Library />);
    expect(await screen.findByText("projects.library.noSharedProjects")).toBeInTheDocument();
    expect(screen.getByText("projects.library.noTemplates")).toBeInTheDocument();
  });

  it("card title and playground button navigate to the project", async () => {
    const user = userEvent.setup();
    await renderLibrary();
    await user.click(screen.getByText("Helper Bot"));
    expect(mockNavigate).toHaveBeenCalledWith("/project/1");
    await user.click(screen.getAllByRole("button", { name: "projects.actions.playground" })[0]);
    expect(mockNavigate).toHaveBeenCalledWith("/project/1/playground");
  });

  it("clone dialog posts the new name and navigates to the clone", async () => {
    api.post.mockResolvedValue({ project: 42 });
    const user = userEvent.setup();
    await renderLibrary();
    // First card's clone button (Helper Bot).
    await user.click(screen.getAllByRole("button", { name: "projects.actions.clone" })[0]);
    // Prefilled with "<name>-clone".
    expect(screen.getByDisplayValue("helper-bot-clone")).toBeInTheDocument();
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "projects.actions.clone" }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/projects/1/clone",
        { name: "helper-bot-clone" },
        "tok"
      )
    );
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/project/42"));
  });

  it("use-template dialog defaults name slug, first team and suggested llm, then instantiates", async () => {
    api.post.mockResolvedValue({ id: 77 });
    const user = userEvent.setup();
    await renderLibrary();
    await user.click(screen.getAllByRole("button", { name: "projects.actions.useTemplate" })[0]);
    // Slugified default name from the template title.
    expect(screen.getByDisplayValue("support-bot")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "projects.template.create" }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/templates/5/instantiate",
        { name: "support-bot", team_id: 4, llm: "gpt4" },
        "tok"
      )
    );
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/project/77"));
  });

  it("template without suggested llm instantiates with llm undefined", async () => {
    api.post.mockResolvedValue({ id: 78 });
    const user = userEvent.setup();
    await renderLibrary();
    await user.click(screen.getAllByRole("button", { name: "projects.actions.useTemplate" })[1]);
    expect(screen.getByDisplayValue("doc-rag")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "projects.template.create" }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/templates/6/instantiate",
        { name: "doc-rag", team_id: 4, llm: undefined },
        "tok"
      )
    );
  });

  it("use-template buttons are disabled when the user has no teams", async () => {
    teamsResp = { teams: [] };
    render(<Library />);
    await screen.findByText("Support Bot");
    for (const btn of screen.getAllByRole("button", { name: "projects.actions.useTemplate" })) {
      expect(btn).toBeDisabled();
    }
  });
});
