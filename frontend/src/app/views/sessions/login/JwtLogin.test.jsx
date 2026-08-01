import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import JwtLogin from "./JwtLogin";
import useAuth from "app/hooks/useAuth";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";

jest.mock("app/hooks/useAuth", () => jest.fn());
jest.mock("app/contexts/PlatformContext", () => ({ usePlatformCapabilities: jest.fn() }));
jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (k, p) => (p && p.provider ? `${k}:${p.provider}` : k),
  }),
}));

const login = jest.fn();
const verifyTotp = jest.fn();

const renderLogin = () =>
  render(
    <MemoryRouter>
      <JwtLogin />
    </MemoryRouter>
  );

// The page assigns window.location.href on success — swap in a plain object.
let locationMock;
beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  useAuth.mockReturnValue({ login, verifyTotp });
  usePlatformCapabilities.mockReturnValue({
    platformCapabilities: { sso: [], sso_provider_names: {}, auth_disable_local: false, app_name: "RESTai" },
  });
  locationMock = { href: "", pathname: "/admin/login" };
  delete window.location;
  window.location = locationMock;
});

const originalLocation = window.location;
afterAll(() => {
  window.location = originalLocation;
});

async function fillAndReveal(user) {
  await user.type(screen.getByLabelText("sessions.username"), "alice");
  // First submit only reveals the password step.
  await user.click(screen.getByRole("button", { name: "common.next" }));
  await user.type(screen.getByLabelText("sessions.password"), "s3cret");
}

describe("JwtLogin", () => {
  it("reveals the password step on first submit (progressive disclosure)", async () => {
    const user = userEvent.setup();
    renderLogin();
    expect(screen.getByRole("button", { name: "common.next" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "common.next" }));
    expect(screen.getByRole("button", { name: "sessions.signInAction" })).toBeInTheDocument();
    expect(login).not.toHaveBeenCalled();
  });

  it("shows the session-expired banner once and clears the flag", async () => {
    sessionStorage.setItem("session_expired", "1");
    renderLogin();
    expect(await screen.findByText(/session has expired/i)).toBeInTheDocument();
    expect(sessionStorage.getItem("session_expired")).toBeNull();
  });

  it("logs in and redirects to /admin", async () => {
    const user = userEvent.setup();
    login.mockResolvedValue({ requires_totp: false });
    renderLogin();

    await fillAndReveal(user);
    await user.click(screen.getByRole("button", { name: "sessions.signInAction" }));

    await waitFor(() => expect(login).toHaveBeenCalledWith("alice", "s3cret"));
    expect(locationMock.href).toBe("/admin");
  });

  it("surfaces login failures inline without redirecting", async () => {
    const user = userEvent.setup();
    login.mockRejectedValue(new Error("Bad credentials"));
    renderLogin();

    await fillAndReveal(user);
    await user.click(screen.getByRole("button", { name: "sessions.signInAction" }));

    expect(await screen.findByText("Bad credentials")).toBeInTheDocument();
    expect(locationMock.href).toBe("");
  });

  it("switches to the TOTP step when 2FA is required, then verifies and redirects", async () => {
    const user = userEvent.setup();
    login.mockResolvedValue({ requires_totp: true, totp_token: "tt" });
    verifyTotp.mockResolvedValue();
    renderLogin();

    await fillAndReveal(user);
    await user.click(screen.getByRole("button", { name: "sessions.signInAction" }));

    expect(await screen.findByText("sessions.totpTitle")).toBeInTheDocument();
    await user.type(screen.getByLabelText("sessions.totpCodeLabel"), "123456");
    await user.click(screen.getByRole("button", { name: "sessions.totpVerify" }));

    await waitFor(() => expect(verifyTotp).toHaveBeenCalledWith("tt", "123456"));
    expect(locationMock.href).toBe("/admin");
  });

  it("shows TOTP errors and supports the recovery-code toggle and back button", async () => {
    const user = userEvent.setup();
    login.mockResolvedValue({ requires_totp: true, totp_token: "tt" });
    verifyTotp.mockRejectedValue(new Error("Invalid code."));
    renderLogin();

    await fillAndReveal(user);
    await user.click(screen.getByRole("button", { name: "sessions.signInAction" }));
    await screen.findByText("sessions.totpTitle");

    await user.type(screen.getByLabelText("sessions.totpCodeLabel"), "000000");
    await user.click(screen.getByRole("button", { name: "sessions.totpVerify" }));
    expect(await screen.findByText("Invalid code.")).toBeInTheDocument();

    // Toggle to recovery-code entry…
    await user.click(screen.getByRole("button", { name: "sessions.totpRecoveryToggle" }));
    expect(screen.getByPlaceholderText("abcd1234")).toBeInTheDocument();

    // …and back to the credentials step.
    await user.click(screen.getByRole("button", { name: "common.back" }));
    expect(screen.getByRole("button", { name: "common.next" })).toBeInTheDocument();
  });

  it("renders SSO buttons and starts the provider flow on click", async () => {
    const user = userEvent.setup();
    usePlatformCapabilities.mockReturnValue({
      platformCapabilities: {
        sso: ["google", "github"],
        sso_provider_names: { google: "Google" },
        auth_disable_local: false,
      },
    });
    renderLogin();

    await user.click(screen.getByRole("button", { name: /google/i }));
    expect(locationMock.href).toBe("/oauth/google/login");
  });

  it("hides the local form entirely when auth_disable_local is set", () => {
    usePlatformCapabilities.mockReturnValue({
      platformCapabilities: { sso: ["oidc"], sso_provider_names: {}, auth_disable_local: true },
    });
    renderLogin();
    expect(screen.queryByLabelText("sessions.username")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /oidc/i })).toBeInTheDocument();
  });
});
