import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EmbeddingNew from "./EmbeddingNew";
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
jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}));

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  api.post.mockResolvedValue({ id: 11 });
});

describe("EmbeddingNew (legacy manual form)", () => {
  it("renders the create form fields", () => {
    render(<EmbeddingNew />);
    expect(screen.getByText("embeddings.newCardTitle")).toBeInTheDocument();
    expect(screen.getByLabelText(/embeddings\.edit\.name/)).toBeInTheDocument();
    expect(screen.getByLabelText(/embeddings\.edit\.className/)).toBeInTheDocument();
    expect(screen.getAllByLabelText(/embeddings\.edit\.options/).length).toBeGreaterThan(0);
  });

  it("posts name/class/options/privacy/description on submit and navigates to the new embedding", async () => {
    const user = userEvent.setup();
    render(<EmbeddingNew />);

    await user.type(screen.getByLabelText(/embeddings\.edit\.name/), "my-emb");
    await user.type(screen.getByLabelText(/embeddings\.edit\.className/), "OllamaEmbedding");
    await user.type(
      screen.getByLabelText(/embeddings\.edit\.options/),
      '{{"model_name": "nomic-embed-text"}'
    );
    await user.type(screen.getByLabelText(/embeddings\.edit\.description/), "local encoder");

    await user.click(screen.getByRole("button", { name: "embeddings.submit" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    const [path, body, token] = api.post.mock.calls[0];
    expect(path).toBe("/embeddings");
    expect(token).toBe("tok");
    expect(body).toEqual(
      expect.objectContaining({
        name: "my-emb",
        class_name: "OllamaEmbedding",
        options: '{"model_name": "nomic-embed-text"}',
        description: "local encoder",
      })
    );
    expect(mockNavigate).toHaveBeenCalledWith("/embedding/11");
  });
});
