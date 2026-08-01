import { render, screen, waitFor } from "@testing-library/react";
import UserActivity from "./UserActivity";
import api from "app/utils/api";
import useAuth from "app/hooks/useAuth";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";

jest.mock("app/utils/api", () => ({ get: jest.fn() }));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));
jest.mock("app/hooks/useAuth", () => jest.fn());
jest.mock("app/contexts/PlatformContext", () => ({ usePlatformCapabilities: jest.fn() }));
// Recharts is SVG/measurement heavy — stub it out; we only assert on our own DOM.
jest.mock("recharts", () => {
  const React = require("react");
  const Stub = ({ children }) => React.createElement("div", null, children);
  return {
    ResponsiveContainer: Stub,
    AreaChart: Stub,
    BarChart: Stub,
    Area: () => null,
    Bar: () => null,
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
  };
});

const STATS = {
  summary: {
    total_requests: 1234,
    total_tokens: 56789,
    total_cost: 1.2345,
    avg_latency_ms: 250,
    total_conversations: 42,
  },
  daily: [{ date: "2026-07-01", requests: 10 }],
  hourly: [{ hour: 9, requests: 5 }],
  top_projects: [
    { project_id: 1, project_name: "support-bot", requests: 900, tokens: 40000 },
  ],
};

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin" } });
  usePlatformCapabilities.mockReturnValue({ platformCapabilities: { currency: "USD" } });
  api.get.mockResolvedValue(STATS);
});

describe("UserActivity", () => {
  it("fetches 30-day stats for the user and renders the summary cards", async () => {
    render(<UserActivity user={{ id: 7 }} />);

    expect(await screen.findByText("users.userActivity.title")).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith("/statistics/users/7?days=30", "tok", { silent: true });

    expect(screen.getByText("1,234")).toBeInTheDocument(); // requests
    expect(screen.getByText("56,789")).toBeInTheDocument(); // tokens
    expect(screen.getByText("$1.234")).toBeInTheDocument(); // cost, 3 decimals
    expect(screen.getByText("250ms")).toBeInTheDocument(); // latency in ms
    expect(screen.getByText("42")).toBeInTheDocument(); // conversations

    // Section headers + top-projects table.
    expect(screen.getByText("users.userActivity.dailyActivity")).toBeInTheDocument();
    expect(screen.getByText("users.userActivity.peakHours")).toBeInTheDocument();
    expect(screen.getByText("support-bot")).toBeInTheDocument();
    expect(screen.getByText("900")).toBeInTheDocument();
    expect(screen.getByText("40,000")).toBeInTheDocument();
  });

  it("formats latency above one second in seconds", async () => {
    api.get.mockResolvedValue({ summary: { ...STATS.summary, avg_latency_ms: 2500 } });
    render(<UserActivity user={{ id: 7 }} />);

    expect(await screen.findByText("2.5s")).toBeInTheDocument();
  });

  it("uses the platform currency symbol", async () => {
    usePlatformCapabilities.mockReturnValue({ platformCapabilities: { currency: "EUR" } });
    render(<UserActivity user={{ id: 7 }} />);

    expect(await screen.findByText("€1.234")).toBeInTheDocument();
  });

  it("renders nothing when the fetch fails", async () => {
    api.get.mockRejectedValue(new Error("boom"));
    const { container } = render(<UserActivity user={{ id: 7 }} />);

    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("skips the fetch entirely when the user has no id", () => {
    const { container } = render(<UserActivity user={{}} />);

    expect(api.get).not.toHaveBeenCalled();
    expect(container).toBeEmptyDOMElement();
  });
});
