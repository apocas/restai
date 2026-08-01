import { render, screen } from "@testing-library/react";
import MatxLayout from "./MatxLayout";

jest.mock("app/hooks/useSettings", () => jest.fn());
import useSettings from "app/hooks/useSettings";

// The barrel drags in the whole layout tree — stub the suspense shell.
jest.mock("app/components", () => ({
  MatxSuspense: ({ children }) => {
    const React = require("react");
    return React.createElement("div", { "data-testid": "suspense" }, children);
  },
}));

// The layout registry lazy-loads Layout1; substitute a marker component.
jest.mock("./index", () => ({
  MatxLayouts: {
    layout1: (props) => {
      const React = require("react");
      return React.createElement("div", { "data-testid": "layout1" }, props.marker);
    },
  },
}));

beforeEach(() => {
  jest.clearAllMocks();
  useSettings.mockReturnValue({ settings: { activeLayout: "layout1" } });
});

describe("MatxLayout", () => {
  it("renders the layout selected by settings.activeLayout inside the suspense shell", () => {
    render(<MatxLayout marker="hello" />);
    const layout = screen.getByTestId("layout1");
    expect(layout).toHaveTextContent("hello");
    expect(screen.getByTestId("suspense")).toContainElement(layout);
  });
});
