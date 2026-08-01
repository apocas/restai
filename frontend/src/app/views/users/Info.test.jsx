import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider, createTheme } from "@mui/material";
import UserInfo from "./Info";
import api from "app/utils/api";

jest.mock("app/utils/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  delete: jest.fn(),
}));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
  useParams: () => ({ id: "bob" }),
}));

// The tab children have their own test files — stub them so this suite only
// covers the shell: tab switching and which data flows to which child.
jest.mock("./components/BasicInformation", () => (props) =>
  require("react").createElement("div", { "data-testid": "tab-basic" }, "basic:" + (props.user.username || ""))
);
jest.mock("./components/Password", () => (props) =>
  require("react").createElement("div", { "data-testid": "tab-password" }, "password:" + (props.user.username || ""))
);
jest.mock("./components/TwoFactorAuth", () => (props) =>
  require("react").createElement("div", { "data-testid": "tab-2fa" }, "2fa:" + (props.user.username || ""))
);
jest.mock("./components/ApiKeys", () => (props) =>
  require("react").createElement("div", { "data-testid": "tab-apikeys" }, "apikeys:" + (props.user.username || ""))
);
jest.mock("./components/Projects", () => (props) =>
  require("react").createElement(
    "div",
    { "data-testid": "tab-projects" },
    "projects:" + (props.user.username || "") + ":" + (props.projects || []).length
  )
);
jest.mock("./components/Teams", () => (props) =>
  require("react").createElement("div", { "data-testid": "tab-teams" }, "teams:" + (props.user.username || ""))
);
jest.mock("./components/UserActivity", () => (props) =>
  require("react").createElement("div", { "data-testid": "tab-activity" }, "activity:" + (props.user.username || ""))
);
jest.mock("./components/DeleteAccount", () => (props) =>
  require("react").createElement("div", { "data-testid": "tab-delete" }, "delete:" + (props.user.username || ""))
);

const USER = {
  id: 7,
  username: "bob",
  email: "bob@example.com",
  is_admin: false,
  sso: null,
  is_restricted: true,
  projects: [{ id: 1, name: "alpha" }],
  teams: [{ id: 1 }, { id: 2 }],
  api_keys: [{ id: 9 }],
};

let userResp;
let mockImpersonate;

beforeEach(() => {
  jest.clearAllMocks();
  mockImpersonate = jest.fn();
  useAuth.mockReturnValue({
    user: { token: "tok", username: "admin", is_admin: true },
    impersonate: mockImpersonate,
  });
  userResp = { ...USER };
  api.get.mockImplementation((path) => {
    if (path === "/users/bob") return Promise.resolve(userResp);
    if (path === "/projects") {
      return Promise.resolve({ projects: [{ id: 1, name: "alpha" }, { id: 2, name: "beta" }] });
    }
    if (path === "/info") {
      return Promise.resolve({ version: "1.0", embeddings: [], llms: [], loaders: [] });
    }
    return Promise.resolve({});
  });
  api.delete.mockResolvedValue({});
  window.confirm = jest.fn(() => true);
});

// useMediaQuery is called with a query *function*, which requires a theme in
// context — plain render() would crash on theme.breakpoints.
const theme = createTheme();
const renderInfo = async () => {
  render(
    <ThemeProvider theme={theme}>
      <UserInfo />
    </ThemeProvider>
  );
  await screen.findByText("basic:bob"); // user fetch landed, basic tab default
};

describe("UserInfo shell", () => {
  it("fetches the user and projects on mount and defaults to the basic tab", async () => {
    await renderInfo();
    expect(api.get).toHaveBeenCalledWith("/users/bob", "tok");
    expect(api.get).toHaveBeenCalledWith("/projects", "tok");
    // The page used to fire a dead GET /info whose result was never used —
    // removed; assert it stays gone.
    expect(api.get).not.toHaveBeenCalledWith("/info", "tok");
    expect(screen.getByTestId("tab-basic")).toBeInTheDocument();
    expect(screen.getByText("bob@example.com")).toBeInTheDocument();
  });

  it("shows hero pills reflecting role, auth, restriction and counts", async () => {
    await renderInfo();
    expect(screen.getByText("users.basic.roleRegular")).toBeInTheDocument();
    expect(screen.getByText("users.basic.authLocal")).toBeInTheDocument();
    expect(screen.getByText("Read-only")).toBeInTheDocument();
    expect(screen.getByText("1 users.basic.projects")).toBeInTheDocument();
    expect(screen.getByText("2 teams")).toBeInTheDocument();
    // not viewing self
    expect(screen.queryByText("users.basic.you")).not.toBeInTheDocument();
  });

  it("switches tabs and hands the fetched user to each child", async () => {
    const user = userEvent.setup();
    await renderInfo();

    await user.click(screen.getByRole("button", { name: "users.tabs.password" }));
    expect(screen.getByTestId("tab-password")).toHaveTextContent("password:bob");
    expect(screen.queryByTestId("tab-basic")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "users.tabs.twoFactor" }));
    expect(screen.getByTestId("tab-2fa")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "users.tabs.apiKeys" }));
    expect(screen.getByTestId("tab-apikeys")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "users.tabs.teams" }));
    expect(screen.getByTestId("tab-teams")).toHaveTextContent("teams:bob");

    await user.click(screen.getByRole("button", { name: "users.tabs.delete" }));
    expect(screen.getByTestId("tab-delete")).toHaveTextContent("delete:bob");
  });

  it("passes the global project list (not the user's) to the Projects tab", async () => {
    const user = userEvent.setup();
    await renderInfo();
    await user.click(screen.getByRole("button", { name: "users.tabs.projects" }));
    // user has 1 project but the tab gets the global list of 2
    expect(screen.getByTestId("tab-projects")).toHaveTextContent("projects:bob:2");
  });

  it("renders the activity tab only when the fetched user has an id", async () => {
    const user = userEvent.setup();
    await renderInfo();
    await user.click(screen.getByRole("button", { name: "users.tabs.activity" }));
    expect(screen.getByTestId("tab-activity")).toHaveTextContent("activity:bob");
  });

  it("hides the activity child while the user has no id", async () => {
    userResp = { ...USER, id: undefined };
    const user = userEvent.setup();
    await renderInfo();
    await user.click(screen.getByRole("button", { name: "users.tabs.activity" }));
    expect(screen.queryByTestId("tab-activity")).not.toBeInTheDocument();
  });
});

describe("UserInfo hero actions", () => {
  it("admin viewing another user can impersonate them", async () => {
    const user = userEvent.setup();
    await renderInfo();
    await user.click(screen.getByRole("button", { name: "users.basic.impersonate" }));
    expect(mockImpersonate).toHaveBeenCalledWith("bob");
  });

  it("delete confirms, calls the API and navigates back to the list", async () => {
    const user = userEvent.setup();
    await renderInfo();

    await user.click(screen.getByRole("button", { name: "common.delete" }));

    expect(window.confirm).toHaveBeenCalledWith('Delete user "bob"?');
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/users/bob", "tok"));
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/users"));
  });

  it("delete aborted by confirm does not call the API", async () => {
    window.confirm = jest.fn(() => false);
    const user = userEvent.setup();
    await renderInfo();

    await user.click(screen.getByRole("button", { name: "common.delete" }));

    expect(api.delete).not.toHaveBeenCalled();
    expect(mockNavigate).not.toHaveBeenCalledWith("/users");
  });

  it("admin viewing themselves gets a You pill but no delete/impersonate", async () => {
    useAuth.mockReturnValue({
      user: { token: "tok", username: "bob", is_admin: true },
      impersonate: mockImpersonate,
    });
    await renderInfo();
    expect(screen.getByText("users.basic.you")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "common.delete" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "users.basic.impersonate" })).not.toBeInTheDocument();
    // edit shortcut stays for admins
    expect(screen.getByRole("button", { name: "common.edit" })).toBeInTheDocument();
  });

  it("non-admin sees no edit, delete or impersonate actions", async () => {
    useAuth.mockReturnValue({
      user: { token: "tok", username: "carol", is_admin: false },
      impersonate: mockImpersonate,
    });
    await renderInfo();
    expect(screen.queryByRole("button", { name: "common.edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "common.delete" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "users.basic.impersonate" })).not.toBeInTheDocument();
  });

  it("the Users breadcrumb navigates back to the list", async () => {
    const user = userEvent.setup();
    await renderInfo();
    await user.click(screen.getByRole("link", { name: "Users" }));
    expect(mockNavigate).toHaveBeenCalledWith("/users");
  });
});
