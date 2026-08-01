import { lazy } from "react";
import { render, screen } from "@testing-library/react";
import Loadable from "./Loadable";

describe("Loadable", () => {
  it("returns a component that renders the wrapped component with its props", () => {
    const Inner = ({ label }) => <div>inner:{label}</div>;
    const Wrapped = Loadable(Inner);
    render(<Wrapped label="abc" />);
    expect(screen.getByText("inner:abc")).toBeInTheDocument();
  });

  it("shows the loading spinner while a lazy component is pending", () => {
    const Wrapped = Loadable(lazy(() => new Promise(() => {})));
    render(<Wrapped />);
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("renders a lazy component once it resolves", async () => {
    const Wrapped = Loadable(
      lazy(() => Promise.resolve({ default: () => <div>lazy done</div> }))
    );
    render(<Wrapped />);
    expect(await screen.findByText("lazy done")).toBeInTheDocument();
  });
});
