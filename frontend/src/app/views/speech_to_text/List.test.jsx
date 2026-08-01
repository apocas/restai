import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SpeechToText from "./List";
import api from "app/utils/api";
import { toast } from "react-toastify";

jest.mock("app/utils/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  delete: jest.fn(),
}));
jest.mock("react-toastify", () => ({
  toast: { success: jest.fn(), error: jest.fn(), info: jest.fn(), warning: jest.fn() },
}));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}));

// Dialog-driven tests type through several MUI TextFields; give headroom
// when suites run in parallel on a loaded machine.
jest.setTimeout(20000);

const MODELS = [
  {
    id: 1,
    name: "whisper-openai",
    class_name: "openai",
    privacy: "public",
    enabled: true,
    description: "hosted whisper",
    options: { model: "whisper-1", api_key: "sk-x", base_url: "" },
  },
  {
    id: 2,
    name: "local-worker",
    class_name: "local",
    privacy: "private",
    enabled: false,
    description: "",
    options: {},
  },
];

let modelsResp;

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  modelsResp = () => Promise.resolve(MODELS);
  api.get.mockImplementation((path) => {
    if (path === "/speech_to_text") return modelsResp();
    return Promise.resolve({});
  });
  api.post.mockResolvedValue({});
  api.patch.mockResolvedValue({});
  api.delete.mockResolvedValue({});
  window.confirm = jest.fn(() => true);
});

const renderList = async () => {
  render(<SpeechToText />);
  await screen.findByText("whisper-openai");
};

const rowOf = (name) => screen.getByText(name).closest("tr");

describe("SpeechToText list rendering", () => {
  it("fetches models and renders rows with provider, model and privacy", async () => {
    await renderList();

    expect(api.get).toHaveBeenCalledWith("/speech_to_text", "tok");
    const whisper = rowOf("whisper-openai");
    expect(within(whisper).getByText("openai")).toBeInTheDocument();
    expect(within(whisper).getByText("whisper-1")).toBeInTheDocument();
    expect(within(whisper).getByText("public")).toBeInTheDocument();

    const local = rowOf("local-worker");
    expect(within(local).getByText("(worker)")).toBeInTheDocument();
    expect(within(local).getByText("private")).toBeInTheDocument();

    // Hero stats.
    expect(screen.getByText("2 configured")).toBeInTheDocument();
    expect(screen.getByText("1 enabled")).toBeInTheDocument();
  });

  it("shows the empty message when no models exist", async () => {
    modelsResp = () => Promise.resolve([]);
    render(<SpeechToText />);
    expect(await screen.findByText("speechGen.empty")).toBeInTheDocument();
  });

  it("navigates to the audio playground from the hero action", async () => {
    const user = userEvent.setup();
    await renderList();
    await user.click(screen.getByRole("button", { name: "speechGen.playground" }));
    expect(mockNavigate).toHaveBeenCalledWith("/audio");
  });

  it("hides admin actions from non-admin users", async () => {
    useAuth.mockReturnValue({ user: { token: "tok", username: "joe", is_admin: false } });
    await renderList();

    expect(screen.queryByRole("button", { name: "speechGen.new" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "speechGen.import.button" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("DeleteIcon")).not.toBeInTheDocument();
    expect(screen.queryByTestId("EditIcon")).not.toBeInTheDocument();
    // Enable toggles render but are disabled.
    expect(within(rowOf("whisper-openai")).getByRole("checkbox")).toBeDisabled();
  });
});

describe("SpeechToText row actions", () => {
  it("toggling the enabled switch PATCHes the model and refetches", async () => {
    const user = userEvent.setup();
    await renderList();

    await user.click(within(rowOf("whisper-openai")).getByRole("checkbox"));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith("/speech_to_text/1", { enabled: false }, "tok")
    );
    expect(toast.success).toHaveBeenCalledWith("speechGen.dialog.disabledToast");
    await waitFor(() =>
      expect(api.get.mock.calls.filter(([p]) => p === "/speech_to_text")).toHaveLength(2)
    );
  });

  it("deletes a non-local model after confirmation", async () => {
    const user = userEvent.setup();
    await renderList();

    const del = within(rowOf("whisper-openai")).getByTestId("DeleteIcon").closest("button");
    await user.click(del);

    expect(window.confirm).toHaveBeenCalledWith("speechGen.dialog.deleteConfirm");
    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith("/speech_to_text/1", "tok")
    );
    expect(toast.success).toHaveBeenCalledWith("speechGen.dialog.deleted");
  });

  it("does not delete when the confirm is dismissed", async () => {
    window.confirm = jest.fn(() => false);
    const user = userEvent.setup();
    await renderList();

    await user.click(within(rowOf("whisper-openai")).getByTestId("DeleteIcon").closest("button"));
    expect(api.delete).not.toHaveBeenCalled();
  });

  it("disables the delete button for local (worker) engines", async () => {
    await renderList();
    const del = within(rowOf("local-worker")).getByTestId("DeleteIcon").closest("button");
    expect(del).toBeDisabled();
  });
});

describe("SpeechToText create dialog", () => {
  it("creates a new openai engine with the typed name and options", async () => {
    const user = userEvent.setup();
    await renderList();

    await user.click(screen.getByRole("button", { name: "speechGen.new" }));
    expect(await screen.findByText("speechGen.dialog.newTitle")).toBeInTheDocument();

    await user.type(screen.getByLabelText(/speechGen\.dialog\.name/), "my-stt");
    await user.type(screen.getByLabelText(/speechGen\.dialog\.apiKey/), "sk-new");
    await user.click(screen.getByRole("button", { name: "speechGen.dialog.create" }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/speech_to_text",
        expect.objectContaining({
          name: "my-stt",
          class_name: "openai",
          privacy: "public",
          enabled: true,
          options: expect.objectContaining({ model: "whisper-1", api_key: "sk-new" }),
        }),
        "tok"
      )
    );
    expect(toast.success).toHaveBeenCalledWith("speechGen.dialog.created");
    await waitFor(() =>
      expect(screen.queryByText("speechGen.dialog.newTitle")).not.toBeInTheDocument()
    );
  });
});

describe("SpeechToText edit dialog", () => {
  it("editing a local engine sends only privacy/description/enabled", async () => {
    const user = userEvent.setup();
    await renderList();

    await user.click(within(rowOf("local-worker")).getByTestId("EditIcon").closest("button"));
    expect(await screen.findByText("speechGen.dialog.editTitle")).toBeInTheDocument();
    // Local engines get the info alert and no provider options.
    expect(screen.getByText("speechGen.dialog.localInfo")).toBeInTheDocument();
    expect(screen.queryByLabelText(/speechGen\.dialog\.apiKey/)).not.toBeInTheDocument();

    await user.type(screen.getByLabelText(/speechGen\.dialog\.description/), "cpu whisper");
    await user.click(screen.getByRole("button", { name: "speechGen.dialog.save" }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        "/speech_to_text/2",
        { privacy: "private", description: "cpu whisper", enabled: false },
        "tok"
      )
    );
    expect(toast.success).toHaveBeenCalledWith("speechGen.dialog.saved");
  });
});

describe("SpeechToText import dialog", () => {
  it("discovers models from an OpenAI-compatible endpoint and imports the selection", async () => {
    api.post.mockImplementation((path) => {
      if (path === "/tools/openai-compat/discover") {
        return Promise.resolve({
          models: [
            { id: "whisper-1", owned_by: "openai" },
            { id: "gpt 4o transcribe" },
          ],
        });
      }
      return Promise.resolve({});
    });
    const user = userEvent.setup();
    await renderList();

    await user.click(screen.getByRole("button", { name: "speechGen.import.button" }));
    expect(await screen.findByText("speechGen.import.title")).toBeInTheDocument();

    await user.type(screen.getByLabelText("speechGen.import.apiKey"), "sk-imp");
    await user.click(screen.getByRole("button", { name: "speechGen.import.discover" }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/tools/openai-compat/discover",
        { base_url: "https://api.openai.com/v1", api_key: "sk-imp" },
        "tok"
      )
    );
    expect(await screen.findByText("speechGen.import.modelsFound")).toBeInTheDocument();
    expect(screen.getByText("gpt 4o transcribe")).toBeInTheDocument();

    // Select all, then import.
    await user.click(screen.getByRole("checkbox", { name: /selectAll/ }));
    await user.click(screen.getByRole("button", { name: /importSelected/ }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/speech_to_text",
        expect.objectContaining({
          name: "whisper-1",
          class_name: "openai",
          options: { model: "whisper-1", api_key: "sk-imp", base_url: "https://api.openai.com/v1" },
        }),
        "tok"
      )
    );
    // Names are sanitized to validate_safe_name; original id kept in options.
    expect(api.post).toHaveBeenCalledWith(
      "/speech_to_text",
      expect.objectContaining({
        name: "gpt-4o-transcribe",
        options: expect.objectContaining({ model: "gpt 4o transcribe" }),
      }),
      "tok"
    );
    expect(toast.success).toHaveBeenCalledWith("speechGen.import.done");
    await waitFor(() =>
      expect(screen.queryByText("speechGen.import.title")).not.toBeInTheDocument()
    );
  });

  it("shows an info toast when discovery returns no models", async () => {
    api.post.mockResolvedValue({ models: [] });
    const user = userEvent.setup();
    await renderList();

    await user.click(screen.getByRole("button", { name: "speechGen.import.button" }));
    await user.click(screen.getByRole("button", { name: "speechGen.import.discover" }));

    await waitFor(() => expect(toast.info).toHaveBeenCalledWith("speechGen.import.noModels"));
    // Import stays disabled with nothing selected.
    expect(screen.getByRole("button", { name: /importSelected/ })).toBeDisabled();
  });
});
