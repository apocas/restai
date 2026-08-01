import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ApiKeys from "./ApiKeys";
import api from "app/utils/api";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";

jest.mock("app/utils/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  delete: jest.fn(),
}));
jest.mock("react-toastify", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
// Interpolated keys render as "key|value1|value2" so assertions can see the params.
jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (k, p) => (p ? `${k}|${Object.values(p).join("|")}` : k),
  }),
}));
jest.mock("app/hooks/useAuth", () => jest.fn());

const target = {
  username: "bob",
  teams: [
    { id: 1, name: "Team A" },
    { id: 2, name: "Team B" },
  ],
};

const PROJECTS = {
  projects: [
    { id: 10, name: "proj-a", team_id: 1 },
    { id: 11, name: "proj-b", team_id: 1 },
    { id: 20, name: "proj-c", team_id: 2 },
  ],
};

const KEYS = [
  {
    id: 1,
    description: "ci key",
    key_prefix: "sk-aaa",
    team_id: 1,
    read_only: true,
    allowed_projects: [10, 11],
    token_quota_monthly: 1000,
    tokens_used_this_month: 800,
    quota_reset_at: "2026-09-01T00:00:00Z",
    created_at: "2026-07-01T00:00:00Z",
  },
  {
    id: 2,
    description: "",
    key_prefix: "sk-bbb",
    team_id: 2,
    read_only: false,
    allowed_projects: null,
    token_quota_monthly: null,
    tokens_used_this_month: 0,
    created_at: "2026-07-02T00:00:00Z",
  },
];

function mockGets({ keys = KEYS, projects = PROJECTS } = {}) {
  api.get.mockImplementation((url) => {
    if (url.includes("/apikeys")) return Promise.resolve(keys);
    if (url === "/projects") return Promise.resolve(projects);
    return Promise.reject(new Error("unexpected " + url));
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  mockGets();
  api.post.mockResolvedValue({ api_key: "sk-plaintext-123" });
  api.patch.mockResolvedValue({});
  api.delete.mockResolvedValue({});
});

describe("ApiKeys listing", () => {
  it("shows the empty state when there are no keys", async () => {
    mockGets({ keys: [] });
    render(<ApiKeys user={target} />);

    expect(await screen.findByText("users.apiKeys.noKeys")).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith("/users/bob/apikeys", "tok");
    expect(api.get).toHaveBeenCalledWith("/projects", "tok");
  });

  it("renders scope chips, team names and quota usage per key", async () => {
    render(<ApiKeys user={target} />);

    expect(await screen.findByText("ci key")).toBeInTheDocument();
    expect(screen.getByText("sk-aaa...")).toBeInTheDocument();
    expect(screen.getByText("Team A")).toBeInTheDocument();
    expect(screen.getByText("Team B")).toBeInTheDocument();

    // Key 1: read-only, restricted to 2 projects, 800/1000 tokens used.
    expect(screen.getByText("users.apiKeys.readOnly")).toBeInTheDocument();
    expect(screen.getByText("users.apiKeys.allowedProjects|2")).toBeInTheDocument();
    expect(screen.getByText("users.apiKeys.quotaTokens|800|1,000")).toBeInTheDocument();
    expect(screen.getByText(/^users\.apiKeys\.quotaResets\|/)).toBeInTheDocument();

    // Key 2: unrestricted, no quota.
    expect(screen.getByText("users.apiKeys.allProjects")).toBeInTheDocument();
    expect(screen.getByText("users.apiKeys.unlimited")).toBeInTheDocument();
  });
});

describe("ApiKeys creation", () => {
  it("requires a team, preselects the team's projects, and reveals the new key once", async () => {
    const user = userEvent.setup();
    render(<ApiKeys user={target} />);
    await screen.findByText("ci key");

    await user.click(screen.getByRole("button", { name: "users.apiKeys.createNew" }));
    const dialog = await screen.findByRole("dialog");

    // Create disabled until a team is chosen (key bills the team's budget).
    const create = within(dialog).getByRole("button", { name: "common.create" });
    expect(create).toBeDisabled();

    await user.type(
      within(dialog).getByLabelText(/users\.apiKeys\.descriptionOptional/),
      "deploy key"
    );

    // Pick Team A → its two projects are auto-selected in the restrict field.
    await user.click(within(dialog).getByLabelText(/users\.apiKeys\.team/));
    await user.click(await screen.findByRole("option", { name: "Team A" }));
    expect(within(dialog).getByText("proj-a")).toBeInTheDocument();
    expect(within(dialog).getByText("proj-b")).toBeInTheDocument();
    expect(create).toBeEnabled();

    await user.click(create);

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/users/bob/apikeys",
        { description: "deploy key", team_id: 1, read_only: false, allowed_projects: [10, 11] },
        "tok"
      )
    );

    // Save-this-key dialog with the plaintext, copyable value.
    expect(await screen.findByText("users.apiKeys.saveKeyWarn")).toBeInTheDocument();
    expect(screen.getByDisplayValue("sk-plaintext-123")).toBeInTheDocument();

    const writeText = jest.fn();
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    await user.click(screen.getByTestId("ContentCopyIcon").closest("button"));
    expect(writeText).toHaveBeenCalledWith("sk-plaintext-123");
    expect(toast.success).toHaveBeenCalledWith("common.copied");
  });

  it("sends the read_only flag and drops deselected projects", async () => {
    const user = userEvent.setup();
    render(<ApiKeys user={target} />);
    await screen.findByText("ci key");

    await user.click(screen.getByRole("button", { name: "users.apiKeys.createNew" }));
    const dialog = await screen.findByRole("dialog");

    await user.click(within(dialog).getByLabelText(/users\.apiKeys\.team/));
    await user.click(await screen.findByRole("option", { name: "Team A" }));

    // Remove both preselected project chips → allowed_projects omitted (all projects).
    for (const chip of ["proj-a", "proj-b"]) {
      await user.click(
        within(within(dialog).getByText(chip).closest(".MuiChip-root")).getByTestId("CancelIcon")
      );
    }
    await user.click(within(dialog).getByRole("checkbox"));

    await user.click(within(dialog).getByRole("button", { name: "common.create" }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/users/bob/apikeys",
        { description: "", team_id: 1, read_only: true },
        "tok"
      )
    );
  });
});

describe("ApiKeys quota dialog", () => {
  it("saves a new monthly cap", async () => {
    const user = userEvent.setup();
    render(<ApiKeys user={target} />);
    await screen.findByText("ci key");

    await user.click(screen.getAllByTestId("EditIcon")[0].closest("button"));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("users.apiKeys.quotaUsedThis|sk-aaa|800")).toBeInTheDocument();

    const input = within(dialog).getByLabelText(/users\.apiKeys\.quotaInput/);
    expect(input).toHaveValue(1000);
    await user.clear(input);
    await user.type(input, "5000");
    await user.click(within(dialog).getByRole("button", { name: "common.save" }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        "/users/bob/apikeys/1",
        { token_quota_monthly: 5000 },
        "tok"
      )
    );
    expect(toast.success).toHaveBeenCalledWith("users.apiKeys.quotaSaved", { position: "top-right" });
  });

  it("clears the cap when the field is emptied", async () => {
    const user = userEvent.setup();
    render(<ApiKeys user={target} />);
    await screen.findByText("ci key");

    await user.click(screen.getAllByTestId("EditIcon")[0].closest("button"));
    const dialog = await screen.findByRole("dialog");
    await user.clear(within(dialog).getByLabelText(/users\.apiKeys\.quotaInput/));
    await user.click(within(dialog).getByRole("button", { name: "common.save" }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        "/users/bob/apikeys/1",
        { token_quota_monthly: 0 },
        "tok"
      )
    );
  });

  it("resets usage via the warning action", async () => {
    const user = userEvent.setup();
    render(<ApiKeys user={target} />);
    await screen.findByText("ci key");

    await user.click(screen.getAllByTestId("EditIcon")[0].closest("button"));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "users.apiKeys.resetUsage" }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith("/users/bob/apikeys/1", { reset_usage: true }, "tok")
    );
    expect(toast.success).toHaveBeenCalledWith("users.apiKeys.usageReset", { position: "top-right" });
  });
});

describe("ApiKeys deletion", () => {
  it("deletes after confirmation and refetches", async () => {
    const user = userEvent.setup();
    jest.spyOn(window, "confirm").mockReturnValue(true);
    render(<ApiKeys user={target} />);
    await screen.findByText("ci key");
    api.get.mockClear();

    await user.click(screen.getAllByTestId("DeleteIcon")[0].closest("button"));

    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith("/users/bob/apikeys/1", "tok")
    );
    expect(api.get).toHaveBeenCalledWith("/users/bob/apikeys", "tok");
  });

  it("does nothing when the confirm is dismissed", async () => {
    const user = userEvent.setup();
    jest.spyOn(window, "confirm").mockReturnValue(false);
    render(<ApiKeys user={target} />);
    await screen.findByText("ci key");

    await user.click(screen.getAllByTestId("DeleteIcon")[0].closest("button"));

    expect(api.delete).not.toHaveBeenCalled();
  });
});
