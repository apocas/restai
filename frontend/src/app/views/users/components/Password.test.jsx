import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Password from "./Password";
import api from "app/utils/api";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";

jest.mock("app/utils/api", () => ({ get: jest.fn(), patch: jest.fn() }));
jest.mock("react-toastify", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));
jest.mock("app/hooks/useAuth", () => jest.fn());

const target = { username: "bob" };

let locationMock;
beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin" } });
  api.get.mockResolvedValue({ enabled: false });
  api.patch.mockResolvedValue({});
  locationMock = { href: "", pathname: "/admin/user/bob" };
  delete window.location;
  window.location = locationMock;
});

async function fillPasswords(user, pw, confirm) {
  await user.type(screen.getByLabelText("users.password.newPassword"), pw);
  await user.type(screen.getByLabelText("users.password.confirmPassword"), confirm);
}

describe("Password", () => {
  it("saves the new password and redirects to the profile", async () => {
    const user = userEvent.setup();
    render(<Password user={target} />);

    await fillPasswords(user, "newpass1", "newpass1");
    await user.click(screen.getByRole("button", { name: "users.password.saveChanges" }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith("/users/bob", { password: "newpass1" }, "tok")
    );
    expect(locationMock.href).toBe("/admin/user/bob");
  });

  it("rejects mismatched confirmation without calling the API", async () => {
    const user = userEvent.setup();
    render(<Password user={target} />);

    await fillPasswords(user, "one", "two");
    await user.click(screen.getByRole("button", { name: "users.password.saveChanges" }));

    expect(toast.error).toHaveBeenCalledWith("users.password.mismatch");
    expect(api.patch).not.toHaveBeenCalled();
  });

  it("requires the TOTP code when 2FA is enabled, and sends it with the change", async () => {
    api.get.mockResolvedValue({ enabled: true });
    const user = userEvent.setup();
    render(<Password user={target} />);

    // 2FA on → info alert + code field appear after the status fetch.
    expect(await screen.findByText("users.password.twoFactorAlert")).toBeInTheDocument();

    await fillPasswords(user, "newpass1", "newpass1");
    await user.click(screen.getByRole("button", { name: "users.password.saveChanges" }));
    expect(toast.error).toHaveBeenCalledWith("users.password.twoFactorRequired");
    expect(api.patch).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("users.password.twoFactorCode"), "123456");
    await user.click(screen.getByRole("button", { name: "users.password.saveChanges" }));
    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        "/users/bob",
        { password: "newpass1", totp_code: "123456" },
        "tok"
      )
    );
  });
});
