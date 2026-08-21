import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProjectInfoTools from "./ProjectInfoTools";
import api from "app/utils/api";

jest.setTimeout(20000);

jest.mock("app/utils/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  put: jest.fn(),
  delete: jest.fn(),
}));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

// CodeMirror is ESM-heavy — stub it (pulled in via ProjectEditTools).
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

const PROJECT = {
  id: 3,
  name: "bot",
  type: "agent",
  llm: "gpt-main",
  team: { id: 7 },
  options: {
    tools: "calculator",
    max_iterations: 10,
    agent_mode: "auto",
    // Pre-existing stored values the save must preserve/overwrite correctly.
    fallback_llm: null,
    tool_timeout: 300,
    max_execution_time: 0,
    memory_bank_enabled: true, // unrelated key that must survive the merge
  },
};

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok" } });
  api.get.mockImplementation((path) => {
    if (path === "/tools/agent") return Promise.resolve([{ name: "calculator" }]);
    if (path === "/projects/3") return Promise.resolve(PROJECT);
    if (path === "/projects") return Promise.resolve({ projects: [] });
    if (path === "/projects/3/custom-tools") return Promise.resolve({ tools: [] });
    if (path === "/llms") {
      return Promise.resolve({ llms: [{ name: "gpt-main" }, { name: "backup-llm" }] });
    }
    return Promise.resolve({});
  });
  api.patch.mockResolvedValue({});
});

describe("ProjectInfoTools save", () => {
  it("persists tool_timeout and max_execution_time edits (regression: whitelist drop)", async () => {
    const user = userEvent.setup();
    render(<ProjectInfoTools project={PROJECT} />);

    const timeField = await screen.findByLabelText("Max Execution Time (seconds)");
    fireEvent.change(timeField, { target: { value: "600" } });
    const toolField = screen.getByLabelText("Tool Timeout (seconds)");
    fireEvent.change(toolField, { target: { value: "120" } });

    await user.click(screen.getByRole("button", { name: /Save/i }));

    await waitFor(() => expect(api.patch).toHaveBeenCalled());
    const [url, body] = api.patch.mock.calls[0];
    expect(url).toBe("/projects/3");
    expect(body.options.max_execution_time).toBe(600);
    expect(body.options.tool_timeout).toBe(120);
    // Untouched keys ride along unchanged.
    expect(body.options.memory_bank_enabled).toBe(true);
    expect(body.options.max_iterations).toBe(10);
  });

  it("persists fallback_llm picks", async () => {
    const user = userEvent.setup();
    render(<ProjectInfoTools project={PROJECT} />);

    await user.click(await screen.findByLabelText("Fallback LLMs"));
    await user.click(await screen.findByRole("option", { name: "backup-llm" }));
    await user.click(screen.getByRole("button", { name: /Save/i }));

    await waitFor(() => expect(api.patch).toHaveBeenCalled());
    const [, body] = api.patch.mock.calls[0];
    expect(body.options.fallback_llm).toBe("backup-llm");
  });
});
