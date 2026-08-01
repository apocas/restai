import { render, screen } from "@testing-library/react";
import EmbeddingEditView from "./Edit";
import api from "app/utils/api";

jest.mock("app/utils/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  delete: jest.fn(),
}));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

jest.mock("react-router-dom", () => ({
  useParams: () => ({ id: "4" }),
}));

jest.mock("./components/EmbeddingEdit", () => (props) => {
  const React = require("react");
  return React.createElement("div", { "data-testid": "embedding-edit-form" }, props.embedding.name);
});

const EMBEDDING = { id: 4, name: "ada", class_name: "OpenAIEmbedding", privacy: "public", dimension: 1536 };

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  api.get.mockResolvedValue(EMBEDDING);
});

describe("Embedding Edit view", () => {
  it("fetches the embedding by route id and renders the hero + edit form", async () => {
    render(<EmbeddingEditView />);
    expect(api.get).toHaveBeenCalledWith("/embeddings/4", "tok");

    expect(await screen.findByTestId("embedding-edit-form")).toHaveTextContent("ada");
    expect(screen.getByText("EMBEDDING/0004 · EDIT")).toBeInTheDocument();
    expect(screen.getByText("OpenAIEmbedding")).toBeInTheDocument();
    expect(screen.getByText("1536-d")).toBeInTheDocument();
  });

  it("does not mount the edit form until the embedding has loaded", async () => {
    let resolveFetch;
    api.get.mockReturnValue(new Promise((res) => (resolveFetch = res)));
    render(<EmbeddingEditView />);
    expect(screen.queryByTestId("embedding-edit-form")).not.toBeInTheDocument();

    resolveFetch(EMBEDDING);
    expect(await screen.findByTestId("embedding-edit-form")).toBeInTheDocument();
  });
});
