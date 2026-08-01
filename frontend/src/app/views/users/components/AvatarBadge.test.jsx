import { render, screen } from "@testing-library/react";
import AvatarBadge from "./AvatarBadge";

describe("AvatarBadge", () => {
  it("renders its children", () => {
    render(
      <AvatarBadge>
        <img src="/me.png" alt="me" />
      </AvatarBadge>
    );
    expect(screen.getByAltText("me")).toBeInTheDocument();
  });

  it("renders a circular-overlap badge element", () => {
    const { container } = render(
      <AvatarBadge variant="dot">
        <span>kid</span>
      </AvatarBadge>
    );
    const badge = container.querySelector(".MuiBadge-badge");
    expect(badge).toBeInTheDocument();
    expect(badge.className).toMatch(/MuiBadge-overlapCircular/);
  });

  it("shows badge content and passes extra props through", () => {
    render(
      <AvatarBadge badgeContent="7" color="success">
        <span>kid</span>
      </AvatarBadge>
    );
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("7").className).toMatch(/MuiBadge-colorSuccess/);
  });

  it("sizes the badge from the width/height props", () => {
    const { container } = render(
      <AvatarBadge badgeContent="x" width={20} height={20}>
        <span>kid</span>
      </AvatarBadge>
    );
    expect(container.querySelector(".MuiBadge-badge")).toHaveStyle({
      width: "20px",
      height: "20px",
    });
  });
});
