import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Users from "./List";
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

// Default sort is id desc, so row order is: bob (id 2), admin (id 1).
const USERS = [
  {
    id: 1,
    username: "admin",
    is_admin: true,
    is_restricted: false,
    sso: null,
    projects: [{ name: "p1" }, { name: "p2" }],
  },
  {
    id: 2,
    username: "bob",
    is_admin: false,
    is_restricted: true,
    sso: "google",
    projects: [],
  },
];

let usersResp;

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  usersResp = { users: USERS };
  api.get.mockImplementation(() => Promise.resolve(usersResp));
  api.delete.mockResolvedValue({});
  window.confirm = jest.fn(() => true);
});

const renderUsers = async () => {
  render(<Users />);
  if ((usersResp.users || []).length) {
    await screen.findByText(usersResp.users[0].username);
  } else {
    await screen.findByText("No users yet");
  }
};

describe("Users list", () => {
  it("fetches /users and renders one row per user with role/auth/access pills", async () => {
    await renderUsers();
    expect(api.get).toHaveBeenCalledWith("/users", "tok");
    expect(screen.getByText("admin")).toBeInTheDocument();
    expect(screen.getByText("bob")).toBeInTheDocument();
    expect(screen.getByText("USER/0001")).toBeInTheDocument();
    expect(screen.getByText("USER/0002")).toBeInTheDocument();
    // role pills
    expect(screen.getByText("Admin")).toBeInTheDocument();
    // auth pills: bob is SSO, admin is Local
    expect(screen.getByText("SSO")).toBeInTheDocument();
    expect(screen.getByText("Local")).toBeInTheDocument();
    // access pills: bob restricted, admin read/write
    expect(screen.getByText("Read-only")).toBeInTheDocument();
    expect(screen.getByText("Read/Write")).toBeInTheDocument();
  });

  it("admin sees a New User action that navigates to the create page", async () => {
    await renderUsers();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "New User" }));
    expect(mockNavigate).toHaveBeenCalledWith("/users/new");
  });

  it("non-admin sees no New User button, no edit/delete actions and no bulk checkboxes", async () => {
    useAuth.mockReturnValue({ user: { token: "tok", username: "joe", is_admin: false } });
    await renderUsers();
    expect(screen.queryByRole("button", { name: "New User" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    // view is still available to everyone (one per row)
    expect(screen.getAllByRole("button", { name: "View" })).toHaveLength(2);
  });

  it("clicking a row navigates to the user page", async () => {
    const user = userEvent.setup();
    await renderUsers();
    await user.click(screen.getByText("bob"));
    expect(mockNavigate).toHaveBeenCalledWith("/user/bob");
  });

  it("view action navigates to the user page", async () => {
    const user = userEvent.setup();
    await renderUsers();
    // first row is bob (id 2, id-desc sort)
    await user.click(screen.getAllByRole("button", { name: "View" })[0]);
    expect(mockNavigate).toHaveBeenCalledWith("/user/bob");
  });

  it("delete confirms with the username, calls the API and refetches", async () => {
    const user = userEvent.setup();
    await renderUsers();

    await user.click(screen.getAllByRole("button", { name: "Delete" })[0]);

    expect(window.confirm).toHaveBeenCalledWith('Delete user "bob"?');
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/users/bob", "tok"));
    expect(toast.success).toHaveBeenCalledWith("Deleted bob");
    await waitFor(() =>
      expect(api.get.mock.calls.filter(([p]) => p === "/users")).toHaveLength(2)
    );
  });

  it("delete aborted by confirm does not call the API", async () => {
    window.confirm = jest.fn(() => false);
    const user = userEvent.setup();
    await renderUsers();

    await user.click(screen.getAllByRole("button", { name: "Delete" })[0]);

    expect(api.delete).not.toHaveBeenCalled();
  });

  it("bulk delete confirms with names, deletes silently one by one and refetches", async () => {
    const user = userEvent.setup();
    await renderUsers();

    await user.click(screen.getByRole("checkbox", { name: "select row bob" }));
    await user.click(screen.getByRole("checkbox", { name: "select row admin" }));
    // The bulk bar button carries visible text "Delete" (row actions are icon buttons).
    await user.click(screen.getByText("Delete"));

    expect(window.confirm).toHaveBeenCalledWith("Delete 2 users?\n\nadmin, bob");
    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith("/users/admin", "tok", { silent: true })
    );
    expect(api.delete).toHaveBeenCalledWith("/users/bob", "tok", { silent: true });
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Deleted 2 users"));
    expect(toast.error).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(api.get.mock.calls.filter(([p]) => p === "/users")).toHaveLength(2)
    );
  });

  it("bulk delete reports partial failures", async () => {
    api.delete.mockImplementation((path) =>
      path === "/users/bob" ? Promise.reject(new Error("nope")) : Promise.resolve({})
    );
    const user = userEvent.setup();
    await renderUsers();

    await user.click(screen.getByRole("checkbox", { name: "select row bob" }));
    await user.click(screen.getByRole("checkbox", { name: "select row admin" }));
    await user.click(screen.getByText("Delete"));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Deleted 1 user"));
    expect(toast.error).toHaveBeenCalledWith("Failed to delete 1 user");
  });

  it("renders the empty state when there are no users", async () => {
    usersResp = { users: [] };
    await renderUsers();
    expect(screen.getByText("No users yet")).toBeInTheDocument();
    expect(
      screen.getByText("Platform users show up here. Add a first admin or teammate to get started.")
    ).toBeInTheDocument();
    // hero + empty-state both offer New User for admins
    expect(screen.getAllByRole("button", { name: "New User" })).toHaveLength(2);
  });
});
