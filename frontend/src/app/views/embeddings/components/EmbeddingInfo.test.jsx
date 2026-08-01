import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EmbeddingInfo from "./EmbeddingInfo";
import api from "app/utils/api";
import { toast } from "react-toastify";

jest.mock("app/utils/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  delete: jest.fn(),
}));
jest.mock("react-toastify", () => ({
  toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() },
}));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}));

// ESM-only leaf widgets — stub them out.
jest.mock("react-qr-code", () => (props) =>
  require("react").createElement("div", {
    "data-testid": "qr",
    "data-value": props.value,
  })
);
jest.mock("@microlink/react-json-view", () => (props) =>
  require("react").createElement(
    "pre",
    { "data-testid": "json-view" },
    JSON.stringify(props.src)
  )
);

const EMBEDDING = {
  id: 3,
  name: "minilm",
  class_name: "HuggingFaceEmbedding",
  privacy: "private",
  description: "Small sentence encoder",
  dimension: 384,
  options: '{"model_name":"all-MiniLM-L6-v2"}',
};

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  api.delete.mockResolvedValue({});
  window.confirm = jest.fn(() => true);
});

describe("EmbeddingInfo identity and stats", () => {
  it("renders name, padded id ref, class and privacy", () => {
    render(<EmbeddingInfo embedding={EMBEDDING} usedBy={0} />);
    expect(screen.getByText("minilm")).toBeInTheDocument();
    expect(screen.getByText("EMBEDDING/0003")).toBeInTheDocument();
    // Class appears in the stat tile and the config row pill.
    expect(screen.getAllByText("HuggingFaceEmbedding").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("PRIVATE").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("manually shared")).toBeInTheDocument();
  });

  it("shows the dimension stat and -d pill", () => {
    render(<EmbeddingInfo embedding={EMBEDDING} usedBy={0} />);
    expect(screen.getByText("384")).toBeInTheDocument();
    expect(screen.getByText("384-d")).toBeInTheDocument();
    expect(screen.getByText("vectors per token")).toBeInTheDocument();
  });

  it("falls back to auto-detected when no dimension is set", () => {
    render(<EmbeddingInfo embedding={{ ...EMBEDDING, dimension: null }} usedBy={0} />);
    expect(screen.getByText("auto-detected")).toBeInTheDocument();
    expect(screen.queryByText(/-d$/)).not.toBeInTheDocument();
  });

  it("public embeddings get the green pill and subtitle", () => {
    render(<EmbeddingInfo embedding={{ ...EMBEDDING, privacy: "public" }} usedBy={0} />);
    expect(screen.getAllByText("PUBLIC").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("any team can attach")).toBeInTheDocument();
  });

  it("shows the used-by count with singular/plural subtitle", () => {
    const { rerender } = render(<EmbeddingInfo embedding={EMBEDDING} usedBy={1} />);
    expect(screen.getByText("project")).toBeInTheDocument();
    rerender(<EmbeddingInfo embedding={EMBEDDING} usedBy={4} />);
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("projects")).toBeInTheDocument();
  });

  it("renders the description text", () => {
    render(<EmbeddingInfo embedding={EMBEDDING} usedBy={0} />);
    expect(screen.getByText("Small sentence encoder")).toBeInTheDocument();
  });
});

describe("EmbeddingInfo options", () => {
  it("parses stringified JSON options into the viewer with a key count", () => {
    render(<EmbeddingInfo embedding={EMBEDDING} usedBy={0} />);
    expect(screen.getByText("1 key")).toBeInTheDocument();
    expect(screen.getByTestId("json-view")).toHaveTextContent('"model_name":"all-MiniLM-L6-v2"');
  });

  it("hides the options card when options are missing or invalid JSON", () => {
    const { rerender } = render(
      <EmbeddingInfo embedding={{ ...EMBEDDING, options: null }} usedBy={0} />
    );
    expect(screen.queryByTestId("json-view")).not.toBeInTheDocument();
    rerender(<EmbeddingInfo embedding={{ ...EMBEDDING, options: "{{nope" }} usedBy={0} />);
    expect(screen.queryByTestId("json-view")).not.toBeInTheDocument();
  });
});

describe("EmbeddingInfo used-by list", () => {
  const projects = [
    { id: 1, name: "alpha", embeddings: "minilm" },
    { id: 2, name: "beta", embeddings: "other" },
  ];

  it("lists only the projects using this embedding", () => {
    render(<EmbeddingInfo embedding={EMBEDDING} projects={projects} usedBy={1} />);
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.queryByText("beta")).not.toBeInTheDocument();
    expect(screen.getByText("1 attached")).toBeInTheDocument();
  });

  it("navigates to the project when a chip is clicked", async () => {
    const user = userEvent.setup();
    render(<EmbeddingInfo embedding={EMBEDDING} projects={projects} usedBy={1} />);
    await user.click(screen.getByText("alpha"));
    expect(mockNavigate).toHaveBeenCalledWith("/project/1");
  });

  it("omits the section when nothing uses the embedding", () => {
    render(<EmbeddingInfo embedding={EMBEDDING} projects={[]} usedBy={0} />);
    expect(screen.queryByText(/attached/)).not.toBeInTheDocument();
  });
});

describe("EmbeddingInfo actions", () => {
  it("toggles the QR code with the current page URL as value", async () => {
    const user = userEvent.setup();
    render(<EmbeddingInfo embedding={EMBEDDING} usedBy={0} />);
    expect(screen.queryByTestId("qr")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("QrCode2Icon").closest("button"));
    expect(screen.getByTestId("qr")).toHaveAttribute("data-value", window.location.href);

    await user.click(screen.getByTestId("QrCode2Icon").closest("button"));
    expect(screen.queryByTestId("qr")).not.toBeInTheDocument();
  });

  it("copies the embedding name to the clipboard and toasts", async () => {
    // userEvent.setup() installs its own clipboard stub — spy on that.
    const user = userEvent.setup();
    render(<EmbeddingInfo embedding={EMBEDDING} usedBy={0} />);
    const writeSpy = jest.spyOn(navigator.clipboard, "writeText");
    await user.click(screen.getByTestId("ContentCopyIcon").closest("button"));
    expect(writeSpy).toHaveBeenCalledWith("minilm");
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it("edit navigates to the edit page", async () => {
    const user = userEvent.setup();
    render(<EmbeddingInfo embedding={EMBEDDING} usedBy={0} />);
    await user.click(screen.getByRole("button", { name: "common.edit" }));
    expect(mockNavigate).toHaveBeenCalledWith("/embedding/3/edit");
  });

  it("delete confirms, calls the API by id and navigates back to the list", async () => {
    const user = userEvent.setup();
    render(<EmbeddingInfo embedding={EMBEDDING} usedBy={0} />);
    await user.click(screen.getByRole("button", { name: "common.delete" }));
    expect(window.confirm).toHaveBeenCalledWith("embeddings.info.confirmDelete");
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/embeddings/3", "tok"));
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/embeddings"));
  });

  it("delete aborted by confirm does not call the API", async () => {
    window.confirm = jest.fn(() => false);
    const user = userEvent.setup();
    render(<EmbeddingInfo embedding={EMBEDDING} usedBy={0} />);
    await user.click(screen.getByRole("button", { name: "common.delete" }));
    expect(api.delete).not.toHaveBeenCalled();
  });

  it("hides edit and delete from non-admins", () => {
    useAuth.mockReturnValue({ user: { token: "tok", username: "bob", is_admin: false } });
    render(<EmbeddingInfo embedding={EMBEDDING} usedBy={0} />);
    expect(screen.queryByRole("button", { name: "common.edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "common.delete" })).not.toBeInTheDocument();
  });
});
