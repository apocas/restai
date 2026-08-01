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

describe("Embeddings NewChooser", () => {
  it("renders the two creation paths", () => {
    render(<NewChooser />);
    expect(screen.getByText("embeddings.chooser.title")).toBeInTheDocument();
    expect(screen.getByText("embeddings.chooser.ollama")).toBeInTheDocument();
    expect(screen.getByText("embeddings.chooser.manual")).toBeInTheDocument();
  });

  it("Ollama card routes to the shared Ollama pull page", async () => {
    const user = userEvent.setup();
    render(<NewChooser />);
    await user.click(screen.getByText("embeddings.chooser.ollama"));
    // NOTE: intentionally the /llms/ollama page — it handles embedding pulls too.
    expect(mockNavigate).toHaveBeenCalledWith("/llms/ollama");
  });

  it("manual card routes to the manual embedding form", async () => {
    const user = userEvent.setup();
    render(<NewChooser />);
    await user.click(screen.getByText("embeddings.chooser.manual"));
    expect(mockNavigate).toHaveBeenCalledWith("/embeddings/new/manual");
  });
});
