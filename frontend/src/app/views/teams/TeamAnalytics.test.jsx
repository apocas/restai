import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TeamAnalytics from "./TeamAnalytics";
import api from "app/utils/api";

jest.mock("app/utils/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  delete: jest.fn(),
}));
jest.mock("react-toastify", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
  useParams: () => ({ id: "4" }),
}));

// Recharts is SVG-measurement heavy under jsdom; stub each export and dump
// the `data` prop so aggregation logic stays assertable.
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
    PieChart: Wrap,
    Pie: ({ data }) =>
      React.createElement("div", {
        "data-testid": "pie",
        "data-chart": JSON.stringify(data),
      }),
    Cell: () => null,
    Area: () => null,
    Bar: () => null,
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
  };
});

jest.mock("./MemberBudgetDialog", () => (props) => {
  const React = require("react");
  if (!props.open) return null;
  return React.createElement(
    "div",
    { "data-testid": "budget-dialog" },
    props.member?.username,
    React.createElement("button", { onClick: () => props.onSaved && props.onSaved() }, "mock-save")
  );
});

const now = new Date();
const YEAR = now.getFullYear();
const MONTH = now.getMonth() + 1;
const DAYS_IN_MONTH = new Date(YEAR, MONTH, 0).getDate();
// Same day-key construction the component uses for the filled series.
const day5 = new Date(Date.UTC(YEAR, MONTH - 1, 5)).toISOString().split("T")[0];

const DATA = {
  team: { id: 4, name: "acme" },
  summary: {
    total_cost: 12.5,
    total_tokens: 1500000,
    total_input_tokens: 1000000,
    total_output_tokens: 500000,
    total_messages: 320,
    total_conversations: 40,
    active_users: 3,
    active_projects: 2,
    direct_access_cost: 1.2,
    direct_access_messages: 10,
    avg_latency_ms: 1500,
  },
  budget: { unlimited: false, budget: 25, spending_month: 12.5 },
  balance: 6,
  daily: [{ date: day5, input_tokens: 10, output_tokens: 5, tokens: 15, cost: 1, messages: 2 }],
  per_project: [
    { project_id: 1, project: "proj1", messages: 100, tokens: 1000, cost: 10 },
    { project_id: null, project: null, messages: 5, tokens: 50, cost: 2.5 },
  ],
  per_llm: [
    { llm: "gpt4", messages: 90, tokens: 900, cost: 11 },
    { llm: "freebie", messages: 10, tokens: 100, cost: 0 },
  ],
  per_user: [
    { user_id: 2, username: "bob", messages: 60, tokens: 600, cost: 6, budget: 8 },
    { user_id: null, username: null, messages: 1, tokens: 10, cost: 0.1, budget: null },
  ],
  status_breakdown: [
    { status: "success", count: 300 },
    { status: "rate_limit", count: 20 },
  ],
  latency_buckets: [{ bucket: "0-100ms", count: 5 }],
  hourly: [{ hour: 0, messages: 3 }],
};

let analyticsResp;

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  analyticsResp = () => Promise.resolve(DATA);
  api.get.mockImplementation((path) => {
    if (path.startsWith("/teams/4/analytics")) return analyticsResp();
    return Promise.resolve({});
  });
});

const renderAnalytics = async () => {
  render(<TeamAnalytics />);
  await screen.findByText("teams.analytics.title");
};

describe("TeamAnalytics", () => {
  it("shows a spinner while loading", () => {
    analyticsResp = () => new Promise(() => {});
    render(<TeamAnalytics />);
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("fetches the current month and renders the stat cards", async () => {
    await renderAnalytics();
    expect(api.get).toHaveBeenCalledWith(
      `/teams/4/analytics?year=${YEAR}&month=${MONTH}`,
      "tok",
      { silent: true }
    );
    expect(screen.getAllByText("$12.50").length).toBeGreaterThanOrEqual(1); // total cost + gauge
    expect(screen.getByText("1.50M")).toBeInTheDocument(); // total tokens
    expect(screen.getByText("320")).toBeInTheDocument(); // messages
    expect(screen.getByText("1.5s")).toBeInTheDocument(); // avg latency
    expect(screen.getByText("$1.20")).toBeInTheDocument(); // direct access cost
  });

  it("renders the budget gauge with spend/cap percentage and available balance", async () => {
    await renderAnalytics();
    expect(screen.getByText("/ $25.00 (50%)")).toBeInTheDocument();
    expect(screen.getByText("teams.balance.available")).toBeInTheDocument();
  });

  it("shows unlimited budget and depleted balance variants", async () => {
    analyticsResp = () =>
      Promise.resolve({ ...DATA, budget: { unlimited: true, spending_month: 3 }, balance: 0 });
    await renderAnalytics();
    expect(screen.getByText(/teams.analytics.unlimited/)).toBeInTheDocument();
    expect(screen.getByText("teams.balance.depleted")).toBeInTheDocument();
  });

  it("403 renders the forbidden state with a working back link", async () => {
    analyticsResp = () => Promise.reject({ status: 403 });
    const user = userEvent.setup();
    render(<TeamAnalytics />);
    expect(await screen.findByText("teams.analytics.forbidden")).toBeInTheDocument();
    await user.click(screen.getByText("teams.analytics.backToTeam"));
    expect(mockNavigate).toHaveBeenCalledWith("/team/4");
  });

  it("other errors render the generic load-error state", async () => {
    analyticsResp = () => Promise.reject({ status: 500 });
    render(<TeamAnalytics />);
    expect(await screen.findByText("teams.analytics.loadError")).toBeInTheDocument();
  });

  it("fills the daily series to every day of the month, keeping fetched points", async () => {
    await renderAnalytics();
    const charts = screen.getAllByTestId("area-chart");
    expect(charts).toHaveLength(2); // cost + tokens trends
    const series = JSON.parse(charts[0].getAttribute("data-chart"));
    expect(series).toHaveLength(DAYS_IN_MONTH);
    const filled = series.find((d) => d.date === day5);
    expect(filled).toMatchObject({ cost: 1, messages: 2 });
    // untouched days are zero-filled
    const zeroDays = series.filter((d) => d.cost === 0);
    expect(zeroDays).toHaveLength(DAYS_IN_MONTH - 1);
  });

  it("project breakdown lists projects, maps null to direct access, and shows cost share", async () => {
    await renderAnalytics();
    expect(screen.getByText("proj1")).toBeInTheDocument();
    expect(screen.getByText("teams.view.tx.directAccess")).toBeInTheDocument();
    expect(screen.getByText("80%")).toBeInTheDocument(); // 10 / 12.5
  });

  it("LLM section: pie only includes non-zero-cost LLMs, table lists all", async () => {
    await renderAnalytics();
    const pie = JSON.parse(screen.getByTestId("pie").getAttribute("data-chart"));
    expect(pie).toEqual([{ name: "gpt4", value: 11 }]);
    expect(screen.getByText("gpt4")).toBeInTheDocument();
    expect(screen.getByText("freebie")).toBeInTheDocument();
  });

  it("user breakdown shows caps, unknown users, and opens the cap editor which refetches on save", async () => {
    const user = userEvent.setup();
    await renderAnalytics();

    expect(screen.getByText("bob")).toBeInTheDocument();
    expect(screen.getByText("$8.00")).toBeInTheDocument();
    expect(screen.getByText("teams.analytics.unknownUser")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument(); // uncapped row

    // Only bob's row (user_id set, current month) gets the edit icon.
    const editIcons = document.querySelectorAll('svg[data-testid="EditIcon"]');
    expect(editIcons).toHaveLength(1);
    await user.click(editIcons[0].closest("button"));

    const dialog = screen.getByTestId("budget-dialog");
    expect(within(dialog).getByText("bob")).toBeInTheDocument();

    await user.click(within(dialog).getByText("mock-save"));
    await waitFor(() =>
      expect(api.get.mock.calls.filter(([p]) => p.startsWith("/teams/4/analytics"))).toHaveLength(2)
    );
  });

  it("renders status breakdown and reliability charts", async () => {
    await renderAnalytics();
    expect(screen.getByText("success")).toBeInTheDocument();
    expect(screen.getByText("rate limit")).toBeInTheDocument();
    expect(screen.getByText("300")).toBeInTheDocument();

    const bars = screen.getAllByTestId("bar-chart");
    expect(bars).toHaveLength(2); // latency + hourly
    expect(JSON.parse(bars[0].getAttribute("data-chart"))).toEqual(DATA.latency_buckets);
    expect(JSON.parse(bars[1].getAttribute("data-chart"))).toEqual(DATA.hourly);
  });

  it("month navigation refetches the previous month and disables next on the current month", async () => {
    const user = userEvent.setup();
    await renderAnalytics();

    const nextBtn = document.querySelector('svg[data-testid="ChevronRightIcon"]').closest("button");
    expect(nextBtn).toBeDisabled();

    const prevBtn = document.querySelector('svg[data-testid="ChevronLeftIcon"]').closest("button");
    await user.click(prevBtn);

    const prevYear = MONTH === 1 ? YEAR - 1 : YEAR;
    const prevMonth = MONTH === 1 ? 12 : MONTH - 1;
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(
        `/teams/4/analytics?year=${prevYear}&month=${prevMonth}`,
        "tok",
        { silent: true }
      )
    );
  });
});
