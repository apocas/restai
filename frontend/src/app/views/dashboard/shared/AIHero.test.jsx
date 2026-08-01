import { render, screen } from "@testing-library/react";
import AIHero from "./AIHero";

jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (k) => k }),
}));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

// The component matches daily rows against today's / yesterday's UTC dates.
const todayKey = new Date().toISOString().slice(0, 10);
const yesterdayKey = new Date(Date.now() - 86400000)
  .toISOString()
  .slice(0, 10);

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { username: "admin" } });
});

describe("AIHero", () => {
  it("greets the logged-in user by name", () => {
    const { container } = render(<AIHero />);
    expect(container.textContent).toContain(", admin");
    // Greeting key comes from the mocked translator.
    expect(container.textContent).toMatch(/dashboard\.hero\.greet/);
  });

  it("omits the name suffix when there is no user", () => {
    useAuth.mockReturnValue(null);
    const { container } = render(<AIHero />);
    expect(container.textContent).not.toContain(", admin");
  });

  it("always shows the operational status chip", () => {
    render(<AIHero />);
    expect(screen.getByText("dashboard.hero.operational")).toBeInTheDocument();
  });

  it("shows the models chip only when modelsCount is provided", () => {
    const { rerender } = render(<AIHero />);
    expect(
      screen.queryByText("dashboard.hero.modelsOnline")
    ).not.toBeInTheDocument();

    rerender(<AIHero modelsCount={3} />);
    expect(screen.getByText("dashboard.hero.modelsOnline")).toBeInTheDocument();
  });

  it("shows today's tokens and the vs-yesterday trend when both days have activity", () => {
    render(
      <AIHero
        dailyTokens={[
          { date: yesterdayKey, input_tokens: 100, output_tokens: 100 },
          { date: todayKey, input_tokens: 300, output_tokens: 100 },
        ]}
      />
    );
    expect(screen.getByText("dashboard.hero.tokensToday")).toBeInTheDocument();
    expect(screen.getByText("dashboard.hero.vsYesterday")).toBeInTheDocument();
  });

  it("hides activity chips on quiet days", () => {
    render(
      <AIHero
        dailyTokens={[
          { date: "2020-01-01", input_tokens: 500, output_tokens: 500 },
        ]}
      />
    );
    expect(
      screen.queryByText("dashboard.hero.tokensToday")
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("dashboard.hero.vsYesterday")
    ).not.toBeInTheDocument();
  });

  it("shows total tokens and latency chips from the summary", () => {
    render(
      <AIHero summary={{ total_tokens: 2_000_000, avg_latency_ms: 1234 }} />
    );
    expect(screen.getByText("dashboard.hero.totalTokens")).toBeInTheDocument();
    expect(screen.getByText("dashboard.hero.latency")).toBeInTheDocument();
  });

  it("hides the latency chip when the summary has no latency", () => {
    render(<AIHero summary={{ total_tokens: 10 }} />);
    expect(
      screen.queryByText("dashboard.hero.latency")
    ).not.toBeInTheDocument();
  });
});
