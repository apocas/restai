import { render, screen } from "@testing-library/react";
import EmbeddingViewInfo from "./Info";
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
  useParams: () => ({ id: "6" }),
}));

let capturedProps;
jest.mock("./components/EmbeddingInfo", () => (props) => {
  const React = require("react");
  capturedProps = props;
  return React.createElement("div", { "data-testid": "embedding-info" }, props.embedding.name);
});

const EMBEDDING = { id: 6, name: "bge", class_name: "HuggingFaceEmbedding", privacy: "private", dimension: 768 };
const PROJECTS = {
  projects: [
    { id: 1, name: "a", embeddings: "bge" },
    { id: 2, name: "b", embeddings: "other" },
  ],
};

beforeEach(() => {
  jest.clearAllMocks();
  capturedProps = undefined;
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  api.get.mockImplementation((path) => {
    if (path === "/embeddings/6") return Promise.resolve(EMBEDDING);
    if (path === "/projects") return Promise.resolve(PROJECTS);
    if (path === "/info") return Promise.resolve({ version: "1.0", embeddings: [], llms: [], loaders: [] });
    return Promise.resolve({});
  });
});

describe("Embedding Info view", () => {
  it("fetches embedding, projects and platform info", async () => {
    render(<EmbeddingViewInfo />);
    expect(await screen.findByTestId("embedding-info")).toHaveTextContent("bge");
    expect(api.get).toHaveBeenCalledWith("/embeddings/6", "tok");
    expect(api.get).toHaveBeenCalledWith("/projects", "tok");
    expect(api.get).toHaveBeenCalledWith("/info", "tok");
  });

  it("computes usedBy from projects referencing the embedding and shows the stats", async () => {
    render(<EmbeddingViewInfo />);
    await screen.findByTestId("embedding-info");
    expect(capturedProps.usedBy).toBe(1);
    expect(screen.getByText("1 project")).toBeInTheDocument();
    expect(screen.getByText("EMBEDDING/0006")).toBeInTheDocument();
    expect(screen.getByText("768-d")).toBeInTheDocument();
  });
});
