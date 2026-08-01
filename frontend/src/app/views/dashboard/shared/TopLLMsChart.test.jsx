import { render, screen } from "@testing-library/react";
import TopLLMsChart from "./TopLLMsChart";

jest.mock("recharts", () => {
  const React = require("react");
  return {
    ResponsiveContainer: ({ children }) =>
      React.createElement("div", { "data-testid": "container" }, children),
    BarChart: ({ children, data }) =>
      React.createElement(
        "div",
        { "data-testid": "bar-chart", "data-rows": JSON.stringify(data) },
        // Drop raw SVG children (<defs> gradients) — only keep component
        // children (Bar/XAxis/...) so jsdom doesn't warn about SVG tags.
        React.Children.toArray(children).filter((c) => typeof c.type !== "string")
      ),
    Bar: (props) =>
      React.createElement("div", {
        "data-testid": "bar",
        "data-key": props.dataKey,
      }),
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
  };
});

describe("TopLLMsChart", () => {
  it("renders nothing without data", () => {
    const { container } = render(<TopLLMsChart data={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the title and feeds rows into the token bar", () => {
    const data = [
      { name: "gpt-4", total_tokens: 5000, request_count: 12 },
      { name: "claude", total_tokens: 3000, request_count: 8 },
    ];
    render(<TopLLMsChart data={data} />);

    expect(screen.getByText("Top LLMs")).toBeInTheDocument();
    expect(
      JSON.parse(screen.getByTestId("bar-chart").getAttribute("data-rows"))
    ).toEqual(data);
    expect(screen.getByTestId("bar").getAttribute("data-key")).toBe(
      "total_tokens"
    );
  });
});
