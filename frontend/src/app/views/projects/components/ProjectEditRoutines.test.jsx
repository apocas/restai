import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProjectEditRoutines from "./ProjectEditRoutines";
import api from "app/utils/api";
import { toast } from "react-toastify";

jest.setTimeout(20000);

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

const PROJECT = { id: 3, name: "docs" };

const ROUTINES = [
  {
    id: 1,
    name: "daily-summary",
    message: "Summarize yesterday's tickets",
    schedule_minutes: 1440,
    enabled: true,
    last_run: "2026-07-30T08:00:00Z",
    last_result: "All good",
  },
  {
    id: 2,
    name: "health-check",
    message: "ping",
    schedule_minutes: 5,
    enabled: false,
    last_run: null,
    last_result: null,
  },
];

let routinesResp;

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok" } });
  routinesResp = () => Promise.resolve({ routines: ROUTINES });
  api.get.mockImplementation((path) => {
    if (path === "/projects/3/routines") return routinesResp();
    if (path.includes("/history")) return Promise.resolve({ runs: [] });
    return Promise.resolve({});
  });
  api.post.mockResolvedValue({});
  api.patch.mockResolvedValue({});
  api.delete.mockResolvedValue({});
});

const renderRoutines = async () => {
  render(<ProjectEditRoutines project={PROJECT} />);
  await screen.findByText("daily-summary");
};

describe("ProjectEditRoutines", () => {
  it("shows a spinner while loading, then the routine cards", async () => {
    routinesResp = () => new Promise(() => {});
    const { unmount } = render(<ProjectEditRoutines project={PROJECT} />);
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    unmount();

    routinesResp = () => Promise.resolve({ routines: ROUTINES });
    await renderRoutines();
    expect(api.get).toHaveBeenCalledWith("/projects/3/routines", "tok");
    expect(screen.getByText("health-check")).toBeInTheDocument();
    expect(screen.getByText("Every 24 hours")).toBeInTheDocument();
    expect(screen.getByText("Every 5 minutes")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Disabled")).toBeInTheDocument();
    expect(screen.getByText(/All good/)).toBeInTheDocument();
  });

  it("shows the empty state when there are no routines", async () => {
    routinesResp = () => Promise.resolve({ routines: [] });
    render(<ProjectEditRoutines project={PROJECT} />);
    expect(await screen.findByText(/No routines yet/)).toBeInTheDocument();
  });

  it("toggling the status chip PATCHes enabled and refetches", async () => {
    const user = userEvent.setup();
    await renderRoutines();

    await user.click(screen.getByText("Active"));
    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith("/projects/3/routines/1", { enabled: false }, "tok")
    );
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  });

  it("fire-now POSTs the fire endpoint and toasts", async () => {
    const user = userEvent.setup();
    await renderRoutines();

    const fireButtons = screen.getAllByRole("button", { name: "projects.edit.routines.fireNow" });
    await user.click(fireButtons[0]);

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/projects/3/routines/1/fire", {}, "tok")
    );
    expect(toast.success).toHaveBeenCalledWith("Routine fired");
  });

  it("delete asks for confirmation and DELETEs on accept, skips on cancel", async () => {
    const user = userEvent.setup();
    const confirmSpy = jest.spyOn(window, "confirm").mockReturnValue(false);
    await renderRoutines();

    const deleteButtons = screen.getAllByRole("button", { name: "projects.actions.delete" });
    await user.click(deleteButtons[0]);
    expect(confirmSpy).toHaveBeenCalledWith('Delete routine "daily-summary"?');
    expect(api.delete).not.toHaveBeenCalled();

    confirmSpy.mockReturnValue(true);
    await user.click(deleteButtons[0]);
    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith("/projects/3/routines/1", "tok")
    );
    expect(toast.success).toHaveBeenCalledWith("Routine deleted");
    confirmSpy.mockRestore();
  });

  it("create dialog: Create disabled until name+message set, then POSTs the form", async () => {
    const user = userEvent.setup();
    await renderRoutines();

    await user.click(screen.getByRole("button", { name: /Add Routine/ }));
    const dialog = await screen.findByRole("dialog");
    const createBtn = within(dialog).getByRole("button", { name: "Create" });
    expect(createBtn).toBeDisabled();

    await user.type(within(dialog).getByLabelText("Name"), "nightly");
    expect(createBtn).toBeDisabled();
    await user.type(within(dialog).getByLabelText("Message"), "do the thing");
    expect(createBtn).toBeEnabled();

    await user.click(createBtn);
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/projects/3/routines",
        { name: "nightly", message: "do the thing", schedule_minutes: 60, enabled: true },
        "tok"
      )
    );
    expect(toast.success).toHaveBeenCalledWith("Routine created");
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  });

  it("edit dialog PATCHes the changed routine", async () => {
    const user = userEvent.setup();
    await renderRoutines();

    const editButtons = screen.getAllByRole("button", { name: "projects.actions.edit" });
    await user.click(editButtons[1]);
    const dialog = await screen.findByRole("dialog");

    const nameField = within(dialog).getByLabelText("Name");
    await user.clear(nameField);
    await user.type(nameField, "health-check-2");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        "/projects/3/routines/2",
        { name: "health-check-2", message: "ping", schedule_minutes: 5, enabled: false },
        "tok"
      )
    );
    expect(toast.success).toHaveBeenCalledWith("Routine updated");
  });

  it("history dialog fetches the execution log and renders per-fire rows", async () => {
    const user = userEvent.setup();
    api.get.mockImplementation((path) => {
      if (path === "/projects/3/routines") return Promise.resolve({ routines: ROUTINES });
      if (path === "/projects/3/routines/1/history?limit=50") {
        return Promise.resolve({
          runs: [
            { id: 11, status: "ok", manual: true, duration_ms: 1200, result: "fine", created_at: "2026-07-30T08:00:00Z" },
            { id: 12, status: "error", manual: false, duration_ms: null, result: "boom", created_at: "2026-07-29T08:00:00Z" },
          ],
        });
      }
      return Promise.resolve({});
    });
    await renderRoutines();

    const historyButtons = screen.getAllByRole("button", { name: "projects.edit.routines.history" });
    await user.click(historyButtons[0]);

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith("/projects/3/routines/1/history?limit=50", "tok")
    );
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/projects.edit.routines.history/)).toBeInTheDocument();
    expect(within(dialog).getByText("ok")).toBeInTheDocument();
    expect(within(dialog).getByText("error")).toBeInTheDocument();
    expect(within(dialog).getByText("manual")).toBeInTheDocument();
    expect(within(dialog).getByText("cron")).toBeInTheDocument();
    expect(within(dialog).getByText("1200 ms")).toBeInTheDocument();
    expect(within(dialog).getByText("fine")).toBeInTheDocument();
    expect(within(dialog).getByText("boom")).toBeInTheDocument();

    // refresh refetches the same routine's history
    await user.click(within(dialog).getByRole("button", { name: "common.refresh" }));
    await waitFor(() =>
      expect(
        api.get.mock.calls.filter(([p]) => p === "/projects/3/routines/1/history?limit=50").length
      ).toBe(2)
    );

    await user.click(within(dialog).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("history dialog shows the empty state when a routine never ran", async () => {
    const user = userEvent.setup();
    await renderRoutines();

    const historyButtons = screen.getAllByRole("button", { name: "projects.edit.routines.history" });
    await user.click(historyButtons[1]);

    expect(await screen.findByText(/No runs yet/)).toBeInTheDocument();
  });
});
