import { useContext } from "react";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axios from "axios";
import AuthContext, { AuthProvider } from "./JWTAuthContext";
import { applyLanguage } from "app/i18n";

jest.mock("axios", () => ({ get: jest.fn(), post: jest.fn() }));
// app/components/index.js re-exports the whole layout tree — stub the one
// piece the provider renders while initializing.
jest.mock("app/components", () => ({ MatxLoading: () => <div data-testid="loading" /> }));
jest.mock("app/i18n", () => ({ applyLanguage: jest.fn() }));

// Probe that surfaces state and exposes the context actions to tests.
let ctx;
function Probe() {
  ctx = useContext(AuthContext);
  return (
    <div>
      <span data-testid="authed">{String(ctx.isAuthenticated)}</span>
      <span data-testid="role">{ctx.user?.role || "none"}</span>
      <span data-testid="impersonating">{String(ctx.isImpersonating)}</span>
    </div>
  );
}

const renderProvider = () =>
  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>
  );

const whoamiUser = (over = {}) => ({
  username: "u1",
  is_admin: false,
  teams: [],
  admin_teams: [],
  ...over,
});

beforeEach(() => {
  jest.clearAllMocks();
  ctx = undefined;
  sessionStorage.clear();
});

describe("AuthProvider bootstrap", () => {
  it("shows the loader, then INITs authenticated from whoami with role assignment", async () => {
    axios.get.mockResolvedValue({ data: whoamiUser({ is_admin: true }) });
    renderProvider();
    expect(screen.getByTestId("loading")).toBeInTheDocument();

    expect(await screen.findByTestId("authed")).toHaveTextContent("true");
    expect(screen.getByTestId("role")).toHaveTextContent("ADMIN");
  });

  it("assigns TEAM_ADMIN when the user admins any team, USER otherwise", async () => {
    axios.get.mockResolvedValue({ data: whoamiUser({ admin_teams: [{ id: 1 }] }) });
    renderProvider();
    expect(await screen.findByTestId("role")).toHaveTextContent("TEAM_ADMIN");
  });

  it("INITs unauthenticated when whoami fails", async () => {
    jest.spyOn(console, "error").mockImplementation(() => {});
    axios.get.mockRejectedValue(new Error("401"));
    renderProvider();
    expect(await screen.findByTestId("authed")).toHaveTextContent("false");
    expect(screen.getByTestId("role")).toHaveTextContent("none");
    console.error.mockRestore();
  });

  it("applies the user's saved language, including legacy JSON-string options", async () => {
    axios.get.mockResolvedValue({
      data: whoamiUser({ options: JSON.stringify({ language: "pt" }) }),
    });
    renderProvider();
    await screen.findByTestId("authed");
    expect(applyLanguage).toHaveBeenCalledWith("pt");
  });

  it("flags impersonation reported by whoami", async () => {
    axios.get.mockResolvedValue({ data: whoamiUser({ impersonating: true }) });
    renderProvider();
    expect(await screen.findByTestId("impersonating")).toHaveTextContent("true");
  });
});

describe("login", () => {
  beforeEach(() => {
    // Bootstrap unauthenticated so login drives the transition.
    jest.spyOn(console, "error").mockImplementation(() => {});
    axios.get.mockRejectedValueOnce(new Error("401"));
  });
  afterEach(() => console.error.mockRestore());

  it("logs in with Basic credentials and INITs from whoami", async () => {
    renderProvider();
    await screen.findByTestId("authed");

    axios.post.mockResolvedValue({ data: {} });
    axios.get.mockResolvedValue({ data: whoamiUser() });

    let result;
    await act(async () => {
      result = await ctx.login("u1", "pw");
    });
    expect(result).toEqual({ requires_totp: false });
    expect(axios.post).toHaveBeenCalledWith(
      "/auth/login",
      {},
      { auth: { username: "u1", password: "pw" } }
    );
    expect(screen.getByTestId("authed")).toHaveTextContent("true");
    expect(screen.getByTestId("role")).toHaveTextContent("USER");
  });

  it("short-circuits with the TOTP token when 2FA is required", async () => {
    renderProvider();
    await screen.findByTestId("authed");

    axios.post.mockResolvedValue({ data: { requires_totp: true, totp_token: "tt" } });
    let result;
    await act(async () => {
      result = await ctx.login("u1", "pw");
    });
    expect(result).toEqual({ requires_totp: true, totp_token: "tt" });
    expect(screen.getByTestId("authed")).toHaveTextContent("false");
  });

  it("stashes the password-age warning for the post-login banner", async () => {
    renderProvider();
    await screen.findByTestId("authed");

    axios.post.mockResolvedValue({ data: { password_warning: { days: 99 } } });
    axios.get.mockResolvedValue({ data: whoamiUser() });
    await act(async () => {
      await ctx.login("u1", "pw");
    });
    expect(JSON.parse(sessionStorage.getItem("password_warning"))).toEqual({ days: 99 });
  });

  it("surfaces the server detail on failure", async () => {
    renderProvider();
    await screen.findByTestId("authed");

    axios.post.mockRejectedValue({ response: { data: { detail: "Bad credentials" } } });
    await expect(ctx.login("u1", "nope")).rejects.toThrow("Bad credentials");
    expect(screen.getByTestId("authed")).toHaveTextContent("false");
  });
});

describe("verifyTotp / logout", () => {
  beforeEach(() => {
    jest.spyOn(console, "error").mockImplementation(() => {});
    axios.get.mockRejectedValueOnce(new Error("401"));
  });
  afterEach(() => console.error.mockRestore());

  it("verifyTotp posts the code and INITs from whoami", async () => {
    renderProvider();
    await screen.findByTestId("authed");

    axios.post.mockResolvedValue({ data: {} });
    axios.get.mockResolvedValue({ data: whoamiUser({ is_admin: true }) });
    await act(async () => {
      await ctx.verifyTotp("tt", "123456");
    });
    expect(axios.post).toHaveBeenCalledWith(
      "/auth/verify-totp",
      { token: "tt", code: "123456" },
      { withCredentials: true }
    );
    expect(screen.getByTestId("role")).toHaveTextContent("ADMIN");
  });

  it("verifyTotp rethrows the server detail on bad codes", async () => {
    renderProvider();
    await screen.findByTestId("authed");

    axios.post.mockRejectedValue({ response: { data: { detail: "Invalid code." } } });
    await expect(ctx.verifyTotp("tt", "000000")).rejects.toThrow("Invalid code.");
  });

  it("logout clears state and posts to the backend", async () => {
    renderProvider();
    await screen.findByTestId("authed");

    axios.post.mockResolvedValue({ data: {} });
    axios.get.mockResolvedValue({ data: whoamiUser() });
    await act(async () => {
      await ctx.login("u1", "pw");
    });
    expect(screen.getByTestId("authed")).toHaveTextContent("true");

    await act(async () => {
      ctx.logout();
    });
    expect(screen.getByTestId("authed")).toHaveTextContent("false");
    expect(axios.post).toHaveBeenCalledWith("/auth/logout", {}, { withCredentials: true });
  });
});
