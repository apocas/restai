import { render, screen } from "@testing-library/react";
import { FlexBox, FlexBetween, FlexAlignCenter, FlexJustifyCenter } from "./FlexBox";

describe("FlexBox variants", () => {
  it("FlexBox renders children with display flex", () => {
    render(<FlexBox data-testid="fb">child</FlexBox>);
    const el = screen.getByTestId("fb");
    expect(el).toHaveTextContent("child");
    expect(el).toHaveStyle({ display: "flex" });
  });

  it("FlexBetween aligns center and spaces between", () => {
    render(<FlexBetween data-testid="fb">x</FlexBetween>);
    const el = screen.getByTestId("fb");
    expect(el).toHaveStyle({
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
    });
  });

  it("FlexAlignCenter centers on both axes", () => {
    render(<FlexAlignCenter data-testid="fb">x</FlexAlignCenter>);
    const el = screen.getByTestId("fb");
    expect(el).toHaveStyle({
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
    });
  });

  it("FlexJustifyCenter centers horizontally only", () => {
    render(<FlexJustifyCenter data-testid="fb">x</FlexJustifyCenter>);
    const el = screen.getByTestId("fb");
    expect(el).toHaveStyle({ display: "flex", justifyContent: "center" });
  });
});
