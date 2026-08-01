import { render, screen } from "@testing-library/react";
import ProjectsStats from "./ProjectsStats";

jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (k) => k }),
}));

describe("ProjectsStats", () => {
  it("renders only the three base cards without a summary", () => {
    render(<ProjectsStats projects={[{ type: "rag" }, { type: "agent" }]} />);

    expect(screen.getByText("dashboard.stats.projects")).toBeInTheDocument();
    expect(screen.getByText("dashboard.stats.users")).toBeInTheDocument();
    expect(screen.getByText("dashboard.stats.teams")).toBeInTheDocument();
    // Tokens / cost / latency cards need summary data.
    expect(screen.queryByText("dashboard.stats.tokens")).not.toBeInTheDocument();
    expect(screen.queryByText("dashboard.stats.cost")).not.toBeInTheDocument();
    expect(
      screen.queryByText("dashboard.stats.avgLatency")
    ).not.toBeInTheDocument();

    // Project count falls back to the projects array length.
    expect(screen.getByText("2")).toBeInTheDocument();
    // Users / teams unknown without summary.
    expect(screen.getAllByText("—")).toHaveLength(2);
  });

  it("renders totals from the summary payload", () => {
    render(
      <ProjectsStats
        projects={[]}
        summary={{
          total_projects: 12,
          total_users: 5,
          total_teams: 3,
          total_tokens: 1_500_000,
          total_cost: 12.345,
        }}
      />
    );

    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    // formatNumber compacts to one decimal + suffix.
    expect(screen.getByText("1.5M")).toBeInTheDocument();
    expect(screen.getByText("$12.35")).toBeInTheDocument();
  });

  it("uses the EUR symbol when currency is EUR", () => {
    render(
      <ProjectsStats
        summary={{
          total_projects: 1,
          total_users: 1,
          total_teams: 1,
          total_tokens: 10,
          total_cost: 2,
        }}
        currency="EUR"
      />
    );
    expect(screen.getByText("€2.00")).toBeInTheDocument();
  });

  it("shows the latency card formatted in seconds above 1000ms", () => {
    render(
      <ProjectsStats
        summary={{
          total_projects: 1,
          total_users: 1,
          total_teams: 1,
          total_tokens: 0,
          total_cost: 0,
          avg_latency_ms: 1500,
        }}
      />
    );
    expect(screen.getByText("dashboard.stats.avgLatency")).toBeInTheDocument();
    expect(screen.getByText("1.5s")).toBeInTheDocument();
  });

  it("shows the latency card in milliseconds below 1000ms", () => {
    render(
      <ProjectsStats
        summary={{
          total_projects: 1,
          total_users: 1,
          total_teams: 1,
          total_tokens: 0,
          total_cost: 0,
          avg_latency_ms: 250,
        }}
      />
    );
    expect(screen.getByText("250ms")).toBeInTheDocument();
  });

  it("derives average latency from dailyTokens when summary lacks it", () => {
    render(
      <ProjectsStats
        summary={{
          total_projects: 1,
          total_users: 1,
          total_teams: 1,
          total_tokens: 0,
          total_cost: 0,
        }}
        dailyTokens={[
          { date: "2026-07-30", avg_latency_ms: 100 },
          { date: "2026-07-31", avg_latency_ms: 300 },
          // Zero-latency (quiet) days are filtered out of the average.
          { date: "2026-08-01", avg_latency_ms: 0 },
        ]}
      />
    );
    expect(screen.getByText("200ms")).toBeInTheDocument();
  });

  it("renders the project type breakdown legend with counts", () => {
    render(
      <ProjectsStats
        projects={[
          { type: "rag" },
          { type: "rag" },
          { type: "agent" },
          { type: "block" },
        ]}
      />
    );
    // Legend labels are the (mock-translated) keys, uppercased, plus counts.
    expect(screen.getByText("PROJECTS.TYPE.RAG 2")).toBeInTheDocument();
    expect(screen.getByText("PROJECTS.TYPE.AGENT 1")).toBeInTheDocument();
    expect(screen.getByText("PROJECTS.TYPE.BLOCK 1")).toBeInTheDocument();
  });
});
