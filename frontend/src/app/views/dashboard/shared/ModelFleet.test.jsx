import { render, screen } from "@testing-library/react";
import ModelFleet from "./ModelFleet";

jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (k) => k }),
}));

describe("ModelFleet", () => {
  it("renders nothing when there are no LLMs", () => {
    const { container } = render(<ModelFleet llms={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders a card per model with compacted metrics", () => {
    render(
      <ModelFleet
        llms={[
          { name: "gpt-4o", total_tokens: 1_500_000, request_count: 42 },
          { name: "claude-3-opus", total_tokens: 2_000, request_count: 7 },
        ]}
      />
    );

    expect(screen.getByText("gpt-4o")).toBeInTheDocument();
    expect(screen.getByText("claude-3-opus")).toBeInTheDocument();
    expect(screen.getByText("1.5M")).toBeInTheDocument();
    expect(screen.getByText("2.0K")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
  });

  it("detects known providers from the model name", () => {
    render(
      <ModelFleet
        llms={[
          { name: "gpt-4o", total_tokens: 1 },
          { name: "claude-3-opus", total_tokens: 1 },
          { name: "gemini-1.5-pro", total_tokens: 1 },
          { name: "mistral-large", total_tokens: 1 },
        ]}
      />
    );
    expect(screen.getByText("OpenAI")).toBeInTheDocument();
    expect(screen.getByText("Anthropic")).toBeInTheDocument();
    expect(screen.getByText("Google")).toBeInTheDocument();
    expect(screen.getByText("Mistral")).toBeInTheDocument();
  });

  it("falls back to the Custom label for unknown providers", () => {
    render(<ModelFleet llms={[{ name: "totally-unheard-of", total_tokens: 1 }]} />);
    expect(screen.getByText("Custom")).toBeInTheDocument();
  });

  it("renders two-letter initials in the avatar", () => {
    render(<ModelFleet llms={[{ name: "gpt-4o", total_tokens: 1 }]} />);
    // "gpt-4o" -> letters only -> "GP"
    expect(screen.getByText("GP")).toBeInTheDocument();
  });
});
