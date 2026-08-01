import { render, screen } from "@testing-library/react";
import MatxDivider from "./MatxDivider";

describe("MatxDivider", () => {
  it("renders the label inside a span when text is given", () => {
    render(<MatxDivider text="OR" />);
    const label = screen.getByText("OR");
    expect(label.tagName).toBe("SPAN");
  });

  it("renders no span when text is omitted", () => {
    const { container } = render(<MatxDivider />);
    expect(container.querySelector("span")).toBeNull();
  });

  it("forwards sx styling to the divider root", () => {
    const { container } = render(<MatxDivider text="hi" sx={{ marginTop: "13px" }} />);
    const root = screen.getByText("hi").parentElement;
    expect(root).toHaveStyle({ marginTop: "13px" });
    expect(container.firstChild).toBeInTheDocument();
  });
});
