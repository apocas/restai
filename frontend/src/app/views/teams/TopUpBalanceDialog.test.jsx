import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TopUpBalanceDialog from "./TopUpBalanceDialog";
import api from "app/utils/api";
import { toast } from "react-toastify";

jest.mock("app/utils/api", () => ({ post: jest.fn() }));
jest.mock("react-toastify", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

const renderDialog = (over = {}) => {
  const props = {
    open: true,
    onClose: jest.fn(),
    teamId: 9,
    current: 25,
    onSaved: jest.fn(),
    ...over,
  };
  render(<TopUpBalanceDialog {...props} />);
  return props;
};

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok" } });
  api.post.mockResolvedValue({ id: 9, balance: 75 });
});

describe("TopUpBalanceDialog", () => {
  it("disables the top-up button until a positive amount is entered", async () => {
    const user = userEvent.setup();
    renderDialog();

    const button = screen.getByRole("button", { name: "teams.balance.topUp" });
    expect(button).toBeDisabled();

    await user.type(screen.getByLabelText("teams.balance.addAmount"), "50");
    expect(button).toBeEnabled();
  });

  it("previews the new balance as current + amount", async () => {
    const user = userEvent.setup();
    renderDialog({ current: 25 });

    expect(screen.queryByText("teams.balance.newBalance")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("teams.balance.addAmount"), "50");
    expect(screen.getByText("teams.balance.newBalance")).toBeInTheDocument();
  });

  it("posts the top-up and fires callbacks", async () => {
    const user = userEvent.setup();
    const props = renderDialog();

    await user.type(screen.getByLabelText("teams.balance.addAmount"), "50");
    await user.click(screen.getByRole("button", { name: "teams.balance.topUp" }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/teams/9/balance/topup", { amount: 50 }, "tok")
    );
    expect(props.onSaved).toHaveBeenCalledWith({ id: 9, balance: 75 });
    expect(props.onClose).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalled();
  });

  it("shows the wallet explainer when the team has no balance yet", () => {
    renderDialog({ current: null });
    expect(screen.getByText("teams.balance.walletHelp")).toBeInTheDocument();
  });
});
