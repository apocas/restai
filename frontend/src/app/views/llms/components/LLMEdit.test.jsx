import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LLMEdit from "./LLMEdit";
import api from "app/utils/api";
import { toast } from "react-toastify";

jest.mock("app/utils/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  delete: jest.fn(),
}));
jest.mock("react-toastify", () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

// json-edit-react is a leaf editor widget — stub it out.
jest.mock("json-edit-react", () => ({ JsonEditor: () => null }));

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}));

const LLM = {
  id: 5,
  name: "gpt4",
  class_name: "OpenAI",
  privacy: "private",
  description: "desc",
  context_window: 128000,
  input_cost: 2.5,
  output_cost: 10,
  options: { model: "gpt-4o" },
};

const realLocation = window.location;
beforeAll(() => {
  delete window.location;
  window.location = { href: "" };
});
afterAll(() => {
  window.location = realLocation;
});

beforeEach(() => {
  jest.clearAllMocks();
  window.location.href = "";
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  api.patch.mockResolvedValue({});
});

describe("LLMEdit", () => {
  it("starts clean: no changes indicator and disabled save", () => {
    render(<LLMEdit llm={LLM} />);
    expect(screen.getByText("no changes")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "llms.edit.saveChanges" })).toBeDisabled();
    expect(screen.queryByText(/UNSAVED/)).not.toBeInTheDocument();
  });

  it("tracks dirty fields and enables save", async () => {
    const user = userEvent.setup();
    render(<LLMEdit llm={LLM} />);

    await user.type(screen.getByLabelText(/llms\.edit\.name/), "x");
    expect(screen.getByText("1 field changed · name")).toBeInTheDocument();
    expect(screen.getByText("UNSAVED · 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "llms.edit.saveChanges" })).toBeEnabled();
  });

  it("patches only the changed fields and redirects to the info page", async () => {
    const user = userEvent.setup();
    render(<LLMEdit llm={LLM} />);

    await user.type(screen.getByLabelText(/llms\.edit\.name/), "x");
    await user.click(screen.getByRole("button", { name: "llms.edit.saveChanges" }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith("/llms/5", { name: "gpt4x" }, "tok")
    );
    expect(toast.success).toHaveBeenCalled();
    await waitFor(() => expect(window.location.href).toBe("/admin/llm/5"));
  });

  it("parses context_window to an integer in the update payload", async () => {
    const user = userEvent.setup();
    render(<LLMEdit llm={LLM} />);

    const ctx = screen.getByLabelText(/llms\.edit\.contextWindow/);
    await user.clear(ctx);
    await user.type(ctx, "9000");
    await user.click(screen.getByRole("button", { name: "llms.edit.saveChanges" }));

    await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1));
    expect(api.patch.mock.calls[0][1]).toEqual({ context_window: 9000 });
  });

  it("shows the discover-models button for OpenAI-compatible classes and applies a picked model", async () => {
    const user = userEvent.setup();
    api.get.mockResolvedValue({ models: [{ id: "m1" }, { id: "m2" }] });
    render(<LLMEdit llm={LLM} />);

    const discover = screen.getByRole("button", { name: "llms.edit.listModels" });
    await user.click(discover);

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith("/tools/openai-compat/models/5", "tok")
    );
    expect(await screen.findByText("m1")).toBeInTheDocument();

    // Picking a chip writes options.model — which lands in the patch payload
    await user.click(screen.getByText("m2"));
    await user.click(screen.getByRole("button", { name: "llms.edit.saveChanges" }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1));
    expect(api.patch.mock.calls[0][1]).toEqual({ options: { model: "m2" } });
  });

  it("shows an error panel when the provider returns no models", async () => {
    const user = userEvent.setup();
    api.get.mockResolvedValue({ models: [] });
    render(<LLMEdit llm={LLM} />);

    await user.click(screen.getByRole("button", { name: "llms.edit.listModels" }));
    expect(
      await screen.findByText(/provider returned no models/)
    ).toBeInTheDocument();
  });

  it("hides the discover-models button for non-OpenAI-compatible classes", () => {
    render(<LLMEdit llm={{ ...LLM, class_name: "Anthropic" }} />);
    expect(
      screen.queryByRole("button", { name: "llms.edit.listModels" })
    ).not.toBeInTheDocument();
  });

  it("cost calculator shows the zero-cost hint when no rates are set", () => {
    render(<LLMEdit llm={{ ...LLM, input_cost: 0, output_cost: 0 }} />);
    expect(screen.getByText(/no cost set/)).toBeInTheDocument();
  });

  it("cost calculator estimates a 100K/50K sample from the per-1M rates", () => {
    render(<LLMEdit llm={LLM} />);
    // 2.5 * 0.1 + 10 * 0.05 = 0.75
    expect(screen.getByText("$0.7500")).toBeInTheDocument();
  });

  it("cancel navigates back to the list without saving", async () => {
    const user = userEvent.setup();
    render(<LLMEdit llm={LLM} />);
    await user.click(screen.getByRole("button", { name: "common.cancel" }));
    expect(mockNavigate).toHaveBeenCalledWith("/llms");
    expect(api.patch).not.toHaveBeenCalled();
  });
});
