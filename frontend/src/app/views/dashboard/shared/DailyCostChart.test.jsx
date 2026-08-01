import { render, screen } from "@testing-library/react";
import DailyCostChart from "./DailyCostChart";

jest.mock("recharts", () => {
  const React = require("react");
  return {
    ResponsiveContainer: ({ children }) =>
      React.createElement("div", { "data-testid": "container" }, children),
    AreaChart: ({ children, data }) =>
      React.createElement(
        "div",
        { "data-testid": "area-chart", "data-rows": JSON.stringify(data) },
        // Drop raw SVG children (<defs> gradients) — only keep component
        // children (Area/XAxis/...) so jsdom doesn't warn about SVG tags.
        React.Children.toArray(children).filter((c) => typeof c.type !== "string")
      ),
    Area: (props) =>
      React.createElement("div", {
        "data-testid": "area",
        "data-key": props.dataKey,
      }),
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
  };
});

const areaKeys = () =>
  screen.getAllByTestId("area").map((a) => a.getAttribute("data-key"));

describe("DailyCostChart", () => {
  it("renders nothing without data", () => {
    const { container } = render(<DailyCostChart data={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when every row has zero cost", () => {
    const { container } = render(
      <DailyCostChart
        data={[{ date: "2026-07-31", input_cost: 0, output_cost: 0, total_cost: 0 }]}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders stacked input/output areas when split costs exist", () => {
    render(
      <DailyCostChart
        data={[
          { date: "2026-07-30", input_cost: 0.5, output_cost: 0.2 },
          { date: "2026-07-31", input_cost: 0.7, output_cost: 0.4 },
        ]}
      />
    );
    expect(screen.getByText("Daily Cost")).toBeInTheDocument();
    expect(areaKeys()).toEqual(["input_cost", "output_cost"]);
  });

  it("falls back to a single total_cost area when only totals exist", () => {
    render(
      <DailyCostChart
        data={[{ date: "2026-07-31", total_cost: 1.25 }]}
      />
    );
    expect(areaKeys()).toEqual(["total_cost"]);
  });

  it("normalizes missing cost fields to zero in the chart rows", () => {
    render(
      <DailyCostChart
        data={[
          { date: "2026-07-30", input_cost: 0.5 },
          { date: "2026-07-31" },
        ]}
      />
    );
    const rows = JSON.parse(
      screen.getByTestId("area-chart").getAttribute("data-rows")
    );
    expect(rows[1]).toEqual({
      date: "2026-07-31",
      input_cost: 0,
      output_cost: 0,
      total_cost: 0,
    });
  });
});
