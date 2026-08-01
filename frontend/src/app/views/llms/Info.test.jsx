import { render, screen } from "@testing-library/react";
import LLMViewInfo from "./Info";
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
  useParams: () => ({ id: "3" }),
}));

let capturedProps;
jest.mock("./components/LLMInfo", () => (props) => {
  const React = require("react");
  capturedProps = props;
  return React.createElement("div", { "data-testid": "llm-info" }, props.llm.name);
});

const LLM = { id: 3, name: "claude", class_name: "Anthropic", privacy: "private", context_window: 200000 };
const PROJECTS = {
  projects: [
    { id: 1, name: "a", llm: "claude" },
    { id: 2, name: "b", llm: "claude" },
    { id: 3, name: "c", llm: "other" },
  ],
};
const INFO = { version: "1.0", embeddings: [], llms: [], loaders: [] };

beforeEach(() => {
  jest.clearAllMocks();
  capturedProps = undefined;
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  api.get.mockImplementation((path) => {
    if (path === "/llms/3") return Promise.resolve(LLM);
    if (path === "/projects") return Promise.resolve(PROJECTS);
    if (path === "/info") return Promise.resolve(INFO);
    return Promise.resolve({});
  });
});

describe("LLM Info view", () => {
  it("fetches llm, projects and platform info", async () => {
    render(<LLMViewInfo />);
    expect(await screen.findByTestId("llm-info")).toHaveTextContent("claude");
    expect(api.get).toHaveBeenCalledWith("/llms/3", "tok");
    expect(api.get).toHaveBeenCalledWith("/projects", "tok");
    expect(api.get).toHaveBeenCalledWith("/info", "tok");
  });

  it("computes usedBy from projects referencing the llm by name and shows the stat", async () => {
    render(<LLMViewInfo />);
    await screen.findByTestId("llm-info");
    expect(capturedProps.usedBy).toBe(2);
    expect(capturedProps.projects).toEqual(PROJECTS.projects);
    expect(capturedProps.info).toEqual(INFO);
    expect(screen.getByText("2 projects")).toBeInTheDocument();
    // Hero identity + provider + context stats
    expect(screen.getByText("LLM/0003")).toBeInTheDocument();
    expect(screen.getByText("Anthropic")).toBeInTheDocument();
    expect(screen.getByText("200K ctx")).toBeInTheDocument();
  });
});
