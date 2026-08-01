import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MemberBudgetDialog from "./MemberBudgetDialog";
import api from "app/utils/api";
import { toast } from "react-toastify";

jest.mock("app/utils/api", () => ({ patch: jest.fn() }));
jest.mock("react-toastify", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

const baseMember = { user_id: 7, username: "bob", budget: 100, spending: 80 };

const renderDialog = (over = {}) => {
  const props = {
    open: true,
    onClose: jest.fn(),
    teamId: 3,
    member: baseMember,
    onSaved: jest.fn(),
    ...over,
  };
  render(<MemberBudgetDialog {...props} />);
  return props;
};

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin" } });
  api.patch.mockResolvedValue({ budget: 50 });
});

describe("MemberBudgetDialog", () => {
  it("renders nothing without a member", () => {
    const { container } = render(
      <MemberBudgetDialog open onClose={() => {}} teamId={3} member={null} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the spend-vs-cap usage bar with the computed percentage", () => {
    renderDialog();
    expect(screen.getByText("$80.00 / $100.00 (80%)")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "80");
  });

  it("caps the displayed percentage at 100", () => {
    renderDialog({ member: { ...baseMember, spending: 250 } });
    expect(screen.getByText("$250.00 / $100.00 (100%)")).toBeInTheDocument();
  });

  it("omits the usage bar when the member has no cap", () => {
    renderDialog({ member: { ...baseMember, budget: null } });
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("saves the entered cap and fires callbacks", async () => {
    const user = userEvent.setup();
    const props = renderDialog();

    const input = screen.getByLabelText("teams.budget.capInput");
    await user.clear(input);
    await user.type(input, "50");
    await user.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        "/teams/3/members/bob/budget",
        { budget: 50 },
        "tok"
      )
    );
    expect(toast.success).toHaveBeenCalledWith("teams.budget.saved", expect.anything());
    expect(props.onSaved).toHaveBeenCalledWith({ budget: 50 });
    expect(props.onClose).toHaveBeenCalled();
  });

  it("Clear sends budget=-1 (unlimited)", async () => {
    const user = userEvent.setup();
    renderDialog();

    await user.click(screen.getByRole("button", { name: "teams.budget.clear" }));
    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        "/teams/3/members/bob/budget",
        { budget: -1 },
        "tok"
      )
    );
    expect(toast.success).toHaveBeenCalledWith("teams.budget.cleared", expect.anything());
  });

  it("treats a blank or non-positive value as clearing the cap", async () => {
    const user = userEvent.setup();
    renderDialog();

    await user.clear(screen.getByLabelText("teams.budget.capInput"));
    await user.click(screen.getByRole("button", { name: "common.save" }));
    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(expect.any(String), { budget: -1 }, "tok")
    );
  });
});
