import { render, screen, waitFor } from "@testing-library/react";
import ProjectEditView from "./Edit";
import api from "app/utils/api";

jest.mock("app/utils/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  delete: jest.fn(),
}));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

let mockParams;
jest.mock("react-router-dom", () => ({
  useParams: () => mockParams,
}));

// The shell has its own suite — stub it and capture the props it receives.
const mockEditProps = jest.fn();
jest.mock("./components/ProjectEdit", () => {
  const React = require("react");
  return function MockProjectEdit(props) {
    mockEditProps(props);
    return React.createElement("div", { "data-testid": "project-edit-shell" });
  };
});

const PROJECT = { id: 3, name: "docs", human_name: "Docs Bot", type: "rag" };
const INFO = { version: "1.0", llms: [{ name: "gpt4" }], embeddings: [], loaders: [] };

beforeEach(() => {
  jest.clearAllMocks();
  mockParams = { id: "3" };
  useAuth.mockReturnValue({ user: { token: "tok" } });
  api.get.mockImplementation((path) => {
    if (path === "/projects/3") return Promise.resolve(PROJECT);
    if (path === "/projects") return Promise.resolve({ projects: [PROJECT, { id: 4, name: "other" }] });
    if (path === "/info") return Promise.resolve(INFO);
    return Promise.resolve({});
  });
});

describe("projects/Edit view", () => {
  it("fetches project, project list, and info, then feeds them to the shell", async () => {
    render(<ProjectEditView />);

    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/projects/3", "tok"));
    expect(api.get).toHaveBeenCalledWith("/projects", "tok");
    expect(api.get).toHaveBeenCalledWith("/info", "tok");

    expect(screen.getByTestId("project-edit-shell")).toBeInTheDocument();
    await waitFor(() =>
      expect(mockEditProps).toHaveBeenLastCalledWith(
        expect.objectContaining({
          project: PROJECT,
          projects: [PROJECT, { id: 4, name: "other" }],
          info: INFO,
        })
      )
    );
  });

  it("renders the hero with the padded project id, display name, and type", async () => {
    render(<ProjectEditView />);
    expect(screen.getByText("PROJECT/0003")).toBeInTheDocument();
    expect(await screen.findByText("Docs Bot")).toBeInTheDocument();
    expect(await screen.findByText("rag")).toBeInTheDocument();
  });

  it("sets the document title from the route id", async () => {
    render(<ProjectEditView />);
    await waitFor(() =>
      expect(document.title).toContain("Edit Project - 3")
    );
  });
});
