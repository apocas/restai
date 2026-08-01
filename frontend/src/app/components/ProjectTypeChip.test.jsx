import { render, screen } from "@testing-library/react";
import ProjectTypeChip from "./ProjectTypeChip";
import { PROJECT_TYPE_COLORS } from "app/utils/constant";

describe("ProjectTypeChip", () => {
  it.each(["rag", "agent", "block"])("renders the %s type with its palette color", (type) => {
    render(<ProjectTypeChip type={type} />);
    const chip = screen.getByText(type);
    expect(chip).toBeInTheDocument();
    expect(chip.closest(".MuiChip-root")).toHaveStyle({
      color: PROJECT_TYPE_COLORS[type].color,
    });
  });

  it("falls back to the default style for unknown types", () => {
    render(<ProjectTypeChip type="mystery" />);
    const chip = screen.getByText("mystery");
    expect(chip.closest(".MuiChip-root")).toHaveStyle({ color: "#ef4444" });
  });

  it("forwards extra props to the underlying Chip", () => {
    render(<ProjectTypeChip type="rag" data-testid="chip" />);
    expect(screen.getByTestId("chip")).toBeInTheDocument();
  });
});
