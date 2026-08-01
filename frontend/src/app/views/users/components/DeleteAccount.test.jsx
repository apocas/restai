import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import DeleteAccount from "./DeleteAccount";
import api from "app/utils/api";
import useAuth from "app/hooks/useAuth";

jest.mock("app/utils/api", () => ({ delete: jest.fn() }));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));
jest.mock("app/hooks/useAuth", () => jest.fn());

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

const renderIt = () =>
  render(
    <MemoryRouter>
      <DeleteAccount user={{ username: "bob" }} />
    </MemoryRouter>
  );

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok" } });
  api.delete.mockResolvedValue(null);
});

describe("DeleteAccount", () => {
  it("keeps the delete button disabled until the confirmation is checked", async () => {
    const user = userEvent.setup();
    renderIt();

    const button = screen.getByRole("button", { name: "users.deleteAccount.delete" });
    expect(button).toBeDisabled();

    await user.click(screen.getByRole("checkbox"));
    expect(button).toBeEnabled();
  });

  it("deletes the account and navigates to the users list", async () => {
    const user = userEvent.setup();
    renderIt();

    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "users.deleteAccount.delete" }));

    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/users/bob", "tok"));
    expect(mockNavigate).toHaveBeenCalledWith("/users");
  });
});
