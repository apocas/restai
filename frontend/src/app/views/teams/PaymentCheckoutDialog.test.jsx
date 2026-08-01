import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PaymentCheckoutDialog from "./PaymentCheckoutDialog";
import api from "app/utils/api";
import useAuth from "app/hooks/useAuth";

jest.mock("app/utils/api", () => ({ post: jest.fn() }));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));
jest.mock("app/hooks/useAuth", () => jest.fn());

let locationMock;
const renderDialog = (over = {}) => {
  const props = {
    open: true,
    onClose: jest.fn(),
    teamId: 4,
    providers: ["stripe"],
    autoRechargeProviders: [],
    ...over,
  };
  render(<PaymentCheckoutDialog {...props} />);
  return props;
};

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok" } });
  api.post.mockResolvedValue({ redirect_url: "https://pay.example/session" });
  locationMock = { href: "" };
  delete window.location;
  window.location = locationMock;
});

describe("PaymentCheckoutDialog", () => {
  it("disables Continue until a positive amount is entered", async () => {
    const user = userEvent.setup();
    renderDialog();

    const cont = screen.getByRole("button", { name: "teams.payment.continue" });
    expect(cont).toBeDisabled();
    await user.type(screen.getByLabelText("teams.payment.amount"), "20");
    expect(cont).toBeEnabled();
  });

  it("hides the provider picker with a single provider", () => {
    renderDialog({ providers: ["stripe"] });
    expect(screen.queryByText("teams.payment.provider")).not.toBeInTheDocument();
  });

  it("lets the user pick between providers and posts the selection", async () => {
    const user = userEvent.setup();
    renderDialog({ providers: ["stripe", "paypal"] });

    await user.type(screen.getByLabelText("teams.payment.amount"), "20");
    await user.click(screen.getByRole("radio", { name: "PayPal" }));
    await user.click(screen.getByRole("button", { name: "teams.payment.continue" }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/teams/4/balance/checkout",
        { amount: 20, provider: "paypal", save_method: false },
        "tok"
      )
    );
  });

  it("offers save-card only for auto-recharge-capable providers and sends the flag", async () => {
    const user = userEvent.setup();
    renderDialog({ providers: ["stripe"], autoRechargeProviders: ["stripe"] });

    await user.type(screen.getByLabelText("teams.payment.amount"), "15");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "teams.payment.continue" }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        expect.any(String),
        { amount: 15, provider: "stripe", save_method: true },
        "tok"
      )
    );
  });

  it("hands the browser off to the hosted checkout page", async () => {
    const user = userEvent.setup();
    renderDialog();

    await user.type(screen.getByLabelText("teams.payment.amount"), "20");
    await user.click(screen.getByRole("button", { name: "teams.payment.continue" }));
    await waitFor(() => expect(locationMock.href).toBe("https://pay.example/session"));
  });

  it("recovers when the checkout response has no redirect", async () => {
    api.post.mockResolvedValue({});
    const user = userEvent.setup();
    renderDialog();

    await user.type(screen.getByLabelText("teams.payment.amount"), "20");
    const cont = screen.getByRole("button", { name: "teams.payment.continue" });
    await user.click(cont);
    await waitFor(() => expect(cont).toBeEnabled());
    expect(locationMock.href).toBe("");
  });
});
