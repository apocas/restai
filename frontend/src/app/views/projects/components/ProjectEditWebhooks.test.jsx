import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProjectEditWebhooks from "./ProjectEditWebhooks";
import api from "app/utils/api";

jest.setTimeout(20000);

jest.mock("app/utils/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  delete: jest.fn(),
}));
jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (k, fallback) => fallback || k }),
}));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

const PROJECT = { id: 3, name: "bot" };

const setup = (options = {}) => {
  const state = { type: "agent", options };
  const setState = jest.fn();
  const utils = render(
    <ProjectEditWebhooks state={state} setState={setState} project={PROJECT} />
  );
  return { state, setState, ...utils };
};

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok" } });
  api.post.mockResolvedValue({ ok: true });
});

describe("ProjectEditWebhooks", () => {
  it("no URL → OFF pill, disabled fire button, and hint text", () => {
    setup();
    expect(screen.getByText("OFF")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Fire test event" })).toBeDisabled();
    expect(screen.getByText("set a URL above to enable")).toBeInTheDocument();
  });

  it("classifies the endpoint host: public https is LIVE, private IP and http are flagged", () => {
    const { unmount } = setup({ webhook_url: "https://hooks.example.com/x" });
    expect(screen.getByText("LIVE")).toBeInTheDocument();
    expect(screen.getByText("HTTPS · public")).toBeInTheDocument();
    unmount();

    const { unmount: u2 } = setup({ webhook_url: "https://192.168.1.20/hook" });
    expect(screen.getByText("private IP")).toBeInTheDocument();
    expect(screen.getByText("OFF")).toBeInTheDocument();
    u2();

    setup({ webhook_url: "http://hooks.example.com/x" });
    expect(screen.getByText("not HTTPS")).toBeInTheDocument();
  });

  it("empty webhook_events means all four events subscribed by default", () => {
    setup({ webhook_url: "https://hooks.example.com/x" });
    expect(screen.getByText(/4 \/ 4 events · all \(default\)/)).toBeInTheDocument();
    // budget_exceeded also appears in the payload-inspector chrome → AllBy
    expect(screen.getAllByText("budget_exceeded").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("sync_completed")).toBeInTheDocument();
    expect(screen.getByText("eval_completed")).toBeInTheDocument();
    expect(screen.getByText("routine_failed")).toBeInTheDocument();
  });

  it("toggling one event off stores the remaining CSV in webhook_events", async () => {
    const user = userEvent.setup();
    const { state, setState } = setup({ webhook_url: "https://hooks.example.com/x" });

    const switches = screen.getAllByRole("checkbox");
    await user.click(switches[0]); // budget_exceeded off

    expect(setState).toHaveBeenCalledWith({
      ...state,
      options: {
        ...state.options,
        webhook_events: "sync_completed, eval_completed, routine_failed",
      },
    });
  });

  it("re-enabling the last missing event collapses back to empty (= all)", async () => {
    const user = userEvent.setup();
    const { state, setState } = setup({
      webhook_url: "https://hooks.example.com/x",
      webhook_events: "sync_completed, eval_completed, routine_failed",
    });
    expect(screen.getByText(/3 \/ 4 events/)).toBeInTheDocument();

    const switches = screen.getAllByRole("checkbox");
    await user.click(switches[0]); // budget_exceeded back on

    expect(setState).toHaveBeenCalledWith({
      ...state,
      options: { ...state.options, webhook_events: "" },
    });
  });

  it("fire test POSTs the test endpoint and logs a queued entry", async () => {
    const user = userEvent.setup();
    setup({ webhook_url: "https://hooks.example.com/x" });

    await user.click(screen.getByRole("button", { name: "Fire test event" }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/projects/3/webhooks/test", {}, "tok")
    );
    expect(await screen.findByText("queued")).toBeInTheDocument();
    expect(screen.getByText(/synthetic `test` event/)).toBeInTheDocument();
  });

  it("fire test surfaces a refusal reason from the backend", async () => {
    const user = userEvent.setup();
    api.post.mockResolvedValue({ ok: false, reason: "private address refused" });
    setup({ webhook_url: "https://hooks.example.com/x" });

    await user.click(screen.getByRole("button", { name: "Fire test event" }));

    expect(await screen.findByText("REFUSED")).toBeInTheDocument();
    expect(screen.getByText(/private address refused/)).toBeInTheDocument();
  });

  it("fire test network failure logs a NETWORK entry", async () => {
    const user = userEvent.setup();
    api.post.mockRejectedValue(new Error("socket hang up"));
    setup({ webhook_url: "https://hooks.example.com/x" });

    await user.click(screen.getByRole("button", { name: "Fire test event" }));

    expect(await screen.findByText("NETWORK")).toBeInTheDocument();
    expect(screen.getByText(/socket hang up/)).toBeInTheDocument();
  });

  it("rotate secret stores the minted value and warns to capture it", async () => {
    const user = userEvent.setup();
    api.post.mockResolvedValue({ secret: "new-hex-secret" });
    const { state, setState } = setup({ webhook_url: "https://hooks.example.com/x" });

    await user.click(screen.getByRole("button", { name: /rotate/ }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/projects/3/webhooks/rotate-secret", {}, "tok")
    );
    expect(setState).toHaveBeenCalledWith({
      ...state,
      options: { ...state.options, webhook_secret: "new-hex-secret" },
    });
    expect(await screen.findByText(/New secret minted/)).toBeInTheDocument();
  });

  it("payload inspector switches between body and cURL snippets", async () => {
    const user = userEvent.setup();
    setup({ webhook_url: "https://hooks.example.com/x" });

    // default tab: JSON body of the selected (first) event
    expect(screen.getByText(/"event": "budget_exceeded"/)).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "cURL" }));
    expect(screen.getByText(/curl -X POST 'https:\/\/hooks.example.com\/x'/)).toBeInTheDocument();

    // selecting another event card re-targets the inspector
    await user.click(screen.getByText("sync_completed"));
    await user.click(screen.getByRole("tab", { name: "Headers" }));
    expect(screen.getByText(/X-RESTai-Event: sync_completed/)).toBeInTheDocument();
  });

  it("secret signing pill shows when a secret is configured", () => {
    setup({ webhook_url: "https://hooks.example.com/x", webhook_secret: "s3cret" });
    expect(screen.getByText("SIGNING ON")).toBeInTheDocument();
  });
});
