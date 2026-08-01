import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Teams from "./Teams";
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

// Default sort is id desc, so row order is: beta (id 2), alpha (id 1).
const TEAMS = [
  {
    id: 1,
    name: "alpha",
    description: "first team",
    users: [{ username: "admin" }, { username: "bob" }],
    projects: [{ id: 1 }],
    admins: [],
  },
  {
    id: 2,
    name: "beta",
    description: "",
    users: [{ username: "bob" }],
    projects: [],
    admins: [{ username: "admin" }],
  },
];

let teamsResp;

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  teamsResp = { teams: TEAMS };
  api.get.mockImplementation(() => Promise.resolve(teamsResp));
  api.delete.mockResolvedValue({});
  window.confirm = jest.fn(() => true);
});

const renderTeams = async () => {
  render(<Teams />);
  if ((teamsResp.teams || []).length) {
    await screen.findByText(teamsResp.teams[0].name);
  } else {
    await screen.findByText("teams.emptyTitle");
  }
};

describe("Teams list", () => {
  it("fetches /teams and renders one row per team", async () => {
    await renderTeams();
    expect(api.get).toHaveBeenCalledWith("/teams", "tok");
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("beta")).toBeInTheDocument();
    expect(screen.getByText("TEAM/0001")).toBeInTheDocument();
    expect(screen.getByText("TEAM/0002")).toBeInTheDocument();
    expect(screen.getByText("first team")).toBeInTheDocument();
  });

  it("platform admin sees the platform_admin role pill on every row and a New Team action", async () => {
    await renderTeams();
    expect(screen.getAllByText("teams.role.platformAdmin")).toHaveLength(2);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "teams.new" }));
    expect(mockNavigate).toHaveBeenCalledWith("/teams/new");
  });

  it("non-admin sees team_admin/member roles and no New Team button or delete action", async () => {
    useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: false } });
    await renderTeams();
    // admin of beta, plain member of alpha
    expect(screen.getByText("teams.role.teamAdmin")).toBeInTheDocument();
    expect(screen.getByText("teams.role.member")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "teams.new" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "teams.actions.delete" })).not.toBeInTheDocument();
    // members can't edit
    expect(screen.getAllByRole("button", { name: "teams.actions.edit" })).toHaveLength(1);
  });

  it("clicking a row navigates to the team page", async () => {
    const user = userEvent.setup();
    await renderTeams();
    await user.click(screen.getByText("beta"));
    expect(mockNavigate).toHaveBeenCalledWith("/team/2");
  });

  it("view action navigates to the team page", async () => {
    const user = userEvent.setup();
    await renderTeams();
    // first row is beta (id 2)
    await user.click(screen.getAllByRole("button", { name: "teams.actions.view" })[0]);
    expect(mockNavigate).toHaveBeenCalledWith("/team/2");
  });

  it("delete confirms, calls the API and refetches", async () => {
    const user = userEvent.setup();
    await renderTeams();

    await user.click(screen.getAllByRole("button", { name: "teams.actions.delete" })[0]);

    expect(window.confirm).toHaveBeenCalledWith("teams.deleteConfirm");
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/teams/2", "tok"));
    expect(toast.success).toHaveBeenCalledWith("teams.deleted");
    await waitFor(() => expect(api.get.mock.calls.filter(([p]) => p === "/teams")).toHaveLength(2));
  });

  it("delete aborted by confirm does not call the API", async () => {
    window.confirm = jest.fn(() => false);
    const user = userEvent.setup();
    await renderTeams();

    await user.click(screen.getAllByRole("button", { name: "teams.actions.delete" })[0]);

    expect(api.delete).not.toHaveBeenCalled();
  });

  it("renders the empty state when there are no teams", async () => {
    teamsResp = { teams: [] };
    await renderTeams();
    expect(screen.getByText("teams.emptyTitle")).toBeInTheDocument();
    expect(screen.getByText("teams.emptyMessage")).toBeInTheDocument();
  });
});
