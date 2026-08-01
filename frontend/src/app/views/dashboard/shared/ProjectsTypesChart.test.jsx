import { render, screen } from "@testing-library/react";
import ProjectsTypesChart from "./ProjectsTypesChart";

// Stub the chart library — we only care about the option the component
// computes, not the canvas ECharts would paint.
jest.mock("echarts-for-react", () => {
  const React = require("react");
  return function MockEcharts(props) {
    return React.createElement("div", {
      "data-testid": "echart",
      "data-option": JSON.stringify(props.option),
    });
  };
});

const getOption = () =>
  JSON.parse(screen.getByTestId("echart").getAttribute("data-option"));

describe("ProjectsTypesChart", () => {
  it("renders nothing when there are no projects", () => {
    const { container } = render(<ProjectsTypesChart projects={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("aggregates project counts by type into the pie series", () => {
    render(
      <ProjectsTypesChart
        projects={[
          { type: "rag" },
          { type: "rag" },
          { type: "agent" },
          { type: "block" },
        ]}
      />
    );
    const option = getOption();
    expect(option.series).toHaveLength(1);
    expect(option.series[0].type).toBe("pie");
    expect(option.series[0].data).toEqual(
      expect.arrayContaining([
        { name: "rag", value: 2 },
        { name: "agent", value: 1 },
        { name: "block", value: 1 },
      ])
    );
    expect(option.series[0].data).toHaveLength(3);
  });
});
