import { render, screen } from "@testing-library/react";
import ProjectsLLMsChart from "./ProjectsLLMsChart";

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

describe("ProjectsLLMsChart", () => {
  it("renders nothing when there are no projects", () => {
    const { container } = render(<ProjectsLLMsChart projects={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when no project has an LLM assigned", () => {
    const { container } = render(
      <ProjectsLLMsChart projects={[{ name: "block-only" }, { llm: null }]} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("counts projects per LLM sorted by usage, skipping LLM-less projects", () => {
    render(
      <ProjectsLLMsChart
        projects={[
          { llm: "gpt-4" },
          { llm: "gpt-4" },
          { llm: "claude" },
          { llm: "gpt-4" },
          { name: "no-llm-block" },
        ]}
      />
    );
    const option = getOption();
    expect(option.series[0].data).toEqual([
      { name: "gpt-4", value: 3 },
      { name: "claude", value: 1 },
    ]);
  });
});
