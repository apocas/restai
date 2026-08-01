import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Sidenav from "./Sidenav";

jest.mock("app/hooks/useSettings", () => jest.fn());
jest.mock("app/hooks/useAuth", () => jest.fn());
import useSettings from "app/hooks/useSettings";
import useAuth from "app/hooks/useAuth";

jest.mock("app/navigations", () => ({
  useNavigations: jest.fn(),
}));
import { useNavigations } from "app/navigations";

jest.mock("app/auth/navGuard", () => ({
  navGuard: jest.fn(),
}));
import { navGuard } from "app/auth/navGuard";

// Barrel stub — only the piece Sidenav renders.
jest.mock("app/components", () => ({
  MatxVerticalNav: ({ items }) => {
    const React = require("react");
    return React.createElement(
      "nav",
      { "data-testid": "vertical-nav" },
      items.map((i) => i.name).join(",")
    );
  },
}));

// react-perfect-scrollbar needs real DOM measurement — swap for a div.
jest.mock("react-perfect-scrollbar", () => ({ children, ...rest }) => {
  const React = require("react");
  return React.createElement("div", { "data-testid": "scrollbar" }, children);
});

const SETTINGS = {
  activeLayout: "layout1",
  layout1Settings: { leftSidebar: { mode: "full", theme: "slateDark1" } },
};

let updateSettings;

beforeEach(() => {
  jest.clearAllMocks();
  updateSettings = jest.fn();
  useSettings.mockReturnValue({ settings: SETTINGS, updateSettings });
  useAuth.mockReturnValue({ user: { username: "admin", is_admin: true } });
  useNavigations.mockReturnValue([{ name: "Home" }, { name: "AdminOnly" }]);
  navGuard.mockImplementation((items) => items.filter((i) => i.name !== "AdminOnly"));
});

describe("Sidenav", () => {
  it("passes the nav items through navGuard before rendering them", () => {
    render(<Sidenav />);
    expect(navGuard).toHaveBeenCalledWith(
      [{ name: "Home" }, { name: "AdminOnly" }],
      { username: "admin", is_admin: true }
    );
    expect(screen.getByTestId("vertical-nav")).toHaveTextContent("Home");
    expect(screen.getByTestId("vertical-nav")).not.toHaveTextContent("AdminOnly");
  });

  it("renders children above the nav", () => {
    render(
      <Sidenav>
        <div data-testid="brand-slot" />
      </Sidenav>
    );
    expect(screen.getByTestId("brand-slot")).toBeInTheDocument();
  });

  it("clicking the mobile overlay closes the sidebar via updateSettings", async () => {
    const user = userEvent.setup();
    const { container } = render(<Sidenav />);

    // The overlay is the last top-level element (fixed backdrop).
    const overlay = container.parentElement.querySelectorAll("div");
    await user.click(overlay[overlay.length - 1]);

    expect(updateSettings).toHaveBeenCalledWith(
      expect.objectContaining({
        layout1Settings: expect.objectContaining({
          leftSidebar: expect.objectContaining({ mode: "close" }),
        }),
      })
    );
  });
});
