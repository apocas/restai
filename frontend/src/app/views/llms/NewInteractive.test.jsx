import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import NewInteractive from "./NewInteractive";
import api from "app/utils/api";
import { toast } from "react-toastify";
import { PROVIDER_CONFIG } from "./providerConfig";

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

// ESM-ish leaf dep — stub the raw JSON tree viewer.
jest.mock("@microlink/react-json-view", () => ({
  __esModule: true,
  default: () => null,
}));

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
  NavLink: ({ children, to }) => {
    const React = require("react");
    return React.createElement("a", { href: to }, children);
  },
}));

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  api.post.mockResolvedValue({ id: 42 });
});

describe("LLMs NewInteractive", () => {
  it("phase 1 lists every provider from PROVIDER_CONFIG", () => {
    render(<NewInteractive />);
    Object.entries(PROVIDER_CONFIG).forEach(([key, cfg]) => {
      // Some labels double as the class_name caption (e.g. Ollama)
      expect(screen.getAllByText(cfg.label).length).toBeGreaterThanOrEqual(1);
    });
    // class_name keys shown as monospace captions
    expect(screen.getByText("AzureOpenAI")).toBeInTheDocument();
  });

  it("search filters provider tiles and shows an empty message on no match", async () => {
    const user = userEvent.setup();
    render(<NewInteractive />);
    const search = screen.getByPlaceholderText("llms.interactive.searchPlaceholder");

    await user.type(search, "anthropic");
    // label + class_name caption both read "Anthropic"
    expect(screen.getAllByText("Anthropic").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("Ollama")).not.toBeInTheDocument();

    await user.clear(search);
    await user.type(search, "zzz-no-such");
    expect(screen.getByText("llms.interactive.noProviders")).toBeInTheDocument();
  });

  it("selecting a provider shows its config form with a password field for the API key", async () => {
    const user = userEvent.setup();
    render(<NewInteractive />);
    await user.click(screen.getByText(/GPT-4o, GPT-4o Mini/));

    // Phase 2 — provider chip + general fields
    expect(screen.getByText("llms.interactive.newX")).toBeInTheDocument();
    expect(screen.getByLabelText(/llms\.interactive\.name/)).toBeInTheDocument();

    // Provider fields from PROVIDER_CONFIG.OpenAI
    const model = screen.getByLabelText(/^Model/);
    expect(model).toBeRequired();
    // API key is a password input — never a plain text field
    const key = screen.getByLabelText(/API Key/);
    expect(key).toHaveAttribute("type", "password");
    // Temperature default (0) is applied
    expect(screen.getByLabelText(/Temperature/)).toHaveValue(0);
  });

  it("blocks submit and toasts when the name is empty", async () => {
    const user = userEvent.setup();
    render(<NewInteractive />);
    await user.click(screen.getByText(/GPT-4o, GPT-4o Mini/));

    await user.click(screen.getByRole("button", { name: "llms.interactive.createLlm" }));
    expect(toast.error).toHaveBeenCalledWith("llms.interactive.nameRequired");
    expect(api.post).not.toHaveBeenCalled();
  });

  it("posts the create payload with class_name, stringified options and context window", async () => {
    const user = userEvent.setup();
    render(<NewInteractive />);
    await user.click(screen.getByText(/GPT-4o, GPT-4o Mini/));

    await user.type(screen.getByLabelText(/llms\.interactive\.name/), "my-gpt");
    await user.type(screen.getByLabelText(/^Model/), "gpt-4o");
    await user.type(screen.getByLabelText(/API Key/), "sk-test");
    const ctx = screen.getByLabelText(/llms\.interactive\.contextWindow/);
    await user.clear(ctx);
    await user.type(ctx, "128000");

    await user.click(screen.getByRole("button", { name: "llms.interactive.createLlm" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    const [path, body, token] = api.post.mock.calls[0];
    expect(path).toBe("/llms");
    expect(token).toBe("tok");
    expect(body.name).toBe("my-gpt");
    expect(body.class_name).toBe("OpenAI");
    expect(body.privacy).toBe("private");
    expect(body.context_window).toBe(128000);
    // options serialized as a JSON string, empty values pruned
    expect(JSON.parse(body.options)).toEqual({
      temperature: 0,
      model: "gpt-4o",
      api_key: "sk-test",
    });
    expect(mockNavigate).toHaveBeenCalledWith("/llm/42");
  });

  it("renders boolean provider fields as a switch with its default applied (OpenAILike)", async () => {
    const user = userEvent.setup();
    render(<NewInteractive />);
    await user.click(screen.getByText("OpenAI-Compatible"));

    const switchEl = screen.getByRole("checkbox", { name: "Is Chat Model" });
    expect(switchEl).toBeChecked();

    await user.type(screen.getByLabelText(/llms\.interactive\.name/), "compat");
    await user.type(screen.getByLabelText(/^Model/), "m1");
    await user.type(screen.getByLabelText(/API Base URL/), "https://api.example.com/v1");
    await user.click(switchEl);

    await user.click(screen.getByRole("button", { name: "llms.interactive.createLlm" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    const body = api.post.mock.calls[0][1];
    expect(body.class_name).toBe("OpenAILike");
    // false survives the empty-value pruning
    expect(JSON.parse(body.options)).toEqual({
      temperature: 0,
      is_chat_model: false,
      model: "m1",
      api_base: "https://api.example.com/v1",
    });
  });

  it("back button returns to provider selection and resets the form", async () => {
    const user = userEvent.setup();
    render(<NewInteractive />);
    await user.click(screen.getByText(/GPT-4o, GPT-4o Mini/));
    await user.type(screen.getByLabelText(/llms\.interactive\.name/), "throwaway");

    await user.click(screen.getByRole("button", { name: "common.cancel" }));
    // Back at phase 1
    expect(screen.getByText("llms.interactive.title")).toBeInTheDocument();

    // Re-entering shows a clean form
    await user.click(screen.getByText(/GPT-4o, GPT-4o Mini/));
    expect(screen.getByLabelText(/llms\.interactive\.name/)).toHaveValue("");
  });
});
