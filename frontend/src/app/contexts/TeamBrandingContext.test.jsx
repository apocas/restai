import { render, screen, act } from "@testing-library/react";
import { TeamBrandingProvider, useTeamBranding } from "./TeamBrandingContext";
import api from "app/utils/api";
import useAuth from "app/hooks/useAuth";

jest.mock("app/utils/api", () => ({ patch: jest.fn() }));
jest.mock("app/hooks/useAuth", () => jest.fn());

let ctx;
function Probe() {
  ctx = useTeamBranding();
  return (
    <div>
      <span data-testid="team">{ctx.teamName || "none"}</span>
      <span data-testid="app">{ctx.branding?.app_name || "none"}</span>
      <span data-testid="count">{ctx.brandedTeams.length}</span>
    </div>
  );
}

const renderBranding = () =>
  render(
    <TeamBrandingProvider>
      <Probe />
    </TeamBrandingProvider>
  );

const branded = (id, name, app_name) => ({ id, name, branding: { app_name } });
const plain = (id, name) => ({ id, name, branding: null });

beforeEach(() => {
  jest.clearAllMocks();
  api.patch.mockResolvedValue({});
  ctx = undefined;
});

describe("TeamBrandingProvider", () => {
  it("exposes nulls when unauthenticated", () => {
    useAuth.mockReturnValue({ user: null, isAuthenticated: false });
    renderBranding();
    expect(screen.getByTestId("team")).toHaveTextContent("none");
    expect(screen.getByTestId("count")).toHaveTextContent("0");
  });

  it("picks the first branded team when there is no preference", () => {
    useAuth.mockReturnValue({
      isAuthenticated: true,
      user: { username: "u", teams: [plain(1, "A"), branded(2, "B", "B-App")], admin_teams: [] },
    });
    renderBranding();
    expect(screen.getByTestId("team")).toHaveTextContent("B");
    expect(screen.getByTestId("app")).toHaveTextContent("B-App");
    expect(screen.getByTestId("count")).toHaveTextContent("1");
  });

  it("honors the user's preferred_team_id over the first branded team", () => {
    useAuth.mockReturnValue({
      isAuthenticated: true,
      user: {
        username: "u",
        options: { preferred_team_id: 3 },
        teams: [branded(2, "B", "B-App"), branded(3, "C", "C-App")],
        admin_teams: [],
      },
    });
    renderBranding();
    expect(screen.getByTestId("team")).toHaveTextContent("C");
  });

  it("dedupes teams the user both belongs to and admins", () => {
    const t = branded(5, "Dup", "Dup-App");
    useAuth.mockReturnValue({
      isAuthenticated: true,
      user: { username: "u", teams: [t], admin_teams: [t] },
    });
    renderBranding();
    expect(screen.getByTestId("count")).toHaveTextContent("1");
  });

  it("reports no branding when no team has any configured", () => {
    useAuth.mockReturnValue({
      isAuthenticated: true,
      user: { username: "u", teams: [plain(1, "A")], admin_teams: [] },
    });
    renderBranding();
    expect(screen.getByTestId("team")).toHaveTextContent("none");
    expect(screen.getByTestId("app")).toHaveTextContent("none");
  });

  it("setActiveTeamId switches the branding and persists the preference", async () => {
    useAuth.mockReturnValue({
      isAuthenticated: true,
      user: {
        username: "u",
        token: "tok",
        teams: [branded(2, "B", "B-App"), branded(3, "C", "C-App")],
        admin_teams: [],
      },
    });
    renderBranding();
    expect(screen.getByTestId("team")).toHaveTextContent("B");

    await act(async () => {
      ctx.setActiveTeamId(3);
    });
    expect(screen.getByTestId("team")).toHaveTextContent("C");
    expect(api.patch).toHaveBeenCalledWith(
      "/users/u",
      { options: { preferred_team_id: 3 } },
      "tok"
    );
  });
});
