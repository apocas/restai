import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import NewInteractive from "./NewInteractive";
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
  api.post.mockResolvedValue({ id: 9 });
});

describe("Embeddings NewInteractive", () => {
  it("lists the embedding providers with class keys", () => {
    render(<NewInteractive />);
    expect(screen.getByText("OpenAI Embeddings")).toBeInTheDocument();
    expect(screen.getByText("HuggingFace Embeddings")).toBeInTheDocument();
    expect(screen.getByText("Ollama Embeddings")).toBeInTheDocument();
    // class_name key captions, including the dotted one
    expect(screen.getByText("LangChain.HuggingFace")).toBeInTheDocument();
  });

  it("selecting a provider applies its default dimension", async () => {
    const user = userEvent.setup();
    render(<NewInteractive />);
    await user.click(screen.getByText("Ollama Embeddings"));

    expect(screen.getByLabelText(/embeddings\.interactive\.dimension/)).toHaveValue(1024);
    // Provider fields
    expect(screen.getByLabelText(/Model Name/)).toBeRequired();
  });

  it("blocks submit and toasts when the name is empty", async () => {
    const user = userEvent.setup();
    render(<NewInteractive />);
    await user.click(screen.getByText("OpenAI Embeddings"));

    await user.click(screen.getByRole("button", { name: "embeddings.interactive.createEmbedding" }));
    expect(toast.error).toHaveBeenCalledWith("embeddings.interactive.nameRequired");
    expect(api.post).not.toHaveBeenCalled();
  });

  it("posts the create payload with stringified options, numeric dimension and a password api key field", async () => {
    const user = userEvent.setup();
    render(<NewInteractive />);
    await user.click(screen.getByText("OpenAI Embeddings"));

    // API key is a password input
    const key = screen.getByLabelText(/API Key/);
    expect(key).toHaveAttribute("type", "password");

    await user.type(screen.getByLabelText(/embeddings\.interactive\.name/), "my-emb");
    await user.type(screen.getByLabelText(/^Model/), "text-embedding-3-small");
    await user.type(key, "sk-secret");

    await user.click(screen.getByRole("button", { name: "embeddings.interactive.createEmbedding" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    const [path, body, token] = api.post.mock.calls[0];
    expect(path).toBe("/embeddings");
    expect(token).toBe("tok");
    expect(body.name).toBe("my-emb");
    expect(body.class_name).toBe("LangChain");
    expect(body.privacy).toBe("private");
    expect(body.dimension).toBe(1536);
    expect(JSON.parse(body.options)).toEqual({
      model: "text-embedding-3-small",
      api_key: "sk-secret",
    });
    expect(mockNavigate).toHaveBeenCalledWith("/embedding/9");
  });

  it("back button resets to provider selection", async () => {
    const user = userEvent.setup();
    render(<NewInteractive />);
    await user.click(screen.getByText("Ollama Embeddings"));
    await user.click(screen.getByRole("button", { name: "common.cancel" }));
    expect(screen.getByText("embeddings.interactive.title")).toBeInTheDocument();
  });
});
