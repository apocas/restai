import { render, screen } from "@testing-library/react";
import ActivityPulse from "./ActivityPulse";

jest.mock("echarts-for-react", () => {
  const React = require("react");
  return function MockEcharts(props) {
    return React.createElement("div", {
      "data-testid": "echart",
      "data-option": JSON.stringify(props.option),
    });
  };
});

const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const dayName = (iso) => DAY_NAMES[new Date(iso + "T00:00:00").getDay()];

// 14 consecutive days: previous week at 100 tokens/day, last week at 200
// tokens/day (one 500-token peak) => +100%-ish trend, 14-day streak.
function makeData() {
  const rows = [];
  for (let i = 0; i < 14; i++) {
    const day = String(18 + i).padStart(2, "0");
    const total = i < 7 ? 100 : 200;
    rows.push({ date: `2026-07-${day}`, input_tokens: total, output_tokens: 0 });
  }
  rows[10].input_tokens = 500; // peak day within the last 7
  return rows;
}

const getOption = () =>
  JSON.parse(screen.getByTestId("echart").getAttribute("data-option"));

describe("ActivityPulse", () => {
  it("renders nothing without data", () => {
    const { container } = render(<ActivityPulse data={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the card with rose chart limited to the last 7 days", () => {
    render(<ActivityPulse data={makeData()} />);
    expect(screen.getByText("Activity Pulse")).toBeInTheDocument();
    expect(screen.getByText("30-day activity")).toBeInTheDocument();

    const option = getOption();
    expect(option.series[0].data).toHaveLength(7);
    // Rose petals carry the weekday name + daily total.
    expect(option.series[0].data[0].name).toBe(dayName("2026-07-25"));
    expect(option.series[0].data[0].value).toBe(200);
  });

  it("computes peak day, trend percentage and streak insights", () => {
    render(<ActivityPulse data={makeData()} />);

    // Peak = the 500-token day (index 10 => 2026-07-28).
    expect(screen.getByText("Peak")).toBeInTheDocument();
    expect(screen.getByText(dayName("2026-07-28"))).toBeInTheDocument();

    // last7 = 6*200 + 500 = 1700 vs prev7 = 700 => +143%.
    expect(screen.getByText("Trend")).toBeInTheDocument();
    expect(screen.getByText("+143%")).toBeInTheDocument();

    // Every day has activity => 14-day streak.
    expect(screen.getByText("Streak")).toBeInTheDocument();
    expect(screen.getByText("14d")).toBeInTheDocument();
  });

  it("shows a negative trend and no streak pill after a quiet day", () => {
    const data = makeData().map((d, i) =>
      i < 7
        ? d
        : { ...d, input_tokens: i === 13 ? 0 : 50 } // last day silent
    );
    render(<ActivityPulse data={data} />);

    // last7 = 6*50 = 300 vs prev7 = 700 => -57%.
    expect(screen.getByText("-57%")).toBeInTheDocument();
    // Streak broken by the trailing zero day => pill hidden (streak <= 1).
    expect(screen.queryByText("Streak")).not.toBeInTheDocument();
  });
});
