import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TeamWallet from "./TeamWallet";
import api from "app/utils/api";
import { toast } from "react-toastify";

jest.mock("app/utils/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  put: jest.fn(),
  delete: jest.fn(),
}));
jest.mock("react-toastify", () => ({
  toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() },
}));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

const mockNavigate = jest.fn();
let mockSearch = "";
jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
  useParams: () => ({ id: "3" }),
  useSearchParams: () => [new URLSearchParams(mockSearch), jest.fn()],
}));

// mui-datatables is heavy under jsdom; stub it to a div that dumps its
// row data so ledger assertions stay possible.
jest.mock("mui-datatables", () => ({
  __esModule: true,
  default: (props) => {
    const React = require("react");
    return React.createElement(
      "div",
      { "data-testid": "ledger-table" },
      JSON.stringify(props.data)
    );
  },
}));

const TEAM = { id: 3, name: "acme", balance: 42 };
const LEDGER = {
  total: 1,
  transactions: [
    {
      created_at: "2026-01-01T00:00:00Z",
      kind: "topup",
      amount: 10,
      balance_after: 52,
      actor_username: "walletadmin",
      description: "seed money",
    },
  ],
};
const PAYCFG_OFF = {
  payments_enabled: false,
  providers: [],
  auto_recharge_providers: [],
  saved_method: null,
  auto_recharge_enabled: false,
};

let teamResp;
let ledgerResp;
let payResp;

beforeEach(() => {
  jest.clearAllMocks();
  mockSearch = "";
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  teamResp = () => Promise.resolve(TEAM);
  ledgerResp = () => Promise.resolve(LEDGER);
  payResp = () => Promise.resolve(PAYCFG_OFF);
  api.get.mockImplementation((path) => {
    if (path === "/teams/3") return teamResp();
    if (path.startsWith("/teams/3/balance/transactions")) return ledgerResp();
    if (path === "/teams/3/payment") return payResp();
    return Promise.resolve({});
  });
  api.put.mockResolvedValue(PAYCFG_OFF);
  api.post.mockResolvedValue({});
  api.delete.mockResolvedValue(PAYCFG_OFF);
  window.confirm = jest.fn(() => true);
});

const renderWallet = async () => {
  render(<TeamWallet />);
  await screen.findByText("acme");
};

describe("TeamWallet", () => {
  it("shows a spinner while the team is loading", () => {
    api.get.mockImplementation(() => new Promise(() => {}));
    render(<TeamWallet />);
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("shows the forbidden message on 403 with a back link to the team", async () => {
    teamResp = () => Promise.reject({ status: 403 });
    const user = userEvent.setup();
    render(<TeamWallet />);

    expect(await screen.findByText("teams.analytics.forbidden")).toBeInTheDocument();
    await user.click(screen.getByText("teams.analytics.backToTeam"));
    expect(mockNavigate).toHaveBeenCalledWith("/team/3");
  });

  it("renders the wallet with an available balance and the fetched ledger", async () => {
    await renderWallet();
    expect(screen.getByText("teams.balance.available")).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith(
      "/teams/3/balance/transactions?start=0&end=50",
      "tok",
      { silent: true }
    );
    const table = await screen.findByTestId("ledger-table");
    await waitFor(() => {
      expect(table).toHaveTextContent("topup");
      expect(table).toHaveTextContent("walletadmin");
      expect(table).toHaveTextContent("seed money");
    });
  });

  it("shows the depleted badge when the balance is zero or below", async () => {
    teamResp = () => Promise.resolve({ ...TEAM, balance: 0 });
    render(<TeamWallet />);
    expect(await screen.findByText("teams.balance.depleted")).toBeInTheDocument();
  });

  it("shows Add Funds only when payments are enabled with providers", async () => {
    await renderWallet();
    expect(screen.queryByRole("button", { name: "teams.payment.addFunds" })).not.toBeInTheDocument();
  });

  it("admin can open the top-up dialog; non-admin has no top-up action", async () => {
    payResp = () => Promise.resolve({ ...PAYCFG_OFF, payments_enabled: true, providers: ["stripe"] });
    const user = userEvent.setup();
    await renderWallet();

    expect(await screen.findByRole("button", { name: "teams.payment.addFunds" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "teams.balance.topUp" }));
    expect(await screen.findByLabelText("teams.balance.addAmount")).toBeInTheDocument();
  });

  it("hides the admin top-up action from non-admins", async () => {
    useAuth.mockReturnValue({ user: { token: "tok", username: "joe", is_admin: false } });
    await renderWallet();
    expect(screen.queryByRole("button", { name: "teams.balance.topUp" })).not.toBeInTheDocument();
  });

  it("offers card setup when auto-recharge is available but no card is saved", async () => {
    payResp = () => Promise.resolve({ ...PAYCFG_OFF, auto_recharge_providers: ["stripe"] });
    const user = userEvent.setup();
    await renderWallet();

    await user.click(await screen.findByRole("button", { name: "teams.payment.saveACard" }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/teams/3/payment/setup?provider=stripe", {}, "tok")
    );
  });

  it("saved card: toggling the switch saves auto-recharge enablement", async () => {
    payResp = () =>
      Promise.resolve({
        ...PAYCFG_OFF,
        auto_recharge_providers: ["stripe"],
        saved_method: { brand: "visa", last4: "4242" },
        auto_recharge_enabled: false,
      });
    const user = userEvent.setup();
    await renderWallet();

    expect(await screen.findByText("visa •••• 4242")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox"));
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith(
        "/teams/3/payment/auto-recharge",
        { enabled: true, threshold: null, amount: null },
        "tok"
      )
    );
    expect(toast.success).toHaveBeenCalledWith("teams.payment.autoRechargeSaved", expect.anything());
  });

  it("saved card: saving threshold/amount sends the parsed numbers", async () => {
    payResp = () =>
      Promise.resolve({
        ...PAYCFG_OFF,
        auto_recharge_providers: ["stripe"],
        saved_method: { brand: "visa", last4: "4242" },
        auto_recharge_enabled: true,
      });
    const user = userEvent.setup();
    await renderWallet();

    await user.type(await screen.findByLabelText("teams.payment.threshold"), "5");
    await user.type(screen.getByLabelText("teams.payment.rechargeAmount"), "20");
    await user.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith(
        "/teams/3/payment/auto-recharge",
        { enabled: true, threshold: 5, amount: 20 },
        "tok"
      )
    );
  });

  it("saved card: removing the payment method confirms then deletes", async () => {
    payResp = () =>
      Promise.resolve({
        ...PAYCFG_OFF,
        auto_recharge_providers: ["stripe"],
        saved_method: { brand: "visa", last4: "4242" },
      });
    const user = userEvent.setup();
    await renderWallet();

    await user.click(await screen.findByRole("button", { name: "teams.payment.removeMethod" }));

    expect(window.confirm).toHaveBeenCalledWith("teams.payment.removeMethodConfirm");
    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith("/teams/3/payment/method", "tok")
    );
    expect(toast.success).toHaveBeenCalledWith("teams.payment.methodRemoved", expect.anything());
  });

  it("handles the ?payment=success provider return: toast + URL cleanup", async () => {
    mockSearch = "payment=success";
    render(<TeamWallet />);

    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith("teams.payment.success", expect.anything())
    );
    expect(mockNavigate).toHaveBeenCalledWith("/team/3/wallet", { replace: true });
  });
});
