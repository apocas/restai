import { lazy } from "react";
import { render, screen } from "@testing-library/react";
import MatxSuspense from "./MatxSuspense";

// The components barrel pulls in the whole layout tree; stub the only
// piece MatxSuspense needs.
jest.mock("app/components", () => ({
  MatxLoading: () => {
    const React = require("react");
    return React.createElement("div", { "data-testid": "matx-loading" });
  },
}));

describe("MatxSuspense", () => {
  it("renders ready children directly", () => {
    render(
      <MatxSuspense>
        <div>ready content</div>
      </MatxSuspense>
    );
    expect(screen.getByText("ready content")).toBeInTheDocument();
    expect(screen.queryByTestId("matx-loading")).not.toBeInTheDocument();
  });

  it("shows the MatxLoading fallback while a lazy child is pending", () => {
    const NeverReady = lazy(() => new Promise(() => {}));
    render(
      <MatxSuspense>
        <NeverReady />
      </MatxSuspense>
    );
    expect(screen.getByTestId("matx-loading")).toBeInTheDocument();
  });
});
