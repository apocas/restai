import { render, screen } from "@testing-library/react";
import DailyTokensChart from "./DailyTokensChart";

// Stub recharts — assert the data the component feeds the chart, not SVG.
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

const data = [
  { date: "2026-07-30", input_tokens: 100, output_tokens: 50 },
  { date: "2026-07-31", input_tokens: 200, output_tokens: 80 },
];

describe("DailyTokensChart", () => {
  it("renders nothing without data", () => {
    const { container } = render(<DailyTokensChart data={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the title and passes the rows to the area chart", () => {
    render(<DailyTokensChart data={data} />);
    expect(screen.getByText("Daily Token Usage")).toBeInTheDocument();

    const chart = screen.getByTestId("area-chart");
    expect(JSON.parse(chart.getAttribute("data-rows"))).toEqual(data);

    // One stacked area per token direction.
    const keys = screen.getAllByTestId("area").map((a) => a.getAttribute("data-key"));
    expect(keys).toEqual(["input_tokens", "output_tokens"]);
  });
});
