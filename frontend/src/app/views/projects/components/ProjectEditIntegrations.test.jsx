import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProjectEditIntegrations from "./ProjectEditIntegrations";
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

// The webhooks panel has its own suite — stub it here.
jest.mock("./ProjectEditWebhooks", () => {
  const React = require("react");
  return function MockWebhooks() {
    return React.createElement("div", { "data-testid": "webhooks-panel" });
  };
});

const PROJECT = { id: 3, name: "bot", type: "agent" };

const setup = (options = {}, project = PROJECT) => {
  const state = { type: "agent", options };
  const setState = jest.fn();
  const utils = render(
    <ProjectEditIntegrations
      state={state}
      setState={setState}
      handleChange={jest.fn()}
      project={project}
    />
  );
  return { state, setState, ...utils };
};

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok" } });
  api.post.mockResolvedValue({ ok: true });
});

describe("ProjectEditIntegrations", () => {
  it("renders all five integration sections plus the webhooks panel", () => {
    setup();
    expect(screen.getByText("Telegram")).toBeInTheDocument();
    expect(screen.getByText("Slack")).toBeInTheDocument();
    expect(screen.getByText("WhatsApp Business Cloud")).toBeInTheDocument();
    expect(screen.getByText("Email · SMTP")).toBeInTheDocument();
    expect(screen.getByText("SMS · Twilio")).toBeInTheDocument();
    expect(screen.getByTestId("webhooks-panel")).toBeInTheDocument();
  });

  it("LIVE/OFF pills reflect configured credentials per section", () => {
    setup({
      telegram_token: "123:abc", // telegram live
      smtp_host: "smtp.x.com", // smtp live
      // slack, whatsapp, sms unconfigured
    });
    expect(screen.getAllByText("LIVE")).toHaveLength(2);
    expect(screen.getAllByText("OFF")).toHaveLength(3);
  });

  it("shows the shared inbound WhatsApp webhook URL (read-only)", () => {
    setup();
    const url = `${window.location.origin}/webhooks/whatsapp`;
    expect(screen.getByDisplayValue(url)).toBeInTheDocument();
    expect(screen.getByDisplayValue(url)).toHaveAttribute("readonly");
  });

  it("editing an option field writes it into state.options", () => {
    const { state, setState } = setup();
    fireEvent.change(screen.getByPlaceholderText("100000000000000"), {
      target: { value: "555" },
    });
    expect(setState).toHaveBeenCalledWith({
      ...state,
      options: { ...state.options, whatsapp_phone_number_id: "555" },
    });
  });

  it("telegram default chat id parses to int, and clears to null", () => {
    const { state, setState } = setup({ telegram_default_chat_id: 42 });
    const field = screen.getByPlaceholderText("123456789");
    fireEvent.change(field, { target: { value: "777" } });
    expect(setState).toHaveBeenCalledWith({
      ...state,
      options: { ...state.options, telegram_default_chat_id: 777 },
    });

    fireEvent.change(field, { target: { value: "" } });
    expect(setState).toHaveBeenLastCalledWith({
      ...state,
      options: { ...state.options, telegram_default_chat_id: null },
    });
  });

  it("WhatsApp test button is disabled until phone id + access token are set", () => {
    setup();
    expect(screen.getByRole("button", { name: "Test connection" })).toBeDisabled();
  });

  it("WhatsApp test success POSTs and renders the success alert", async () => {
    const user = userEvent.setup();
    api.post.mockResolvedValue({
      ok: true,
      display_name: "Acme",
      verified_name: "Acme Inc",
      quality_rating: "GREEN",
    });
    setup({ whatsapp_phone_number_id: "100", whatsapp_access_token: "tokk" });

    const btn = screen.getByRole("button", { name: "Test connection" });
    expect(btn).toBeEnabled();
    await user.click(btn);

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/projects/3/whatsapp/test", {}, "tok")
    );
    expect(
      await screen.findByText("OK · display: Acme · verified: Acme Inc · quality: GREEN")
    ).toBeInTheDocument();
  });

  it("WhatsApp test failure renders the error alert", async () => {
    const user = userEvent.setup();
    api.post.mockRejectedValue(new Error("boom"));
    setup({ whatsapp_phone_number_id: "100", whatsapp_access_token: "tokk" });

    await user.click(screen.getByRole("button", { name: "Test connection" }));

    expect(await screen.findByText("Error: boom")).toBeInTheDocument();
  });

  it("upstream API error surfaces the ok:false payload as an error alert", async () => {
    const user = userEvent.setup();
    api.post.mockResolvedValue({ ok: false, error: "invalid access token" });
    setup({ whatsapp_phone_number_id: "100", whatsapp_access_token: "bad" });

    await user.click(screen.getByRole("button", { name: "Test connection" }));

    expect(await screen.findByText("Error: invalid access token")).toBeInTheDocument();
  });
});
