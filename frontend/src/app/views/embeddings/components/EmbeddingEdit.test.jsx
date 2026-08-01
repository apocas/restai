import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EmbeddingEdit from "./EmbeddingEdit";
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

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}));

const EMBEDDING = {
  id: 3,
  name: "ada",
  class_name: "OpenAIEmbedding",
  privacy: "private",
  description: "",
  dimension: 1536,
  options: '{"model":"text-embedding-3-small"}',
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

describe("EmbeddingEdit", () => {
  it("starts clean with save disabled and a VALID JSON badge", () => {
    render(<EmbeddingEdit embedding={EMBEDDING} />);
    expect(screen.getByText("no changes")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "embeddings.edit.saveChanges" })).toBeDisabled();
    expect(screen.getByText("VALID JSON")).toBeInTheDocument();
  });

  it("patches only the changed fields and redirects to the info page", async () => {
    const user = userEvent.setup();
    render(<EmbeddingEdit embedding={EMBEDDING} />);

    await user.type(screen.getByLabelText(/embeddings\.edit\.name/), "x");
    expect(screen.getByText("UNSAVED")).toBeInTheDocument();
    expect(screen.getByText("1 field(s) changed")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "embeddings.edit.saveChanges" }));
    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith("/embeddings/3", { name: "adax" }, "tok")
    );
    expect(toast.success).toHaveBeenCalled();
    await waitFor(() => expect(window.location.href).toBe("/admin/embedding/3"));
  });

  it("flags invalid options JSON and repairs formatting via the Format button", async () => {
    const user = userEvent.setup();
    render(<EmbeddingEdit embedding={{ ...EMBEDDING, options: "{ not json" }} />);

    expect(screen.getByText("INVALID JSON")).toBeInTheDocument();
    expect(screen.getByText(/Options is not valid JSON/)).toBeInTheDocument();

    // Format leaves invalid input untouched
    await user.click(screen.getByRole("button", { name: /Format/ }));
    expect(screen.getByText("INVALID JSON")).toBeInTheDocument();
  });

  it("Format pretty-prints valid JSON in place", async () => {
    const user = userEvent.setup();
    render(<EmbeddingEdit embedding={EMBEDDING} />);

    await user.click(screen.getByRole("button", { name: /Format/ }));
    expect(screen.getByDisplayValue(/"model": "text-embedding-3-small"/)).toBeInTheDocument();
  });

  it("uses a free-form class field when the stored class is not in the curated list", () => {
    render(<EmbeddingEdit embedding={{ ...EMBEDDING, class_name: "MyCustomEmbedding" }} />);
    // Free-form mode: a plain textbox holding the custom class
    expect(screen.getByDisplayValue("MyCustomEmbedding")).toBeInTheDocument();
    expect(screen.getByText(/pick from list/)).toBeInTheDocument();
  });

  it("cancel navigates back to the list without saving", async () => {
    const user = userEvent.setup();
    render(<EmbeddingEdit embedding={EMBEDDING} />);
    await user.click(screen.getByRole("button", { name: "common.cancel" }));
    expect(mockNavigate).toHaveBeenCalledWith("/embeddings");
    expect(api.patch).not.toHaveBeenCalled();
  });
});
