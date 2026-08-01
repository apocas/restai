import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ImageGenerators from "./List";
import api from "app/utils/api";
import { toast } from "react-toastify";

jest.mock("app/utils/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  delete: jest.fn(),
}));
jest.mock("react-toastify", () => ({
  toast: { success: jest.fn(), error: jest.fn(), warning: jest.fn(), info: jest.fn() },
}));
// Stable t — the component's fetch effect depends on [t]; a fresh function
// per render would retrigger it forever.
jest.mock("react-i18next", () => {
  const t = (k) => k;
  return { useTranslation: () => ({ t }) };
});
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}));

// Default sort is name asc: dalle (id 2) first, local-sd (id 1) second.
const GENERATORS = [
  { id: 1, name: "local-sd", class_name: "local", privacy: "public", enabled: true, options: {} },
  { id: 2, name: "dalle", class_name: "openai", privacy: "private", enabled: false, options: { model: "dall-e-3" } },
];

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  api.get.mockResolvedValue(GENERATORS);
  api.patch.mockResolvedValue({});
  api.post.mockResolvedValue({});
  api.delete.mockResolvedValue({});
  window.confirm = jest.fn(() => true);
});

const renderList = async () => {
  render(<ImageGenerators />);
  await screen.findByText("dalle");
};

describe("ImageGenerators List", () => {
  it("fetches and renders generator rows with provider and model", async () => {
    await renderList();
    expect(api.get).toHaveBeenCalledWith("/image_generators", "tok");
    expect(screen.getByText("local-sd")).toBeInTheDocument();
    expect(screen.getByText("dall-e-3")).toBeInTheDocument();
    // local worker rows show the worker marker instead of a model
    expect(screen.getByText("(worker)")).toBeInTheDocument();
  });

  it("toggling the enabled switch PATCHes the generator and refetches", async () => {
    const user = userEvent.setup();
    await renderList();

    // Row order (name asc): dalle first. Its switch is unchecked.
    const switches = screen.getAllByRole("checkbox");
    expect(switches[0]).not.toBeChecked();
    await user.click(switches[0]);

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith("/image_generators/2", { enabled: true }, "tok")
    );
    expect(toast.success).toHaveBeenCalledWith("imageGen.dialog.enabledToast");
    await waitFor(() => {
      const listCalls = api.get.mock.calls.filter(([p]) => p === "/image_generators");
      expect(listCalls).toHaveLength(2);
    });
  });

  it("delete is disabled for local workers and works with confirm for remote generators", async () => {
    const user = userEvent.setup();
    await renderList();

    // Tooltip wraps the delete buttons in a labelled span (disabled-button pattern)
    const localDeleteWrap = screen.getByLabelText("imageGen.actions.deleteLocal");
    expect(within(localDeleteWrap).getByRole("button")).toBeDisabled();

    await user.click(within(screen.getByLabelText("imageGen.actions.delete")).getByRole("button"));
    expect(window.confirm).toHaveBeenCalledWith("imageGen.dialog.deleteConfirm");
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/image_generators/2", "tok"));
    expect(toast.success).toHaveBeenCalledWith("imageGen.dialog.deleted");
  });

  it("dismissed confirm aborts the delete", async () => {
    window.confirm = jest.fn(() => false);
    const user = userEvent.setup();
    await renderList();
    await user.click(within(screen.getByLabelText("imageGen.actions.delete")).getByRole("button"));
    expect(api.delete).not.toHaveBeenCalled();
  });

  it("create dialog posts the new generator with provider options (api key as password)", async () => {
    const user = userEvent.setup();
    await renderList();

    await user.click(screen.getByRole("button", { name: "imageGen.new" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("imageGen.dialog.newTitle")).toBeInTheDocument();

    const apiKey = within(dialog).getByLabelText(/imageGen\.dialog\.apiKey/);
    expect(apiKey).toHaveAttribute("type", "password");

    await user.type(within(dialog).getByLabelText(/imageGen\.dialog\.name/), "banana");
    const model = within(dialog).getByLabelText(/imageGen\.dialog\.model/);
    await user.clear(model);
    await user.type(model, "dall-e-3");
    await user.type(apiKey, "sk-img");

    await user.click(within(dialog).getByRole("button", { name: "imageGen.dialog.create" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    const [path, body, token] = api.post.mock.calls[0];
    expect(path).toBe("/image_generators");
    expect(token).toBe("tok");
    expect(body).toEqual({
      name: "banana",
      class_name: "openai",
      privacy: "public",
      description: "",
      enabled: true,
      options: { model: "dall-e-3", api_key: "sk-img", base_url: "" },
    });
    expect(toast.success).toHaveBeenCalledWith("imageGen.dialog.created");
  });

  it("editing a local worker restricts the payload to privacy/description/enabled", async () => {
    const user = userEvent.setup();
    await renderList();

    // local-sd row's edit button (second row, name asc)
    const edits = screen.getAllByRole("button", { name: "imageGen.actions.edit" });
    await user.click(edits[1]);

    const dialog = await screen.findByRole("dialog");
    // Local worker info alert, no provider/model/key fields
    expect(within(dialog).getByText("imageGen.dialog.localInfo")).toBeInTheDocument();
    expect(within(dialog).queryByLabelText(/imageGen\.dialog\.model/)).not.toBeInTheDocument();

    await user.type(within(dialog).getByLabelText(/imageGen\.dialog\.description/), "gpu box");
    await user.click(within(dialog).getByRole("button", { name: "imageGen.dialog.save" }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        "/image_generators/1",
        { privacy: "public", description: "gpu box", enabled: true },
        "tok"
      )
    );
  });

  it("import flow: discovers models from an OpenAI-compatible endpoint and imports the selection", async () => {
    const user = userEvent.setup();
    api.post.mockImplementation((path) => {
      if (path === "/tools/openai-compat/discover") {
        return Promise.resolve({ models: [{ id: "gpt image 1", owned_by: "openai" }, { id: "dall-e-3" }] });
      }
      return Promise.resolve({});
    });
    await renderList();

    await user.click(screen.getByRole("button", { name: "imageGen.import.button" }));
    const dialog = await screen.findByRole("dialog");

    await user.type(within(dialog).getByLabelText(/imageGen\.import\.apiKey/), "sk-up");
    await user.click(within(dialog).getByRole("button", { name: "imageGen.import.discover" }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/tools/openai-compat/discover",
        { base_url: "https://api.openai.com/v1", api_key: "sk-up" },
        "tok"
      )
    );
    expect(await within(dialog).findByText("gpt image 1")).toBeInTheDocument();

    // Checkboxes: [select-all, model1, model2] — pick the first model
    const boxes = within(dialog).getAllByRole("checkbox");
    await user.click(boxes[1]);
    await user.click(within(dialog).getByRole("button", { name: "imageGen.import.importSelected" }));

    await waitFor(() => {
      const importCalls = api.post.mock.calls.filter(([p]) => p === "/image_generators");
      expect(importCalls).toHaveLength(1);
    });
    const body = api.post.mock.calls.find(([p]) => p === "/image_generators")[1];
    // Name sanitized to validate_safe_name charset; original id kept in options.model
    expect(body.name).toBe("gpt-image-1");
    expect(body.class_name).toBe("openai");
    expect(body.options).toEqual({
      model: "gpt image 1",
      api_key: "sk-up",
      base_url: "https://api.openai.com/v1",
    });
    expect(toast.success).toHaveBeenCalledWith("imageGen.import.done");
  });

  it("hides admin actions from non-admins", async () => {
    useAuth.mockReturnValue({ user: { token: "tok", username: "joe", is_admin: false } });
    await renderList();
    expect(screen.queryByRole("button", { name: "imageGen.new" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "imageGen.import.button" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("imageGen.actions.delete")).not.toBeInTheDocument();
    // enabled switches render but are disabled
    screen.getAllByRole("checkbox").forEach((c) => expect(c).toBeDisabled());
  });
});
