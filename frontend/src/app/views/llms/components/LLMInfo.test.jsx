import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LLMInfo from "./LLMInfo";
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

const LLM = {
  id: 5,
  name: "gpt4",
  class_name: "OpenAI",
  privacy: "public",
  description: "General purpose model",
  context_window: 128000,
  input_cost: 2.5,
  output_cost: 10,
  options: { model: "gpt-4o", temperature: 0.1 },
};

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  api.delete.mockResolvedValue({});
  window.confirm = jest.fn(() => true);
});

describe("LLMInfo identity and stats", () => {
  it("renders name, padded id ref and provider metadata", () => {
    render(<LLMInfo llm={LLM} usedBy={0} />);
    expect(screen.getByText("gpt4")).toBeInTheDocument();
    expect(screen.getByText("LLM/0005")).toBeInTheDocument();
    // Provider short name appears in the stat tile, identity pill and config row.
    expect(screen.getAllByText("OpenAI").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("PUBLIC")).toBeInTheDocument();
  });

  it("formats the context window (128K stat + localised token pill)", () => {
    render(<LLMInfo llm={LLM} usedBy={0} />);
    // "128K" shows in the stat tile AND on the context-scale legend.
    expect(screen.getAllByText("128K").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("128,000 llms.info.tokens")).toBeInTheDocument();
  });

  it("falls back to the default 4K context when none is set", () => {
    render(<LLMInfo llm={{ ...LLM, context_window: null }} usedBy={0} />);
    expect(screen.getByText("default 4K")).toBeInTheDocument();
    expect(screen.getByText("4,096 llms.info.tokens")).toBeInTheDocument();
  });

  it("shows the per-1M cost pair in the stat tile and per-direction rows", () => {
    render(<LLMInfo llm={LLM} usedBy={0} />);
    expect(screen.getByText("$2.50/$10.00")).toBeInTheDocument();
    expect(screen.getByText("$2.50")).toBeInTheDocument();
    expect(screen.getByText("$10.00")).toBeInTheDocument();
  });

  it("renders zero-cost models as free", () => {
    render(<LLMInfo llm={{ ...LLM, input_cost: 0, output_cost: null }} usedBy={0} />);
    // Stat tile + input row + output row
    expect(screen.getAllByText("free")).toHaveLength(3);
  });

  it("shows the used-by count with singular/plural subtitle", () => {
    const { rerender } = render(<LLMInfo llm={LLM} usedBy={1} />);
    expect(screen.getByText("project")).toBeInTheDocument();
    rerender(<LLMInfo llm={LLM} usedBy={3} />);
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("projects")).toBeInTheDocument();
  });

  it("marks private models with an amber PRIVATE pill", () => {
    render(<LLMInfo llm={{ ...LLM, privacy: "private" }} usedBy={0} />);
    expect(screen.getByText("PRIVATE")).toBeInTheDocument();
  });

  it("renders the description, or an em-dash placeholder when empty", () => {
    const { rerender } = render(<LLMInfo llm={LLM} usedBy={0} />);
    expect(screen.getByText("General purpose model")).toBeInTheDocument();
    rerender(<LLMInfo llm={{ ...LLM, description: "" }} usedBy={0} />);
    expect(screen.queryByText("General purpose model")).not.toBeInTheDocument();
  });
});

describe("LLMInfo options", () => {
  it("renders object options through the JSON viewer with a key count", () => {
    render(<LLMInfo llm={LLM} usedBy={0} />);
    expect(screen.getByText("2 keys")).toBeInTheDocument();
    expect(screen.getByTestId("json-view")).toHaveTextContent('"model":"gpt-4o"');
  });

  it("parses stringified JSON options too", () => {
    render(<LLMInfo llm={{ ...LLM, options: '{"model":"x"}' }} usedBy={0} />);
    expect(screen.getByText("1 key")).toBeInTheDocument();
    expect(screen.getByTestId("json-view")).toHaveTextContent('"model":"x"');
  });

  it("hides the options card when options are missing or invalid JSON", () => {
    const { rerender } = render(<LLMInfo llm={{ ...LLM, options: null }} usedBy={0} />);
    expect(screen.queryByTestId("json-view")).not.toBeInTheDocument();
    rerender(<LLMInfo llm={{ ...LLM, options: "not-json{{" }} usedBy={0} />);
    expect(screen.queryByTestId("json-view")).not.toBeInTheDocument();
  });
});

describe("LLMInfo used-by list", () => {
  const projects = [
    { id: 1, name: "alpha", llm: "gpt4" },
    { id: 2, name: "beta", llm: "other" },
    { id: 3, name: "gamma", llm: "gpt4" },
  ];

  it("lists only the projects whose main llm matches, with an attached count", () => {
    render(<LLMInfo llm={LLM} projects={projects} usedBy={2} />);
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("gamma")).toBeInTheDocument();
    expect(screen.queryByText("beta")).not.toBeInTheDocument();
    expect(screen.getByText("2 attached")).toBeInTheDocument();
  });

  it("navigates to the project page when a chip is clicked", async () => {
    const user = userEvent.setup();
    render(<LLMInfo llm={LLM} projects={projects} usedBy={2} />);
    await user.click(screen.getByText("alpha"));
    expect(mockNavigate).toHaveBeenCalledWith("/project/1");
  });

  it("omits the section entirely when no project uses the model", () => {
    render(<LLMInfo llm={LLM} projects={[{ id: 2, name: "beta", llm: "other" }]} usedBy={0} />);
    expect(screen.queryByText(/attached/)).not.toBeInTheDocument();
  });
});

describe("LLMInfo actions", () => {
  it("toggles the QR code with the current page URL as value", async () => {
    const user = userEvent.setup();
    render(<LLMInfo llm={LLM} usedBy={0} />);
    expect(screen.queryByTestId("qr")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("QrCode2Icon").closest("button"));
    expect(screen.getByTestId("qr")).toHaveAttribute("data-value", window.location.href);

    await user.click(screen.getByTestId("QrCode2Icon").closest("button"));
    expect(screen.queryByTestId("qr")).not.toBeInTheDocument();
  });

  it("copies the model name to the clipboard and toasts", async () => {
    // userEvent.setup() installs its own clipboard stub — spy on that.
    const user = userEvent.setup();
    render(<LLMInfo llm={LLM} usedBy={0} />);
    const writeSpy = jest.spyOn(navigator.clipboard, "writeText");
    await user.click(screen.getByTestId("ContentCopyIcon").closest("button"));
    expect(writeSpy).toHaveBeenCalledWith("gpt4");
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it("edit navigates to the edit page", async () => {
    const user = userEvent.setup();
    render(<LLMInfo llm={LLM} usedBy={0} />);
    await user.click(screen.getByRole("button", { name: "common.edit" }));
    expect(mockNavigate).toHaveBeenCalledWith("/llm/5/edit");
  });

  it("delete confirms, calls the API by id and navigates back to the list", async () => {
    const user = userEvent.setup();
    render(<LLMInfo llm={LLM} usedBy={0} />);
    await user.click(screen.getByRole("button", { name: "common.delete" }));
    expect(window.confirm).toHaveBeenCalledWith("llms.info.confirmDelete");
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/llms/5", "tok"));
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/llms"));
  });

  it("delete aborted by confirm does not call the API", async () => {
    window.confirm = jest.fn(() => false);
    const user = userEvent.setup();
    render(<LLMInfo llm={LLM} usedBy={0} />);
    await user.click(screen.getByRole("button", { name: "common.delete" }));
    expect(api.delete).not.toHaveBeenCalled();
  });

  it("hides edit and delete from non-admins", () => {
    useAuth.mockReturnValue({ user: { token: "tok", username: "bob", is_admin: false } });
    render(<LLMInfo llm={LLM} usedBy={0} />);
    expect(screen.queryByRole("button", { name: "common.edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "common.delete" })).not.toBeInTheDocument();
  });
});
