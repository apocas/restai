import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Brand from "./Brand";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";
import { useTeamBranding } from "app/contexts/TeamBrandingContext";

jest.mock("app/contexts/PlatformContext", () => ({
  usePlatformCapabilities: jest.fn(),
}));
jest.mock("app/contexts/TeamBrandingContext", () => ({
  useTeamBranding: jest.fn(),
}));
// The components barrel pulls in the whole layout tree; stub the only
// piece Brand needs.
jest.mock("app/components", () => ({
  MatxLogo: () => {
    const React = require("react");
    return React.createElement("div", { "data-testid": "matx-logo" });
  },
}));

const brandingState = (overrides = {}) => ({
  branding: null,
  brandedTeams: [],
  activeTeamId: null,
  setActiveTeamId: jest.fn(),
  ...overrides,
});

beforeEach(() => {
  jest.clearAllMocks();
  usePlatformCapabilities.mockReturnValue({
    platformCapabilities: { app_name: "PlatformApp" },
  });
  useTeamBranding.mockReturnValue(brandingState());
});

describe("Brand", () => {
  it("falls back to the platform app name and default logo", () => {
    render(<Brand onToggleSidenav={jest.fn()} />);
    expect(screen.getByText("PlatformApp")).toBeInTheDocument();
    expect(screen.getByTestId("matx-logo")).toBeInTheDocument();
  });

  it("prefers the team branding app name and logo", () => {
    useTeamBranding.mockReturnValue(
      brandingState({
        branding: { app_name: "TeamApp", logo_url: "https://x/logo.png" },
      })
    );
    render(<Brand onToggleSidenav={jest.fn()} />);
    expect(screen.getByText("TeamApp")).toBeInTheDocument();
    expect(screen.queryByTestId("matx-logo")).not.toBeInTheDocument();
    expect(screen.getByAltText("logo")).toHaveAttribute("src", "https://x/logo.png");
  });

  it("defaults to RESTai when nothing configures a name", () => {
    usePlatformCapabilities.mockReturnValue({ platformCapabilities: {} });
    render(<Brand onToggleSidenav={jest.fn()} />);
    expect(screen.getByText("RESTai")).toBeInTheDocument();
  });

  it("toggles the sidenav from both the logo badge and the collapse button", async () => {
    const user = userEvent.setup();
    const onToggle = jest.fn();
    render(<Brand onToggleSidenav={onToggle} />);

    await user.click(screen.getByTestId("matx-logo"));
    expect(onToggle).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button"));
    expect(onToggle).toHaveBeenCalledTimes(2);
  });

  it("hides the team switcher with fewer than two branded teams", () => {
    useTeamBranding.mockReturnValue(
      brandingState({ brandedTeams: [{ id: 1, name: "Solo", branding: null }] })
    );
    render(<Brand onToggleSidenav={jest.fn()} />);
    // Only the collapse button — no switcher.
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("opens the switcher menu and selects a team", async () => {
    const user = userEvent.setup();
    const setActiveTeamId = jest.fn();
    useTeamBranding.mockReturnValue(
      brandingState({
        brandedTeams: [
          { id: 1, name: "Alpha", branding: { app_name: "Alpha-App" } },
          { id: 2, name: "Beta", branding: null },
        ],
        activeTeamId: 1,
        setActiveTeamId,
      })
    );
    render(<Brand onToggleSidenav={jest.fn()} />);

    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(2); // switcher + collapse
    await user.click(buttons[0]);

    // Menu shows branding app_name when present, team name otherwise.
    expect(screen.getByRole("menuitem", { name: "Alpha-App" })).toBeInTheDocument();
    await user.click(screen.getByRole("menuitem", { name: "Beta" }));
    expect(setActiveTeamId).toHaveBeenCalledWith(2);
  });
});
