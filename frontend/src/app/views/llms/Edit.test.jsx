import { render, screen } from "@testing-library/react";
import LLMEditView from "./Edit";
import api from "app/utils/api";

jest.mock("app/utils/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  delete: jest.fn(),
}));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

jest.mock("react-router-dom", () => ({
  useParams: () => ({ id: "7" }),
}));

// The heavy inner form (json-edit-react etc.) is covered by its own test.
jest.mock("./components/LLMEdit", () => (props) => {
  const React = require("react");
  return React.createElement("div", { "data-testid": "llm-edit-form" }, props.llm.name);
});

const LLM = {
  id: 7,
  name: "gpt4",
  class_name: "OpenAI",
  privacy: "public",
  context_window: 128000,
  input_cost: 2.5,
  output_cost: 10,
};

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  api.get.mockResolvedValue(LLM);
});

describe("LLM Edit view", () => {
  it("fetches the LLM by route id and renders the hero + edit form", async () => {
    render(<LLMEditView />);
    expect(api.get).toHaveBeenCalledWith("/llms/7", "tok");

    expect(await screen.findByTestId("llm-edit-form")).toHaveTextContent("gpt4");
    // Hero identity line uses the zero-padded id
    expect(screen.getByText("LLM/0007 · EDIT")).toBeInTheDocument();
    // Provider short name resolved from class_name
    expect(screen.getByText("OpenAI")).toBeInTheDocument();
    // Context window formatted as 128K
    expect(screen.getByText("128K ctx")).toBeInTheDocument();
    // Cost stat renders both per-1M rates
    expect(screen.getByText("$2.50/$10.00")).toBeInTheDocument();
  });

  it("does not mount the edit form until the LLM has loaded", async () => {
    let resolveFetch;
    api.get.mockReturnValue(new Promise((res) => (resolveFetch = res)));
    render(<LLMEditView />);
    expect(screen.queryByTestId("llm-edit-form")).not.toBeInTheDocument();

    resolveFetch(LLM);
    expect(await screen.findByTestId("llm-edit-form")).toBeInTheDocument();
  });
});
