import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import UserNewView from "./New";
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
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  api.post.mockResolvedValue({ username: "carol" });
});

const renderIt = () =>
  render(
    <MemoryRouter>
      <UserNewView />
    </MemoryRouter>
  );

const fields = () => ({
  username: screen.getByLabelText(/users\.fields\.username/),
  password: screen.getByLabelText(/users\.fields\.password/),
  confirm: screen.getByLabelText(/users\.fields\.confirmPassword/),
  submit: screen.getByRole("button", { name: "users.newPage.create" }),
});

describe("UserNewView rendering", () => {
  it("renders account fields and the four permission switches, all off", () => {
    renderIt();
    const f = fields();
    expect(f.username).toBeInTheDocument();
    expect(f.password).toHaveAttribute("type", "password");
    expect(f.confirm).toHaveAttribute("type", "password");

    // is_admin, is_restricted, is_suspended, is_private — in DOM order
    const switches = screen.getAllByRole("checkbox");
    expect(switches).toHaveLength(4);
    switches.forEach((s) => expect(s).not.toBeChecked());
    expect(screen.getByText("users.fields.isAdmin")).toBeInTheDocument();
    expect(screen.getByText("users.fields.isRestricted")).toBeInTheDocument();
    expect(screen.getByText("users.fields.isSuspended")).toBeInTheDocument();
    expect(screen.getByText("users.fields.isPrivate")).toBeInTheDocument();
  });

  it("shows the strength meter and requirement checklist once a password is typed", async () => {
    const user = userEvent.setup();
    renderIt();
    const f = fields();

    // no password yet — no checklist
    expect(screen.queryByText("users.pwReq.chars")).not.toBeInTheDocument();

    await user.type(f.password, "abc");
    expect(screen.getByText("users.pwReq.weak")).toBeInTheDocument();
    expect(screen.getByText("users.pwReq.chars")).toBeInTheDocument();

    await user.clear(f.password);
    await user.type(f.password, "Password1");
    expect(screen.getByText("users.pwReq.strong")).toBeInTheDocument();
  });

  it("flags a confirm-password mismatch inline while typing", async () => {
    const user = userEvent.setup();
    renderIt();
    const f = fields();

    await user.type(f.password, "Password1");
    await user.type(f.confirm, "Password2");
    expect(screen.getByText("users.newPage.passwordsMismatch")).toBeInTheDocument();

    await user.clear(f.confirm);
    await user.type(f.confirm, "Password1");
    expect(screen.queryByText("users.newPage.passwordsMismatch")).not.toBeInTheDocument();
  });
});

describe("UserNewView validation on submit", () => {
  it("rejects an empty username", async () => {
    const user = userEvent.setup();
    renderIt();
    await user.click(fields().submit);
    expect(toast.error).toHaveBeenCalledWith("users.newPage.usernameRequired");
    expect(api.post).not.toHaveBeenCalled();
  });

  it("rejects a missing password", async () => {
    const user = userEvent.setup();
    renderIt();
    const f = fields();
    await user.type(f.username, "carol");
    await user.click(f.submit);
    expect(toast.error).toHaveBeenCalledWith("users.newPage.passwordRequired");
    expect(api.post).not.toHaveBeenCalled();
  });

  it("rejects mismatched passwords", async () => {
    const user = userEvent.setup();
    renderIt();
    const f = fields();
    await user.type(f.username, "carol");
    await user.type(f.password, "Password1");
    await user.type(f.confirm, "Password2");
    await user.click(f.submit);
    expect(toast.error).toHaveBeenCalledWith("users.newPage.passwordsMismatch");
    expect(api.post).not.toHaveBeenCalled();
  });

  it("rejects passwords shorter than 8 chars", async () => {
    const user = userEvent.setup();
    renderIt();
    const f = fields();
    await user.type(f.username, "carol");
    await user.type(f.password, "Pw1");
    await user.type(f.confirm, "Pw1");
    await user.click(f.submit);
    expect(toast.error).toHaveBeenCalledWith("users.newPage.passwordMin");
    expect(api.post).not.toHaveBeenCalled();
  });
});

describe("UserNewView submit", () => {
  it("POSTs the full payload (toggled flags included) and navigates to the new profile", async () => {
    const user = userEvent.setup();
    renderIt();
    const f = fields();

    await user.type(f.username, "carol");
    await user.type(f.password, "Password1");
    await user.type(f.confirm, "Password1");
    const switches = screen.getAllByRole("checkbox");
    await user.click(switches[0]); // is_admin
    await user.click(switches[1]); // is_restricted
    await user.click(f.submit);

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/users",
        {
          username: "carol",
          password: "Password1",
          is_admin: true,
          is_private: false,
          is_restricted: true,
          is_suspended: false,
        },
        "tok"
      )
    );
    expect(mockNavigate).toHaveBeenCalledWith("/user/carol");
  });

  it("stays on the form and re-enables the button when the API rejects", async () => {
    api.post.mockRejectedValue(new Error("409"));
    const user = userEvent.setup();
    renderIt();
    const f = fields();

    await user.type(f.username, "carol");
    await user.type(f.password, "Password1");
    await user.type(f.confirm, "Password1");
    await user.click(f.submit);

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(mockNavigate).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "users.newPage.create" })).toBeEnabled()
    );
  });

  it("cancel navigates back to the users list without posting", async () => {
    const user = userEvent.setup();
    renderIt();
    await user.click(screen.getByRole("button", { name: "common.cancel" }));
    expect(mockNavigate).toHaveBeenCalledWith("/users");
    expect(api.post).not.toHaveBeenCalled();
  });
});
