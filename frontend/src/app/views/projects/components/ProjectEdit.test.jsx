import { render as rtlRender, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import ProjectEdit from "./ProjectEdit";
import api from "app/utils/api";

// ProjectTabNav's useMediaQuery takes a function query — needs a real theme.
const theme = createTheme();
const render = (ui) => rtlRender(<ThemeProvider theme={theme}>{ui}</ThemeProvider>);

jest.setTimeout(20000);

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
jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}));

// The five tab bodies get dedicated suites — here they're stubbed so the
// shell test focuses on load / tab switching / save payload / fieldErrors
// plumbing without dragging in the whole form tree.
jest.mock("./ProjectEditGeneral", () => {
  const React = require("react");
  return function MockGeneral({ fieldErrors, handleChange, handleTeamChange, clearFieldError }) {
    return React.createElement(
      "div",
      { "data-testid": "tab-general" },
      React.createElement("span", { "data-testid": "general-field-errors" }, JSON.stringify(fieldErrors)),
      React.createElement(
        "button",
        { type: "button", onClick: () => handleChange({ target: { name: "human_name", value: "Renamed", type: "text" } }) },
        "mutate-name"
      ),
      React.createElement(
        "button",
        { type: "button", onClick: () => handleTeamChange({ target: { value: 9 } }) },
        "pick-team"
      ),
      React.createElement(
        "button",
        { type: "button", onClick: () => clearFieldError("options.rate_limit") },
        "clear-error"
      )
    );
  };
});
jest.mock("./ProjectEditSystemPrompt", () => {
  const React = require("react");
  return function MockSystem() {
    return React.createElement("div", { "data-testid": "tab-system" });
  };
});
jest.mock("./ProjectEditKnowledge", () => {
  const React = require("react");
  return function MockKnowledge({ fieldErrors }) {
    return React.createElement(
      "div",
      { "data-testid": "tab-knowledge" },
      React.createElement("span", { "data-testid": "knowledge-field-errors" }, JSON.stringify(fieldErrors))
    );
  };
});
jest.mock("./ProjectEditSecurity", () => {
  const React = require("react");
  return function MockSecurity({ fieldErrors, handleChange }) {
    return React.createElement(
      "div",
      { "data-testid": "tab-security" },
      React.createElement("span", { "data-testid": "security-field-errors" }, JSON.stringify(fieldErrors)),
      // Lets shell tests drive the budget field through the real handleChange.
      React.createElement("button", {
        type: "button", // inside the form — must not act as a submit
        "data-testid": "security-set-budget",
        onClick: () => handleChange({ target: { name: "budget", value: "12.5" } }),
      })
    );
  };
});
jest.mock("./ProjectEditIntegrations", () => {
  const React = require("react");
  return function MockIntegrations() {
    return React.createElement("div", { "data-testid": "tab-integrations" });
  };
});

const RAG_PROJECT = {
  id: 3,
  name: "docs",
  human_name: "Docs",
  human_description: "the docs bot",
  type: "rag",
  llm: "gpt4",
  embeddings: "embed1",
  guard: "12",
  censorship: "blocked",
  public: false,
  default_prompt: "",
  system: "You are docs.",
  users: [{ username: "bob" }],
  team: { id: 7 },
  options: { k: 6, score: 0.5, logging: true },
};

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  api.get.mockImplementation((path) => {
    if (path === "/users") {
      return Promise.resolve({ users: [{ username: "admin" }, { username: "bob" }] });
    }
    if (path === "/teams") return Promise.resolve({ teams: [{ id: 7, name: "acme" }] });
    if (path === "/teams/7") return Promise.resolve({ id: 7, name: "acme", llms: [] });
    if (path === "/teams/9") return Promise.resolve({ id: 9, name: "beta", llms: [] });
    if (path.endsWith("/prompts")) return Promise.resolve([{ id: 1, version: 1 }]);
    return Promise.resolve({});
  });
  api.patch.mockResolvedValue({ id: 3 });
});

const renderShell = async (project = RAG_PROJECT) => {
  render(<ProjectEdit project={project} projects={[]} info={{ llms: [], embeddings: [], loaders: [] }} />);
  await screen.findByTestId("tab-general");
  // wait for the member-hydration effect so save payloads are deterministic
  await waitFor(() => expect(api.get).toHaveBeenCalledWith("/users", "tok"));
};

describe("ProjectEdit shell", () => {
  it("loads lookups on mount and shows the General tab by default", async () => {
    await renderShell();
    expect(api.get).toHaveBeenCalledWith("/users", "tok");
    expect(api.get).toHaveBeenCalledWith("/teams", "tok");
    expect(api.get).toHaveBeenCalledWith("/projects/3/prompts", "tok", { silent: true });
    expect(api.get).toHaveBeenCalledWith("/teams/7", "tok", { silent: true });
    expect(screen.getByTestId("tab-general")).toBeInTheDocument();
    // rag → Knowledge tab present
    expect(screen.getByRole("button", { name: "projects.edit.tabs.knowledge" })).toBeInTheDocument();
  });

  it("hides the Knowledge tab and skips prompt fetch appropriately for non-rag projects", async () => {
    const agent = { ...RAG_PROJECT, type: "agent", id: 4 };
    render(<ProjectEdit project={agent} projects={[]} info={{ llms: [], embeddings: [] }} />);
    await screen.findByTestId("tab-general");
    expect(screen.queryByRole("button", { name: "projects.edit.tabs.knowledge" })).not.toBeInTheDocument();
    // agent still versions its prompt
    expect(api.get).toHaveBeenCalledWith("/projects/4/prompts", "tok", { silent: true });
  });

  it("does not fetch prompt versions for block projects", async () => {
    const block = { ...RAG_PROJECT, type: "block", id: 5, team: null };
    render(<ProjectEdit project={block} projects={[]} info={{ llms: [], embeddings: [] }} />);
    await screen.findByTestId("tab-general");
    expect(api.get).not.toHaveBeenCalledWith("/projects/5/prompts", "tok", { silent: true });
  });

  it("hides agent/rag-only tabs from block projects", async () => {
    // Regression: '!project.type === "agent"' precedence bug made this
    // gating dead — block projects used to see the System tab.
    const block = { ...RAG_PROJECT, type: "block", id: 5, team: null };
    render(<ProjectEdit project={block} projects={[]} info={{ llms: [], embeddings: [] }} />);
    await screen.findByTestId("tab-general");
    expect(screen.queryByRole("button", { name: "projects.edit.tabs.system" })).not.toBeInTheDocument();
  });

  it("switches tabs via the side nav", async () => {
    const user = userEvent.setup();
    await renderShell();

    await user.click(screen.getByRole("button", { name: "projects.edit.tabs.security" }));
    expect(screen.getByTestId("tab-security")).toBeInTheDocument();
    expect(screen.queryByTestId("tab-general")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "projects.edit.tabs.knowledge" }));
    expect(screen.getByTestId("tab-knowledge")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "projects.edit.tabs.integrations" }));
    expect(screen.getByTestId("tab-integrations")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "projects.edit.tabs.system" }));
    expect(screen.getByTestId("tab-system")).toBeInTheDocument();
  });

  it("save PATCHes the mapped rag payload and navigates back to the project", async () => {
    const user = userEvent.setup();
    await renderShell();
    // wait for team + member hydration so the payload carries them
    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/teams/7", "tok", { silent: true }));

    await user.click(screen.getByRole("button", { name: /common.save/ }));

    await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1));
    const [path, payload, token] = api.patch.mock.calls[0];
    expect(path).toBe("/projects/3");
    expect(token).toBe("tok");
    expect(payload).toEqual(
      expect.objectContaining({
        name: "docs",
        llm: "gpt4",
        embeddings: "embed1",
        human_name: "Docs",
        human_description: "the docs bot",
        guard: "12",
        censorship: "blocked",
        public: false,
        team_id: 7,
        users: ["bob"],
        system: "You are docs.",
      })
    );
    expect(payload.options).toEqual(
      expect.objectContaining({
        logging: true,
        k: 6,
        score: 0.5,
        rate_limit: null,
        guard_output: null,
        guard_mode: "block",
        eval_llm: null,
        sync_enabled: false,
        enable_knowledge_graph: false,
      })
    );
    // agent-only options must not leak into a rag payload
    expect(payload.options).not.toHaveProperty("agent_loop");
    expect(mockNavigate).toHaveBeenCalledWith("/project/3");
  });

  it("budget edits land in options.budget and survive into the PATCH", async () => {
    // Regression: budget used to be written to a top-level state key the
    // submit never mapped — edits were silently discarded. The limiter
    // reads options.budget, so that's where it must go.
    const user = userEvent.setup();
    await renderShell();
    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/teams/7", "tok", { silent: true }));

    await user.click(screen.getByRole("button", { name: "projects.edit.tabs.security" }));
    await user.click(screen.getByTestId("security-set-budget"));
    await user.click(screen.getByRole("button", { name: /common.save/ }));

    await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1));
    const [, payload] = api.patch.mock.calls[0];
    expect(payload.options).toEqual(expect.objectContaining({ budget: 12.5 }));
  });

  it("agent save carries memory-bank/browser options but no rag retrieval options", async () => {
    const user = userEvent.setup();
    const agent = {
      ...RAG_PROJECT,
      type: "agent",
      id: 4,
      options: { logging: false, memory_bank_enabled: true, memory_bank_max_tokens: 4000 },
    };
    render(<ProjectEdit project={agent} projects={[]} info={{ llms: [], embeddings: [] }} />);
    await screen.findByTestId("tab-general");
    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/teams/7", "tok", { silent: true }));

    await user.click(screen.getByRole("button", { name: /common.save/ }));

    await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1));
    const payload = api.patch.mock.calls[0][1];
    expect(payload.options).toEqual(
      expect.objectContaining({
        memory_bank_enabled: true,
        memory_bank_max_tokens: 4000,
        memory_search_enabled: false,
        browser_allow_eval: false,
        agent_loop: null,
      })
    );
    expect(payload.options).not.toHaveProperty("sync_enabled");
  });

  it("a 422 with fieldErrors lands in the tabs and clearFieldError prunes one key", async () => {
    const user = userEvent.setup();
    api.patch.mockRejectedValue(
      Object.assign(new Error("422"), {
        fieldErrors: { "options.rate_limit": "too big", "options.k": "too small" },
      })
    );
    await renderShell();

    await user.click(screen.getByRole("button", { name: /common.save/ }));

    await waitFor(() =>
      expect(screen.getByTestId("general-field-errors")).toHaveTextContent("too big")
    );
    expect(screen.getByTestId("general-field-errors")).toHaveTextContent("too small");
    expect(mockNavigate).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "clear-error" }));
    expect(screen.getByTestId("general-field-errors")).not.toHaveTextContent("too big");
    expect(screen.getByTestId("general-field-errors")).toHaveTextContent("too small");
  });

  // NOTE: these two use a fixture without `team`/`users`. With them present,
  // the async hydration effects (selectedUsers fill-in + /teams/{id} refetch)
  // setState AFTER the baseline snapshot, so the form reads as dirty right
  // after load — a real bug (cancel always prompts to discard). Reported, not
  // worked around in source.
  const CLEAN_PROJECT = { ...RAG_PROJECT, team: null, users: undefined };

  it("cancel with no changes navigates straight back without a dialog", async () => {
    const user = userEvent.setup();
    await renderShell(CLEAN_PROJECT);
    await user.click(screen.getByRole("button", { name: "common.cancel" }));
    expect(screen.queryByText("projects.unsavedChanges.title")).not.toBeInTheDocument();
    expect(mockNavigate).toHaveBeenCalledWith("/project/3");
  });

  it("dirty state stars the save button and gates cancel behind the discard dialog", async () => {
    const user = userEvent.setup();
    await renderShell(CLEAN_PROJECT);

    expect(screen.getByRole("button", { name: "common.save" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "mutate-name" }));
    expect(screen.getByRole("button", { name: "common.save*" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "common.cancel" }));
    expect(screen.getByText("projects.unsavedChanges.title")).toBeInTheDocument();
    expect(mockNavigate).not.toHaveBeenCalled();

    // keep editing → dialog closes, still on the page
    await user.click(screen.getByRole("button", { name: "common.keepEditing" }));
    await waitFor(() =>
      expect(screen.queryByText("projects.unsavedChanges.title")).not.toBeInTheDocument()
    );
    expect(mockNavigate).not.toHaveBeenCalled();

    // discard → navigates away
    await user.click(screen.getByRole("button", { name: "common.cancel" }));
    await user.click(screen.getByRole("button", { name: "common.discard" }));
    expect(mockNavigate).toHaveBeenCalledWith("/project/3");
  });

  it("changing team refetches the team and saves the new team_id", async () => {
    const user = userEvent.setup();
    await renderShell();

    await user.click(screen.getByRole("button", { name: "pick-team" }));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/teams/9", "tok"));

    await user.click(screen.getByRole("button", { name: /common.save/ }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1));
    expect(api.patch.mock.calls[0][1]).toEqual(expect.objectContaining({ team_id: 9 }));
  });
});
