import { render, screen } from "@testing-library/react";
import ChatAvatar from "./ChatAvatar";

describe("ChatAvatar", () => {
  it("renders an avatar image for the given src", () => {
    render(<ChatAvatar src="/face.png" />);
    expect(screen.getByRole("img")).toHaveAttribute("src", "/face.png");
  });

  it("renders the generic fallback avatar without a src", () => {
    const { container } = render(<ChatAvatar />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(container.querySelector(".MuiAvatar-root")).toBeInTheDocument();
  });
});
