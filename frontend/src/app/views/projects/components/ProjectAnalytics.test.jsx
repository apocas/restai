import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProjectAnalytics from "./ProjectAnalytics";
import api from "app/utils/api";

jest.mock("app/utils/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  delete: jest.fn(),
}));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

jest.mock("recharts", () => {
  const React = require("react");
  const Wrap = ({ children }) => React.createElement("div", null, children);
  const chart = (testid) =>
    function Chart({ children, data }) {
      return React.createElement(
        "div",
        { "data-testid": testid, "data-chart": JSON.stringify(data) },
        children
      );
    };
  return {
    ResponsiveContainer: Wrap,
    AreaChart: chart("area-chart"),
    BarChart: chart("bar-chart"),
    Area: () => null,
    Bar: () => null,
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
  };
});

const now = new Date();
const YEAR = now.getFullYear();
const MONTH = now.getMonth() + 1;
const DAYS_IN_MONTH = new Date(YEAR, MONTH, 0).getDate();
// Same day-key construction the component uses for the filled series.
const day5 = new Date(YEAR, MONTH - 1, 5).toISOString().split("T")[0];

const DATA = {
  summary: {
    total_conversations: 42,
    total_messages: 321,
    avg_messages_per_conversation: 7.6,
    avg_latency_ms: 1500,
  },
  daily: [{ date: day5, conversations: 3, messages: 9 }],
  hourly: [{ hour: 0, messages: 4 }],
  top_users: [{ user_id: 1, username: "alice", messages: 12 }],
  status_breakdown: [
    { status: "success", count: 300 },
    { status: "rate_limit", count: 21 },
  ],
  latency_buckets: [
    { bucket: "0-100ms", count: 5 },
    { bucket: "100-500ms", count: 0 },
  ],
  llm_breakdown: [{ llm: "gpt4", messages: 100, tokens: 5000, cost: 1.2 }],
};

let analyticsResp;

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin" } });
  analyticsResp = () => Promise.resolve(DATA);
  api.get.mockImplementation((path) => {
    if (path.includes("/analytics/conversations")) return analyticsResp();
    return Promise.resolve({});
  });
});

const renderAnalytics = async () => {
  render(<ProjectAnalytics project={{ id: 7 }} />);
  await screen.findByText("projects.edit.analytics.title");
};

describe("ProjectAnalytics", () => {
  it("fetches the current month silently and renders the stat cards", async () => {
    await renderAnalytics();
    expect(api.get).toHaveBeenCalledWith(
      `/projects/7/analytics/conversations?year=${YEAR}&month=${MONTH}`,
      "tok",
      { silent: true }
    );
    expect(screen.getByText("42")).toBeInTheDocument(); // conversations
    expect(screen.getByText("321")).toBeInTheDocument(); // messages
    expect(screen.getByText("7.6")).toBeInTheDocument(); // avg msgs/conv
    expect(screen.getByText("1.5s")).toBeInTheDocument(); // avg latency > 1s
  });

  it("renders nothing until data arrives and nothing on fetch failure", async () => {
    analyticsResp = () => Promise.reject({ status: 500 });
    const { container } = render(<ProjectAnalytics project={{ id: 7 }} />);
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("fills the daily activity series to every day of the month", async () => {
    await renderAnalytics();
    const chart = screen.getByTestId("area-chart");
    const series = JSON.parse(chart.getAttribute("data-chart"));
    expect(series).toHaveLength(DAYS_IN_MONTH);
    expect(series.find((d) => d.date === day5)).toMatchObject({ conversations: 3, messages: 9 });
    expect(series.filter((d) => d.messages === 0)).toHaveLength(DAYS_IN_MONTH - 1);
  });

  it("wires hourly and latency data into the bar charts", async () => {
    await renderAnalytics();
    const bars = screen.getAllByTestId("bar-chart");
    expect(bars).toHaveLength(2); // peak hours + latency distribution
    expect(JSON.parse(bars[0].getAttribute("data-chart"))).toEqual(DATA.hourly);
    expect(JSON.parse(bars[1].getAttribute("data-chart"))).toEqual(DATA.latency_buckets);
  });

  it("renders the status breakdown with underscores humanized", async () => {
    await renderAnalytics();
    expect(screen.getByText("success")).toBeInTheDocument();
    expect(screen.getByText("rate limit")).toBeInTheDocument();
    expect(screen.getByText("300")).toBeInTheDocument();
    expect(screen.getByText("21")).toBeInTheDocument();
  });

  it("renders the LLM breakdown table with formatted token counts", async () => {
    await renderAnalytics();
    expect(screen.getByText("gpt4")).toBeInTheDocument();
    expect(screen.getByText("100")).toBeInTheDocument();
    expect(screen.getByText("5,000")).toBeInTheDocument();
  });

  it("renders top users", async () => {
    await renderAnalytics();
    expect(screen.getByText("alice")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("omits drill-down sections when the data is absent or all-zero", async () => {
    analyticsResp = () =>
      Promise.resolve({
        summary: DATA.summary,
        daily: [],
        hourly: [],
        latency_buckets: [{ bucket: "0-100ms", count: 0 }],
      });
    await renderAnalytics();
    expect(screen.queryByText("projects.edit.analytics.outcomeBreakdown")).not.toBeInTheDocument();
    expect(screen.queryByText("projects.edit.analytics.latencyDistribution")).not.toBeInTheDocument();
    expect(screen.queryByText("projects.edit.analytics.llmUsage")).not.toBeInTheDocument();
    expect(screen.queryByText("projects.edit.analytics.topUsers")).not.toBeInTheDocument();
  });

  it("month navigation refetches the previous month", async () => {
    const user = userEvent.setup();
    await renderAnalytics();
    await user.click(
      document.querySelector('svg[data-testid="ChevronLeftIcon"]').closest("button")
    );
    const prevYear = MONTH === 1 ? YEAR - 1 : YEAR;
    const prevMonth = MONTH === 1 ? 12 : MONTH - 1;
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(
        `/projects/7/analytics/conversations?year=${prevYear}&month=${prevMonth}`,
        "tok",
        { silent: true }
      )
    );
  });
});
