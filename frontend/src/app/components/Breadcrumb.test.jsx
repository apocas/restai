import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Breadcrumb from "./Breadcrumb";

const renderCrumbs = (routeSegments) =>
  render(
    <MemoryRouter>
      <Breadcrumb routeSegments={routeSegments} />
    </MemoryRouter>
  );

describe("Breadcrumb", () => {
  it("links intermediate segments and renders the last as plain text", () => {
    renderCrumbs([
      { name: "Projects", path: "/projects" },
      { name: "My Project", path: "/projects/1" },
    ]);

    const link = screen.getByRole("link", { name: "Projects" });
    expect(link).toHaveAttribute("href", "/projects");

    // Final segment: shown (twice — heading + trail) but never a link.
    expect(screen.getAllByText("My Project").length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: "My Project" })).not.toBeInTheDocument();
  });

  it("renders only the home icon when no segments are given", () => {
    renderCrumbs(undefined);
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });
});
