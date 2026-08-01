import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import NewChooser from "./NewChooser";

jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
  NavLink: ({ children, to }) => {
    const React = require("react");
    return React.createElement("a", { href: to }, children);
  },
}));

beforeEach(() => {
  jest.clearAllMocks();
});

describe("LLMs NewChooser", () => {
  it("renders the two creation paths", () => {
    render(<NewChooser />);
    expect(screen.getByText("llms.chooser.title")).toBeInTheDocument();
    expect(screen.getByText("llms.chooser.ollama")).toBeInTheDocument();
    expect(screen.getByText("llms.chooser.manual")).toBeInTheDocument();
    // Ollama card carries the "fastest" badge
    expect(screen.getByText("llms.chooser.fastest")).toBeInTheDocument();
  });

  it("navigates to the Ollama flow when the Ollama card is clicked", async () => {
    const user = userEvent.setup();
    render(<NewChooser />);
    await user.click(screen.getByText("llms.chooser.ollama"));
    expect(mockNavigate).toHaveBeenCalledWith("/llms/ollama");
  });

  it("navigates to the manual flow when the manual card is clicked", async () => {
    const user = userEvent.setup();
    render(<NewChooser />);
    await user.click(screen.getByText("llms.chooser.manual"));
    expect(mockNavigate).toHaveBeenCalledWith("/llms/new/manual");
  });
});
