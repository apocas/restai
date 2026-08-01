import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import OnboardingChecklist from "./OnboardingChecklist";
import api from "app/utils/api";

jest.mock("app/utils/api", () => ({ get: jest.fn() }));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

const DISMISS_KEY = "restai_onboarding_dismissed";

// Route api.get by path so each test controls the platform state.
function mockPlatform({ llms = [], projects = [], teams = [] }) {
  api.get.mockImplementation((path) => {
    if (path === "/llms") return Promise.resolve(llms);
    if (path === "/projects") return Promise.resolve({ projects });
    if (path === "/teams") return Promise.resolve({ teams });
    return Promise.reject(new Error(`unexpected path ${path}`));
  });
}

const renderChecklist = () =>
  render(
    <MemoryRouter>
      <OnboardingChecklist />
    </MemoryRouter>
  );

beforeEach(() => {
  jest.clearAllMocks();
  localStorage.clear();
  useAuth.mockReturnValue({ user: { is_admin: true, token: "tok" } });
});

describe("OnboardingChecklist", () => {
  it("shows the three steps on a fresh install", async () => {
    mockPlatform({});
    renderChecklist();
    expect(await screen.findByText("Add an LLM")).toBeInTheDocument();
    expect(screen.getByText("Add the LLM to a team")).toBeInTheDocument();
    expect(screen.getByText("Create your first project")).toBeInTheDocument();
  });

  it("renders nothing for non-admin users", () => {
    useAuth.mockReturnValue({ user: { is_admin: false, token: "tok" } });
    mockPlatform({});
    const { container } = renderChecklist();
    expect(container).toBeEmptyDOMElement();
    expect(api.get).not.toHaveBeenCalled();
  });

  it("auto-hides when every step is complete", async () => {
    mockPlatform({
      llms: [{ name: "gpt" }],
      projects: [{ id: 1 }],
      teams: [{ id: 1, llms: ["gpt"] }],
    });
    const { container } = renderChecklist();
    // Wait for the three fetches to settle, then assert it stayed empty.
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("stays hidden once dismissed and persists the dismissal", async () => {
    mockPlatform({});
    renderChecklist();
    await screen.findByText("Add an LLM");

    const dismiss = screen.getByLabelText(/dismiss/i);
    await userEvent.click(dismiss);

    expect(localStorage.getItem(DISMISS_KEY)).toBe("1");
    expect(screen.queryByText("Add an LLM")).not.toBeInTheDocument();
  });

  it("respects a pre-existing dismissal", () => {
    localStorage.setItem(DISMISS_KEY, "1");
    mockPlatform({});
    const { container } = renderChecklist();
    expect(container).toBeEmptyDOMElement();
  });
});
