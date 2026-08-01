import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LLMs from "./List";
import api from "app/utils/api";
import { toast } from "react-toastify";

jest.mock("app/utils/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  delete: jest.fn(),
}));
jest.mock("react-toastify", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}));

// Kept to 2 rows — DataList renders fast, but small fixtures keep intent clear.
// Default sort is id desc, so row order is: claude (id 2), gpt4 (id 1).
const LLMS = [
  { id: 1, name: "gpt4", class_name: "OpenAI", privacy: "public", context_window: 128000, input_cost: 2.5, output_cost: 10 },
  { id: 2, name: "claude", class_name: "Anthropic", privacy: "private", context_window: 200000 },
];

let llmsResp;
let usageResp;

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  llmsResp = LLMS;
  usageResp = { count: 0, projects: [] };
  api.get.mockImplementation((path) => {
    if (path === "/llms") return Promise.resolve(llmsResp);
    if (/^\/llms\/\d+\/usage$/.test(path)) return Promise.resolve(usageResp);
    return Promise.resolve({});
  });
  api.delete.mockResolvedValue({});
  window.confirm = jest.fn(() => true);
});

const renderList = async () => {
  render(<LLMs />);
  // wait for the fetched rows to land
  await screen.findByText(llmsResp[0]?.name || "llms.emptyTitle");
};

// The delete icon for the top row (claude, id 2 — first because of id-desc sort).
const clickDeleteOnFirstRow = async (user) => {
  const buttons = await screen.findAllByRole("button", { name: "llms.actions.delete" });
  await user.click(buttons[0]);
};

describe("LLMs List", () => {
  it("fetches and renders the LLM rows", async () => {
    await renderList();
    expect(api.get).toHaveBeenCalledWith("/llms", "tok");
    expect(screen.getByText("gpt4")).toBeInTheDocument();
    expect(screen.getByText("claude")).toBeInTheDocument();
    expect(screen.getByText("LLM/0002")).toBeInTheDocument();
  });

  it("hides delete/edit actions from non-admins", async () => {
    useAuth.mockReturnValue({ user: { token: "tok", username: "joe", is_admin: false } });
    await renderList();
    expect(screen.queryByRole("button", { name: "llms.actions.delete" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "llms.actions.edit" })).not.toBeInTheDocument();
  });

  it("zero-usage delete: checks usage, confirms, deletes without reassign query", async () => {
    const user = userEvent.setup();
    await renderList();

    await clickDeleteOnFirstRow(user);

    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/llms/2/usage", "tok"));
    expect(window.confirm).toHaveBeenCalledWith("llms.info.deleteConfirm");
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/llms/2", "tok"));
    expect(toast.success).toHaveBeenCalledWith("llms.info.deleted");
    // no reassign dialog
    expect(screen.queryByText("llms.reassign.title")).not.toBeInTheDocument();
    // list refetched after delete
    await waitFor(() => {
      const listCalls = api.get.mock.calls.filter(([p]) => p === "/llms");
      expect(listCalls).toHaveLength(2);
    });
  });

  it("zero-usage delete aborted by confirm does nothing", async () => {
    window.confirm = jest.fn(() => false);
    const user = userEvent.setup();
    await renderList();

    await clickDeleteOnFirstRow(user);

    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/llms/2/usage", "tok"));
    expect(api.delete).not.toHaveBeenCalled();
  });

  it("non-zero usage opens the reassign dialog listing affected projects instead of confirm", async () => {
    usageResp = {
      count: 2,
      projects: [
        { id: 10, name: "proj-a", human_name: "Proj A", fields: ["llm"] },
        { id: 11, name: "proj-b", fields: ["rerank_llm"] },
      ],
    };
    const user = userEvent.setup();
    await renderList();

    await clickDeleteOnFirstRow(user);

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("llms.reassign.title")).toBeInTheDocument();
    // no plain confirm, no delete yet
    expect(window.confirm).not.toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();
    // affected projects listed (human_name preferred, name as fallback)
    expect(within(dialog).getByText("Proj A")).toBeInTheDocument();
    expect(within(dialog).getByText("proj-b")).toBeInTheDocument();
    expect(within(dialog).getByText("(llms.reassign.field_llm)")).toBeInTheDocument();
    expect(within(dialog).getByText("(llms.reassign.field_rerank_llm)")).toBeInTheDocument();
    // replacement pre-selected with the first other LLM
    expect(within(dialog).getByRole("combobox")).toHaveTextContent("gpt4");
    expect(within(dialog).getByRole("button", { name: "llms.reassign.confirm" })).toBeEnabled();
  });

  it("confirming the reassign dialog deletes with ?reassign_to=<target> and refetches", async () => {
    usageResp = { count: 1, projects: [{ id: 10, name: "proj-a", fields: ["llm"] }] };
    api.delete.mockResolvedValue({ reassigned: 1, reassigned_to: "gpt4" });
    const user = userEvent.setup();
    await renderList();

    await clickDeleteOnFirstRow(user);
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "llms.reassign.confirm" }));

    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith("/llms/2?reassign_to=gpt4", "tok")
    );
    expect(toast.success).toHaveBeenCalledWith("llms.reassign.done");
    await waitFor(() =>
      expect(screen.queryByText("llms.reassign.title")).not.toBeInTheDocument()
    );
    await waitFor(() => {
      const listCalls = api.get.mock.calls.filter(([p]) => p === "/llms");
      expect(listCalls).toHaveLength(2);
    });
  });

  it("cancel closes the reassign dialog without deleting", async () => {
    usageResp = { count: 1, projects: [{ id: 10, name: "proj-a", fields: ["llm"] }] };
    const user = userEvent.setup();
    await renderList();

    await clickDeleteOnFirstRow(user);
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "llms.reassign.cancel" }));

    await waitFor(() =>
      expect(screen.queryByText("llms.reassign.title")).not.toBeInTheDocument()
    );
    expect(api.delete).not.toHaveBeenCalled();
  });

  it("with no replacement LLM available the dialog blocks deletion", async () => {
    llmsResp = [LLMS[1]]; // only "claude" exists
    usageResp = { count: 1, projects: [{ id: 10, name: "proj-a", fields: ["llm"] }] };
    const user = userEvent.setup();
    await renderList();

    await clickDeleteOnFirstRow(user);

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("llms.reassign.noReplacement")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "llms.reassign.confirm" })).toBeDisabled();
    expect(api.delete).not.toHaveBeenCalled();
  });
});
