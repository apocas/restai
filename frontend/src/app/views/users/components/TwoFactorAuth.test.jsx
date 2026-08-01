import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TwoFactorAuth from "./TwoFactorAuth";
import api from "app/utils/api";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";

jest.mock("app/utils/api", () => ({ get: jest.fn(), post: jest.fn() }));
jest.mock("react-toastify", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));
jest.mock("app/hooks/useAuth", () => jest.fn());

const SETUP = {
  secret: "BASE32SECRET",
  provisioning_uri: "otpauth://totp/RESTai:bob?secret=BASE32SECRET",
  recovery_codes: ["aaaa-1111", "bbbb-2222", "cccc-3333", "dddd-4444"],
};

const renderIt = (username = "bob") =>
  render(<TwoFactorAuth user={{ username: "bob" }} />);

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "bob" } });
  api.get.mockResolvedValue({ enabled: false, enforced: false });
});

describe("TwoFactorAuth setup flow", () => {
  it("walks through setup: QR + secret + recovery codes, then enables", async () => {
    const user = userEvent.setup();
    api.post.mockResolvedValueOnce(SETUP); // /totp/setup
    renderIt();

    expect(await screen.findByText("users.twoFactor.disabledChip")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "users.twoFactor.setup" }));

    // Step screen: manual key + all recovery codes visible.
    expect(await screen.findByText("BASE32SECRET")).toBeInTheDocument();
    for (const code of SETUP.recovery_codes) {
      expect(screen.getByText(code)).toBeInTheDocument();
    }

    // Enable requires a 6-digit code AND the password.
    const enable = screen.getByRole("button", { name: "users.twoFactor.enable" });
    expect(enable).toBeDisabled();
    await user.type(screen.getByLabelText("users.twoFactor.code"), "123456");
    expect(enable).toBeDisabled();
    await user.type(screen.getByLabelText("users.twoFactor.password"), "pw");
    expect(enable).toBeEnabled();

    api.post.mockResolvedValueOnce({}); // /totp/enable
    api.get.mockResolvedValue({ enabled: true, enforced: false });
    await user.click(enable);

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/users/bob/totp/enable",
        { code: "123456", password: "pw" },
        "tok"
      )
    );
    expect(toast.success).toHaveBeenCalledWith("users.twoFactor.enabledSuccess");
    expect(await screen.findByText("users.twoFactor.enabledChip")).toBeInTheDocument();
  });

  it("surfaces the server detail when the code is rejected", async () => {
    const user = userEvent.setup();
    api.post.mockResolvedValueOnce(SETUP);
    renderIt();
    await user.click(await screen.findByRole("button", { name: "users.twoFactor.setup" }));
    await screen.findByText("BASE32SECRET");

    await user.type(screen.getByLabelText("users.twoFactor.code"), "999999");
    await user.type(screen.getByLabelText("users.twoFactor.password"), "pw");
    api.post.mockRejectedValueOnce({ response: { data: { detail: "Code mismatch" } } });
    await user.click(screen.getByRole("button", { name: "users.twoFactor.enable" }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Code mismatch"));
  });
});

describe("TwoFactorAuth disable flow", () => {
  beforeEach(() => {
    api.get.mockResolvedValue({ enabled: true, enforced: false });
  });

  it("reveals the password confirmation and disables 2FA (self only)", async () => {
    const user = userEvent.setup();
    renderIt();

    await user.click(await screen.findByRole("button", { name: "users.twoFactor.disable" }));
    await user.type(screen.getByLabelText("users.twoFactor.confirmPassword"), "pw");

    api.post.mockResolvedValueOnce({});
    api.get.mockResolvedValue({ enabled: false, enforced: false });
    await user.click(screen.getByRole("button", { name: "users.twoFactor.confirmDisable" }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/users/bob/totp/disable", { password: "pw" }, "tok")
    );
    expect(toast.success).toHaveBeenCalledWith("users.twoFactor.disabledSuccess");
  });

  it("blocks disabling when 2FA is platform-enforced", async () => {
    api.get.mockResolvedValue({ enabled: true, enforced: true });
    renderIt();

    expect(await screen.findByText("users.twoFactor.enforced")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "users.twoFactor.cannotDisable" })
    ).toBeDisabled();
  });

  it("hides the disable control when viewing someone else's profile", async () => {
    useAuth.mockReturnValue({ user: { token: "tok", username: "someone-else" } });
    renderIt();

    expect(await screen.findByText("users.twoFactor.enabledChip")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "users.twoFactor.disable" })).not.toBeInTheDocument();
  });
});
