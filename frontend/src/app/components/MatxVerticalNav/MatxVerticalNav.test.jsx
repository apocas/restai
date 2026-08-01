import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import MatxVerticalNav from "./MatxVerticalNav";

const ITEMS = [
  { type: "label", label: "Backend" },
  { name: "Dashboard", path: "/dashboard", icon: "dashboard" },
  { name: "Projects", path: "/projects", icon: "folder", badge: { value: "12" } },
  { name: "Docs", path: "https://example.com/docs", type: "extLink", icon: "book" },
  {
    name: "Admin",
    icon: "settings",
    children: [{ name: "Users", path: "/users", iconText: "U" }],
  },
];

const renderNav = (initialEntries = ["/"]) =>
  render(
    <MemoryRouter initialEntries={initialEntries}>
      <MatxVerticalNav items={ITEMS} />
    </MemoryRouter>
  );

describe("MatxVerticalNav", () => {
  it("renders section labels, internal links, and badges", () => {
    renderNav();
    expect(screen.getByText("Backend")).toBeInTheDocument();

    const dashboard = screen.getByText("Dashboard").closest("a");
    expect(dashboard).toHaveAttribute("href", "/dashboard");
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("renders external links with target=_blank and noopener", () => {
    renderNav();
    const docs = screen.getByText("Docs").closest("a");
    expect(docs).toHaveAttribute("href", "https://example.com/docs");
    expect(docs).toHaveAttribute("target", "_blank");
    expect(docs).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("applies the active class to the current route's link", () => {
    renderNav(["/projects"]);
    const active = screen.getByText("Projects").closest("a");
    const inactive = screen.getByText("Dashboard").closest("a");
    // Regression: InternalItem is emotion styled(NavLink); the wrapper must
    // preserve NavLink's function-className API so `.active` really lands
    // (it used to stringify the function into the class attribute).
    expect(active).toHaveClass("active");
    expect(active).toHaveClass("nav-item");
    expect(active).toHaveAttribute("aria-current", "page");
    expect(inactive).not.toHaveClass("active");
    expect(inactive).toHaveClass("nav-item");
  });

  it("renders children of a parent item inside an expansion panel", () => {
    renderNav();
    expect(screen.getByText("Admin")).toBeInTheDocument();
    expect(screen.getByText("Users")).toBeInTheDocument();
    expect(screen.getByText("Users").closest("a")).toHaveAttribute("href", "/users");
  });
});
