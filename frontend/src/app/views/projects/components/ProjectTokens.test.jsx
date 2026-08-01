import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProjectTokens from "./ProjectTokens";

let mockCurrency = "USD";
jest.mock("app/contexts/PlatformContext", () => ({
  usePlatformCapabilities: () => ({ platformCapabilities: { currency: mockCurrency } }),
}));

// Recharts is SVG-measurement heavy under jsdom; stub each export and dump
// the `data` prop so the fill/aggregation logic stays assertable.
jest.mock("recharts", () => {
  const React = require("react");
  const Wrap = ({ children }) => React.createElement("div", null, children);
  return {
    ResponsiveContainer: Wrap,
    AreaChart: ({ children, data }) =>
      React.createElement(
        "div",
        { "data-testid": "area-chart", "data-chart": JSON.stringify(data) },
        children
      ),
    Area: () => null,
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
  };
});

const YEAR = 2026;
const MONTH = 3; // March — 31 days
// Same day-key construction the component uses when filling the series.
const dayKey = (d) => new Date(YEAR, MONTH - 1, d).toISOString().split("T")[0];

const TOKENS = [
  { date: dayKey(5), input_tokens: 1000, output_tokens: 500, input_cost: 0.01, output_cost: 0.02, avg_latency_ms: 1200 },
  { date: dayKey(6), input_tokens: 500, output_tokens: 500, input_cost: 0.005, output_cost: 0.005, avg_latency_ms: 800 },
];

const setYear = jest.fn();
const setMonth = jest.fn();

const renderTokens = (overrides = {}) =>
  render(
    <ProjectTokens
      project={{ id: 7 }}
      tokens={TOKENS}
      selectedYear={YEAR}
      selectedMonth={MONTH}
      setSelectedYear={setYear}
      setSelectedMonth={setMonth}
      {...overrides}
    />
  );

beforeEach(() => {
  jest.clearAllMocks();
  mockCurrency = "USD";
});

describe("ProjectTokens", () => {
  it("renders the month label and stat cards computed from the token series", () => {
    renderTokens();
    expect(screen.getByText("March 2026")).toBeInTheDocument();
    // total tokens 1000+500+500+500
    expect(screen.getByText("2,500")).toBeInTheDocument();
    expect(screen.getByText("Total Tokens")).toBeInTheDocument();
    // total cost 0.01+0.02+0.005+0.005 = 0.04
    expect(screen.getByText("$0.040")).toBeInTheDocument();
    // 2 days with data -> avg daily tokens 1250, avg daily cost 0.02
    expect(screen.getByText("1,250")).toBeInTheDocument();
    expect(screen.getByText("$0.020")).toBeInTheDocument();
    // avg latency over days that reported one: (1200+800)/2 = 1000ms
    expect(screen.getByText("1000ms")).toBeInTheDocument();
  });

  it("formats avg latency above 1s in seconds", () => {
    renderTokens({
      tokens: [{ date: dayKey(5), input_tokens: 1, output_tokens: 1, input_cost: 0, output_cost: 0, avg_latency_ms: 2500 }],
    });
    expect(screen.getByText("2.5s")).toBeInTheDocument();
  });

  it("uses the platform currency symbol", () => {
    mockCurrency = "EUR";
    renderTokens();
    expect(screen.getByText("€0.040")).toBeInTheDocument();
    expect(screen.getByText("€0.020")).toBeInTheDocument();
  });

  it("fills the chart series to every day of the month keeping fetched points", () => {
    renderTokens();
    const charts = screen.getAllByTestId("area-chart");
    expect(charts).toHaveLength(3); // tokens + cost + latency
    const series = JSON.parse(charts[0].getAttribute("data-chart"));
    expect(series).toHaveLength(31);
    const filled = series.find((d) => d.date === dayKey(5));
    expect(filled).toMatchObject({ input_tokens: 1000, output_tokens: 500 });
    expect(series.filter((d) => d.input_tokens === 0)).toHaveLength(29);
  });

  it("previous-month navigation wraps January into December of the previous year", async () => {
    const user = userEvent.setup();
    renderTokens({ selectedMonth: 1 });
    await user.click(
      document.querySelector('svg[data-testid="ChevronLeftIcon"]').closest("button")
    );
    expect(setMonth).toHaveBeenCalledWith(12);
    expect(setYear).toHaveBeenCalledWith(YEAR - 1);
  });

  it("next-month navigation advances within the year", async () => {
    const user = userEvent.setup();
    renderTokens();
    await user.click(
      document.querySelector('svg[data-testid="ChevronRightIcon"]').closest("button")
    );
    expect(setMonth).toHaveBeenCalledWith(MONTH + 1);
    expect(setYear).not.toHaveBeenCalled();
  });

  it("next-month navigation is a no-op on the current month", async () => {
    const user = userEvent.setup();
    const now = new Date();
    renderTokens({ selectedYear: now.getFullYear(), selectedMonth: now.getMonth() + 1 });
    await user.click(
      document.querySelector('svg[data-testid="ChevronRightIcon"]').closest("button")
    );
    expect(setMonth).not.toHaveBeenCalled();
    expect(setYear).not.toHaveBeenCalled();
  });
});
