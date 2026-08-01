import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Teams from "./Teams";
import api from "app/utils/api";
import useAuth from "app/hooks/useAuth";

jest.mock("app/utils/api", () => ({ get: jest.fn() }));
// Interpolated keys render as "key|value1|value2" so assertions can see the params.
jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (k, p) => (p ? `${k}|${Object.values(p).join("|")}` : k),
  }),
}));
jest.mock("app/hooks/useAuth", () => jest.fn());

const renderIt = (target) =>
  render(
    <MemoryRouter>
      <Teams user={target} />
    </MemoryRouter>
  );

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin" } });
});

describe("Teams with the budget endpoint", () => {
  it("renders capped, uncapped and depleted-wallet team cards", async () => {
    api.get.mockResolvedValue({
      teams: [
        { team_id: 1, team_name: "Alpha", is_admin: true, budget: 100, spending: 80, team_balance: 12.5 },
        { team_id: 2, team_name: "Beta", is_admin: false, budget: null, spending: 3.5, team_balance: 0 },
      ],
    });
    renderIt({ username: "bob", teams: [{ id: 2, name: "Beta", description: "the beta team" }] });

    expect(await screen.findByText("Alpha")).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith("/users/bob/team-budgets", "tok", { silent: true });

    // Card count badge.
    expect(screen.getByText("2")).toBeInTheDocument();

    // Alpha: admin chip, 80/100 → 80%, remaining $20, wallet balance shown.
    expect(screen.getByText("users.userTeams.admin")).toBeInTheDocument();
    expect(screen.getByText("80%")).toBeInTheDocument();
    expect(screen.getByText("users.userTeams.remaining|$20.00")).toBeInTheDocument();
    expect(screen.getByText("users.userTeams.teamWallet|$12.50")).toBeInTheDocument();

    // Beta: member chip, uncapped spend line, depleted wallet, description from profile.
    expect(screen.getByText("users.userTeams.member")).toBeInTheDocument();
    expect(screen.getByText(/users\.userTeams\.spentThisMonth\|\$3\.50/)).toBeInTheDocument();
    expect(screen.getByText(/users\.userTeams\.uncapped/)).toBeInTheDocument();
    expect(screen.getByText("teams.balance.depleted")).toBeInTheDocument();
    expect(screen.getByText("the beta team")).toBeInTheDocument();

    // Team name links to the team page.
    expect(screen.getByRole("link", { name: "Alpha" })).toHaveAttribute("href", "/team/1");
  });
});

describe("Teams fallback when the budget endpoint fails", () => {
  it("builds cards from the profile team lists with admin flags", async () => {
    api.get.mockRejectedValue(new Error("older backend"));
    renderIt({
      username: "bob",
      teams: [
        { id: 1, name: "Zulu" },
        { id: 2, name: "Alpha" },
      ],
      admin_teams: [{ id: 2, name: "Alpha" }],
    });

    await waitFor(() => expect(api.get).toHaveBeenCalled());

    // Sorted alphabetically: Alpha (admin) then Zulu (member).
    const links = screen.getAllByRole("link");
    expect(links.map((l) => l.textContent)).toEqual(["Alpha", "Zulu"]);
    expect(screen.getByText("users.userTeams.admin")).toBeInTheDocument();
    expect(screen.getByText("users.userTeams.member")).toBeInTheDocument();

    // Fallback has no budget info → uncapped spend of $0.00 on both.
    expect(screen.getAllByText(/users\.userTeams\.spentThisMonth\|\$0\.00/)).toHaveLength(2);
  });

  it("shows the empty state for a user with no teams", async () => {
    api.get.mockResolvedValue({ teams: [] });
    renderIt({ username: "bob", teams: [] });

    expect(await screen.findByText("users.userTeams.noTeams")).toBeInTheDocument();
  });
});
