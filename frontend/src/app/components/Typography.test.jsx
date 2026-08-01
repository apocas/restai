import { render, screen } from "@testing-library/react";
import { H1, H2, H3, H4, H5, H6, Paragraph, Small, Span, Tiny } from "./Typography";

describe("Typography components", () => {
  it.each([
    [H1, "H1", "28px"],
    [H2, "H2", "24px"],
    [H3, "H3", "18px"],
    [H4, "H4", "16px"],
    [H5, "H5", "14px"],
    [H6, "H6", "13px"],
  ])("heading %#. renders children in the right tag with its font size", (Comp, tag, size) => {
    render(<Comp>hello {tag}</Comp>);
    const el = screen.getByText(`hello ${tag}`);
    expect(el.tagName).toBe(tag);
    expect(el).toHaveStyle({ fontSize: size, fontWeight: 500 });
  });

  it("Paragraph renders a <p> at 14px", () => {
    render(<Paragraph>para</Paragraph>);
    const el = screen.getByText("para");
    expect(el.tagName).toBe("P");
    expect(el).toHaveStyle({ fontSize: "14px" });
  });

  it("Small renders a <small> at 12px", () => {
    render(<Small>tiny-ish</Small>);
    const el = screen.getByText("tiny-ish");
    expect(el.tagName).toBe("SMALL");
    expect(el).toHaveStyle({ fontSize: "12px" });
  });

  it("Span renders a <span>", () => {
    render(<Span>inline</Span>);
    expect(screen.getByText("inline").tagName).toBe("SPAN");
  });

  it("Tiny renders a <small> at 10px", () => {
    render(<Tiny>micro</Tiny>);
    const el = screen.getByText("micro");
    expect(el.tagName).toBe("SMALL");
    expect(el).toHaveStyle({ fontSize: "10px" });
  });

  it("applies ellipsis styles when the ellipsis prop is set", () => {
    render(<H1 ellipsis="true">truncated</H1>);
    expect(screen.getByText("truncated")).toHaveStyle({
      whiteSpace: "nowrap",
      overflow: "hidden",
      textOverflow: "ellipsis",
    });
  });

  it("omits ellipsis styles by default", () => {
    render(<H1>free flowing</H1>);
    expect(screen.getByText("free flowing")).not.toHaveStyle({ whiteSpace: "nowrap" });
  });

  it("passes className and extra props through", () => {
    render(
      <Paragraph className="custom-cls" data-testid="para">
        styled
      </Paragraph>
    );
    const el = screen.getByTestId("para");
    expect(el).toHaveClass("custom-cls");
    expect(el).toHaveTextContent("styled");
  });
});
