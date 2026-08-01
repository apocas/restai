import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import BasicInformation from "./BasicInformation";
import api from "app/utils/api";
import useAuth from "app/hooks/useAuth";
import { applyLanguage } from "app/i18n";

jest.mock("app/utils/api", () => ({ patch: jest.fn() }));
jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (k) => k, i18n: { language: "en" } }),
}));
jest.mock("app/hooks/useAuth", () => jest.fn());
jest.mock("app/i18n", () => ({
  SUPPORTED_LANGUAGES: [
    { code: "en", label: "English", nativeLabel: "English" },
    { code: "de", label: "German", nativeLabel: "Deutsch" },
  ],
  applyLanguage: jest.fn(),
}));

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

const renderIt = (target) =>
  render(
    <MemoryRouter>
      <BasicInformation user={target} />
    </MemoryRouter>
  );

let locationMock;
beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  api.patch.mockResolvedValue({});
  locationMock = { href: "", pathname: "/admin/user/bob" };
  delete window.location;
  window.location = locationMock;
});

describe("BasicInformation rendering", () => {
  it("shows admin-only switches when an admin views another user (no language, suspend visible)", () => {
    renderIt({ username: "bob", is_admin: false });

    expect(screen.getByText("users.fields.isAdmin")).toBeInTheDocument();
    expect(screen.getByText("users.fields.isPrivate")).toBeInTheDocument();
    expect(screen.getByText("users.basic.restricted")).toBeInTheDocument();
    // Suspend only shows for admin viewing someone else.
    expect(screen.getByRole("checkbox", { name: "suspended checkbox" })).toBeInTheDocument();
    // Language editor is self-profile only.
    expect(screen.queryByText("users.basic.language")).not.toBeInTheDocument();
  });

  it("hides all privileged switches from a plain non-admin user", () => {
    useAuth.mockReturnValue({ user: { token: "tok", username: "carol", is_admin: false } });
    renderIt({ username: "bob" });

    expect(screen.queryByText("users.fields.isAdmin")).not.toBeInTheDocument();
    expect(screen.queryByText("users.fields.isPrivate")).not.toBeInTheDocument();
    expect(screen.queryByText("users.basic.restricted")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "suspended checkbox" })).not.toBeInTheDocument();
  });

  it("hides the suspend switch on your own profile but shows the language picker", () => {
    renderIt({ username: "admin", is_admin: true });

    expect(screen.queryByRole("checkbox", { name: "suspended checkbox" })).not.toBeInTheDocument();
    // Label + fieldset legend both carry the key.
    expect(screen.getAllByText("users.basic.language").length).toBeGreaterThan(0);
  });
});

describe("BasicInformation saving", () => {
  it("patches only the changed flags and redirects to the profile", async () => {
    const user = userEvent.setup();
    renderIt({ username: "bob", is_admin: false, is_restricted: false });

    await user.click(screen.getByRole("checkbox", { name: "restricted checkbox" }));
    await user.click(screen.getByRole("button", { name: "users.basic.saveChanges" }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith("/users/bob", { is_restricted: true }, "tok")
    );
    expect(locationMock.href).toBe("/admin/user/bob");
  });

  it("saves a language change on the self profile and applies it locally", async () => {
    const user = userEvent.setup();
    renderIt({ username: "admin", is_admin: true, options: { language: "en" } });

    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByRole("option", { name: "Deutsch" }));
    await user.click(screen.getByRole("button", { name: "users.basic.saveChanges" }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        "/users/admin",
        { options: { language: "de" } },
        "tok"
      )
    );
    expect(applyLanguage).toHaveBeenCalledWith("de");
    expect(locationMock.href).toBe("/admin/user/admin");
  });

  it("cancel navigates back to the users list without patching", async () => {
    const user = userEvent.setup();
    renderIt({ username: "bob" });

    await user.click(screen.getByRole("button", { name: "common.cancel" }));

    expect(mockNavigate).toHaveBeenCalledWith("/users");
    expect(api.patch).not.toHaveBeenCalled();
  });
});
