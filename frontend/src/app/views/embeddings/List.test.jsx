import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Embeddings from "./List";
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

// Default sort is id desc, so row order is: bge (id 2), ada (id 1).
const EMBEDDINGS = [
  { id: 1, name: "ada", class_name: "OpenAIEmbedding", privacy: "public", dimension: 1536 },
  { id: 2, name: "bge", class_name: "HuggingFaceEmbedding", privacy: "private", dimension: 768 },
];

let embeddingsResp;

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  embeddingsResp = EMBEDDINGS;
  api.get.mockImplementation((path) => {
    if (path === "/embeddings") return Promise.resolve(embeddingsResp);
    return Promise.resolve({});
  });
  api.delete.mockResolvedValue({});
  window.confirm = jest.fn(() => true);
});

const renderList = async () => {
  render(<Embeddings />);
  await screen.findByText(embeddingsResp[0]?.name || "embeddings.emptyTitle");
};

describe("Embeddings List", () => {
  it("fetches and renders embedding rows with dimension pills", async () => {
    await renderList();
    expect(api.get).toHaveBeenCalledWith("/embeddings", "tok");
    expect(screen.getByText("ada")).toBeInTheDocument();
    expect(screen.getByText("bge")).toBeInTheDocument();
    expect(screen.getByText("EMBEDDING/0002")).toBeInTheDocument();
    expect(screen.getByText("1536-d")).toBeInTheDocument();
    expect(screen.getByText("768-d")).toBeInTheDocument();
  });

  it("also accepts an { embeddings: [...] } response shape", async () => {
    api.get.mockImplementation((path) =>
      path === "/embeddings"
        ? Promise.resolve({ embeddings: EMBEDDINGS })
        : Promise.resolve({})
    );
    render(<Embeddings />);
    expect(await screen.findByText("ada")).toBeInTheDocument();
  });

  it("hides edit/delete actions and the new button from non-admins", async () => {
    useAuth.mockReturnValue({ user: { token: "tok", username: "joe", is_admin: false } });
    await renderList();
    expect(screen.queryByRole("button", { name: "embeddings.actions.delete" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "embeddings.actions.edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "embeddings.newBreadcrumb" })).not.toBeInTheDocument();
  });

  it("deletes after confirm and refetches the list", async () => {
    const user = userEvent.setup();
    await renderList();

    const deletes = screen.getAllByRole("button", { name: "embeddings.actions.delete" });
    await user.click(deletes[0]); // top row = bge (id 2)

    expect(window.confirm).toHaveBeenCalledWith("embeddings.info.deleteConfirm");
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/embeddings/2", "tok"));
    expect(toast.success).toHaveBeenCalledWith("embeddings.info.deleted");
    await waitFor(() => {
      const listCalls = api.get.mock.calls.filter(([p]) => p === "/embeddings");
      expect(listCalls).toHaveLength(2);
    });
  });

  it("does nothing when the confirm dialog is dismissed", async () => {
    window.confirm = jest.fn(() => false);
    const user = userEvent.setup();
    await renderList();

    await user.click(screen.getAllByRole("button", { name: "embeddings.actions.delete" })[0]);
    expect(api.delete).not.toHaveBeenCalled();
  });

  it("new button navigates to the chooser", async () => {
    const user = userEvent.setup();
    await renderList();
    await user.click(screen.getByRole("button", { name: "embeddings.newBreadcrumb" }));
    expect(mockNavigate).toHaveBeenCalledWith("/embeddings/new");
  });
});
