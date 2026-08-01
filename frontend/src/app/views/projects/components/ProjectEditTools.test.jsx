import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProjectEditTools from "./ProjectEditTools";
import api from "app/utils/api";
import { toast } from "react-toastify";

jest.setTimeout(20000);

jest.mock("app/utils/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  put: jest.fn(),
  delete: jest.fn(),
}));
jest.mock("react-toastify", () => ({
  toast: { success: jest.fn(), error: jest.fn(), warn: jest.fn() },
}));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

// CodeMirror is ESM-heavy — stub it with a plain textarea.
jest.mock("@uiw/react-codemirror", () => {
  const React = require("react");
  return function MockCodeMirror({ value, onChange }) {
    return React.createElement("textarea", {
      "data-testid": "codemirror",
      value: value || "",
      onChange: (e) => onChange && onChange(e.target.value),
    });
  };
});
jest.mock("@codemirror/lang-python", () => ({ python: () => [] }));
jest.mock("@codemirror/lang-json", () => ({ json: () => [] }));

const AGENT_PROJECT = { id: 3, name: "bot", type: "agent", team: { id: 7 } };

const TOOLS = [{ name: "calculator" }, { name: "search_knowledge" }, { name: "send_email" }];

const CUSTOM_TOOLS = [
  {
    id: 1,
    name: "fetch_weather",
    description: "Gets the weather",
    parameters: '{"city": "string"}',
    code: "print('hi')",
    enabled: true,
    created_at: "2026-07-01T10:00:00Z",
  },
];

const isStdioServer = (host) => !!host && !host.startsWith("http");

const makeProps = (overrides = {}) => ({
  state: { type: "agent", team: { id: 7 }, options: { tools: "calculator" } },
  setState: jest.fn(),
  handleChange: jest.fn(),
  project: AGENT_PROJECT,
  mcpServers: [],
  setMcpServers: jest.fn(),
  tools: TOOLS,
  handleAddMcpServer: jest.fn(),
  handleRemoveMcpServer: jest.fn(),
  handleMcpServerFieldChange: jest.fn(),
  handleProbeMcpServer: jest.fn(),
  handleMcpToolsChange: jest.fn(),
  handleAddGatewayServices: jest.fn(),
  isStdioServer,
  ...overrides,
});

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok" } });
  api.get.mockImplementation((path) => {
    if (path === "/projects") {
      return Promise.resolve({
        projects: [
          { id: 9, name: "kb", human_name: "Knowledge Base", type: "rag", team: { id: 7 } },
          { id: 10, name: "other-kb", type: "rag", team: { id: 99 } },
          { id: 11, name: "an-agent", type: "agent", team: { id: 7 } },
        ],
      });
    }
    if (path === "/projects/3/custom-tools") return Promise.resolve({ tools: CUSTOM_TOOLS });
    return Promise.resolve({});
  });
  api.patch.mockResolvedValue({ enabled: false });
  api.delete.mockResolvedValue({});
});

describe("ProjectEditTools", () => {
  it("selected builtin tools come from the CSV and picking another re-joins the CSV", async () => {
    const user = userEvent.setup();
    const props = makeProps();
    render(<ProjectEditTools {...props} />);

    expect(screen.getByText("calculator")).toBeInTheDocument();

    await user.click(screen.getByLabelText("nav.tools"));
    await user.click(await screen.findByRole("option", { name: "send_email" }));

    expect(props.setState).toHaveBeenCalledWith({
      ...props.state,
      options: { ...props.state.options, tools: "calculator,send_email" },
    });
  });

  it("agent-only fields (max iterations, agent mode, knowledge search) hidden for rag projects", async () => {
    const props = makeProps({
      project: { id: 5, name: "ragproj", type: "rag" },
      state: { type: "rag", options: {} },
    });
    render(<ProjectEditTools {...props} />);
    expect(screen.queryByLabelText("Max Iterations")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Agent Mode")).not.toBeInTheDocument();
    // rag → no /projects fetch for knowledge-search candidates, no custom tools
    expect(api.get).not.toHaveBeenCalled();
  });

  it("knowledge search picker lists only same-team rag projects", async () => {
    const user = userEvent.setup();
    render(<ProjectEditTools {...makeProps()} />);
    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/projects", "tok"));

    await user.click(screen.getByLabelText(/Knowledge Search/));
    const listbox = await screen.findByRole("listbox");
    const options = within(listbox).getAllByRole("option").map((o) => o.textContent);
    expect(options).toContain("Knowledge Base");
    expect(options).not.toContain("other-kb"); // different team
    expect(options).not.toContain("an-agent"); // not rag
  });

  it("warns when a knowledge-search project is picked but the tool is not enabled", async () => {
    const props = makeProps({
      state: { type: "agent", team: { id: 7 }, options: { tools: "calculator", search_knowledge_project: "kb" } },
    });
    render(<ProjectEditTools {...props} />);
    expect(await screen.findByText(/Add “search_knowledge” to the Tools field/)).toBeInTheDocument();

    const okProps = makeProps({
      state: { type: "agent", team: { id: 7 }, options: { tools: "calculator, search_knowledge", search_knowledge_project: "kb" } },
    });
    const { container } = render(<ProjectEditTools {...okProps} />);
    expect(within(container).queryByText(/Add “search_knowledge”/)).not.toBeInTheDocument();
  });

  it("max iterations edits write parsed ints into options", async () => {
    const props = makeProps();
    render(<ProjectEditTools {...props} />);
    const field = screen.getByLabelText("Max Iterations");
    expect(field).toHaveValue(10);

    const { fireEvent } = require("@testing-library/react");
    fireEvent.change(field, { target: { value: "25" } });
    expect(props.setState).toHaveBeenCalledWith({
      ...props.state,
      options: { ...props.state.options, max_iterations: 25 },
    });
  });

  it("MCP: add button delegates to handleAddMcpServer; empty host disables Check", async () => {
    const user = userEvent.setup();
    const props = makeProps({
      mcpServers: [{ host: "", tools: "", availableTools: [] }],
    });
    render(<ProjectEditTools {...props} />);

    expect(screen.getByRole("button", { name: "projects.edit.tools.mcpCheck" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Add MCP Server" }));
    expect(props.handleAddMcpServer).toHaveBeenCalled();
  });

  it("MCP: stdio host shows args/env fields, http host shows headers field", () => {
    const props = makeProps({
      mcpServers: [
        { host: "npx", args: ["-y", "server"], env: { PORT: "1" }, tools: "", availableTools: [] },
        { host: "http://localhost:3001/sse", headersText: "", tools: "", availableTools: [] },
      ],
    });
    render(<ProjectEditTools {...props} />);

    expect(screen.getByLabelText("projects.edit.tools.mcpArguments")).toHaveValue("-y server");
    expect(screen.getByLabelText("projects.edit.tools.mcpEnvVars")).toHaveValue("PORT=1");
    expect(screen.getByLabelText("projects.edit.tools.mcpHeaders")).toBeInTheDocument();
  });

  it("MCP: probe errors render with a Retry hook, and Check triggers the probe", async () => {
    const user = userEvent.setup();
    const props = makeProps({
      mcpServers: [{ host: "http://x/sse", error: "connection refused", tools: "", availableTools: [] }],
    });
    render(<ProjectEditTools {...props} />);

    expect(screen.getByText("connection refused")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(props.handleProbeMcpServer).toHaveBeenCalledWith(0);

    await user.click(screen.getByRole("button", { name: "projects.edit.tools.mcpCheck" }));
    expect(props.handleProbeMcpServer).toHaveBeenCalledTimes(2);
  });

  it("agent-created tools: fetches, renders the accordion, and toggles enabled via PATCH", async () => {
    const user = userEvent.setup();
    render(<ProjectEditTools {...makeProps()} />);

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith("/projects/3/custom-tools", "tok")
    );
    expect(await screen.findByText("fetch_weather")).toBeInTheDocument();
    expect(screen.getByText("Agent-Created Tools")).toBeInTheDocument();

    await user.click(screen.getByText("Enabled"));
    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith("/projects/3/custom-tools/fetch_weather", {}, "tok")
    );
    expect(toast.success).toHaveBeenCalledWith('Tool "fetch_weather" disabled');
  });

  it("agent-created tools: delete is confirm-gated", async () => {
    const user = userEvent.setup();
    const confirmSpy = jest.spyOn(window, "confirm").mockReturnValue(true);
    render(<ProjectEditTools {...makeProps()} />);
    await screen.findByText("fetch_weather");

    // expand the accordion to reach the delete button
    await user.click(screen.getByText("fetch_weather"));
    await user.click(await screen.findByRole("button", { name: /Delete/ }));

    expect(confirmSpy).toHaveBeenCalled();
    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith("/projects/3/custom-tools/fetch_weather", "tok")
    );
    expect(toast.success).toHaveBeenCalledWith('Tool "fetch_weather" deleted');
    confirmSpy.mockRestore();
  });

  it("agent-created tools section hides entirely when the project has none", async () => {
    api.get.mockImplementation((path) => {
      if (path === "/projects") return Promise.resolve({ projects: [] });
      if (path === "/projects/3/custom-tools") return Promise.resolve({ tools: [] });
      return Promise.resolve({});
    });
    render(<ProjectEditTools {...makeProps()} />);
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith("/projects/3/custom-tools", "tok")
    );
    await waitFor(() =>
      expect(screen.queryByText("Agent-Created Tools")).not.toBeInTheDocument()
    );
  });
});
