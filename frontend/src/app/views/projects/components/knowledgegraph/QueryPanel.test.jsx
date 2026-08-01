import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import QueryPanel from "./QueryPanel";
import api from "app/utils/api";

jest.mock("app/utils/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  delete: jest.fn(),
}));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

const PROJECT = { id: 1, name: "proj" };

const RESULT = {
  answer: "Acme was founded in 1990.",
  entities_matched: ["Acme Corp"],
  sources: ["docs/acme.pdf", "docs/history.txt"],
  source_count: 2,
};

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  api.post.mockResolvedValue(RESULT);
});

const questionBox = () =>
  screen.getByPlaceholderText("e.g. What did the document say about Acme Corp?");

describe("QueryPanel", () => {
  it("disables Ask while the question is blank", async () => {
    const user = userEvent.setup();
    render(<QueryPanel project={PROJECT} />);
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();

    await user.type(questionBox(), "   ");
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
    expect(api.post).not.toHaveBeenCalled();
  });

  it("submits the trimmed question and renders answer, entities and sources", async () => {
    const user = userEvent.setup();
    render(<QueryPanel project={PROJECT} />);

    await user.type(questionBox(), "  What about Acme?  ");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/projects/1/kg/query",
        { question: "What about Acme?" },
        "tok"
      )
    );
    expect(await screen.findByText("Acme was founded in 1990.")).toBeInTheDocument();
    expect(screen.getByText("Entities matched")).toBeInTheDocument();
    expect(screen.getByText("Acme Corp")).toBeInTheDocument();
    expect(screen.getByText("Sources (2)")).toBeInTheDocument();
    expect(screen.getByText("docs/acme.pdf")).toBeInTheDocument();
    expect(screen.getByText("docs/history.txt")).toBeInTheDocument();
  });

  it("omits the entities and sources sections when the result has none", async () => {
    api.post.mockResolvedValue({ answer: "Nothing found.", entities_matched: [], sources: [] });
    const user = userEvent.setup();
    render(<QueryPanel project={PROJECT} />);

    await user.type(questionBox(), "Anything?");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText("Nothing found.")).toBeInTheDocument();
    expect(screen.queryByText("Entities matched")).not.toBeInTheDocument();
    expect(screen.queryByText(/Sources \(/)).not.toBeInTheDocument();
  });

  it("Ctrl+Enter submits from the textarea", async () => {
    const user = userEvent.setup();
    render(<QueryPanel project={PROJECT} />);

    await user.type(questionBox(), "Who is Bob?");
    await user.type(questionBox(), "{Control>}{Enter}{/Control}");

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/projects/1/kg/query",
        { question: "Who is Bob?" },
        "tok"
      )
    );
  });

  it("plain Enter does not submit (it is a multiline field)", async () => {
    const user = userEvent.setup();
    render(<QueryPanel project={PROJECT} />);

    await user.type(questionBox(), "Who is Bob?{Enter}");
    expect(api.post).not.toHaveBeenCalled();
  });
});
