import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ErrorBoundary from "./ErrorBoundary";

function Bomb() {
  throw new Error("boom");
}

describe("ErrorBoundary", () => {
  it("renders children when nothing throws", () => {
    render(
      <ErrorBoundary>
        <div>all good</div>
      </ErrorBoundary>
    );
    expect(screen.getByText("all good")).toBeInTheDocument();
  });

  it("catches render errors and shows the fallback with a refresh button", async () => {
    // React logs caught errors loudly — silence for this intentional throw.
    const spy = jest.spyOn(console, "error").mockImplementation(() => {});
    const original = window.location;
    delete window.location;
    window.location = { ...original, reload: jest.fn() };
    try {
      render(
        <ErrorBoundary>
          <Bomb />
        </ErrorBoundary>
      );
      expect(screen.getByText("Something went wrong.")).toBeInTheDocument();

      await userEvent.click(screen.getByRole("button", { name: /refresh/i }));
      expect(window.location.reload).toHaveBeenCalled();
    } finally {
      window.location = original;
      spy.mockRestore();
    }
  });
});
