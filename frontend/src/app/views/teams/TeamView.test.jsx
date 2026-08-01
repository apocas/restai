import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TeamView from "./TeamView";
import api from "app/utils/api";
import { toast } from "react-toastify";

jest.mock("app/utils/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  delete: jest.fn(),
}));
jest.mock("react-toastify", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
  useParams: () => ({ id: "5" }),
}));

// ESM-only / heavy leaf deps.
jest.mock("boring-avatars", () => () => null);
jest.mock("@microlink/react-json-view", () => () => null);
jest.mock("mui-datatables", () => ({
  __esModule: true,
  default: (props) => {
    const React = require("react");
    return React.createElement(
      "div",
      { "data-testid": "tx-table" },
      JSON.stringify(props.data)
    );
  },
}));
jest.mock("./MemberBudgetDialog", () => (props) => {
  const React = require("react");
  return props.open
    ? React.createElement("div", { "data-testid": "budget-dialog" }, props.member?.username)
    : null;
});
jest.mock("./TopUpBalanceDialog", () => (props) => {
  const React = require("react");
  return props.open ? React.createElement("div", { "data-testid": "topup-dialog" }) : null;
});

const TEAM = {
  id: 5,
  name: "acme",
  description: "the acme team",
  budget: 10,
  spending: 8,
  remaining: 2,
  balance: 3.5,
  users: [
    { id: 1, username: "admin" },
    { id: 2, username: "bob" },
  ],
  admins: [{ id: 1, username: "admin" }],
  projects: [{ id: 11, name: "proj1", human_name: "Proj One", type: "agent" }],
  llms: [{ id: 21, name: "gpt4" }],
  embeddings: [{ id: 31, name: "embed1" }],
  image_generators: ["dalle"],
  audio_generators: [],
};

const BUDGETS = [
  { user_id: 2, username: "bob", budget: 5, spending: 1 },
  { user_id: 1, username: "admin", budget: null, spending: 0 },
];
const TX = {
  total: 1,
  transactions: [
    {
      date: "2026-01-01T00:00:00Z",
      project: "proj1",
      user: "bob",
      llm: "gpt4",
      input_tokens: 100,
      output_tokens: 50,
      total_cost: 0.5,
    },
  ],
};

let teamResp;
let budgetsResp;

beforeEach(() => {
  jest.clearAllMocks();
  // team admin via admins list, not platform admin
  useAuth.mockReturnValue({ user: { id: 1, token: "tok", username: "admin", is_admin: false } });
  teamResp = () => Promise.resolve(TEAM);
  budgetsResp = () => Promise.resolve(BUDGETS);
  api.get.mockImplementation((path) => {
    if (path === "/teams/5") return teamResp();
    if (path === "/teams/5/members/budgets") return budgetsResp();
    if (path.startsWith("/teams/5/transactions")) return Promise.resolve(TX);
    return Promise.resolve({});
  });
  api.delete.mockResolvedValue({});
  window.confirm = jest.fn(() => true);
});

const renderView = async () => {
  render(<TeamView />);
  await screen.findByText("acme");
};

describe("TeamView", () => {
  it("shows a spinner while loading", () => {
    teamResp = () => new Promise(() => {});
    render(<TeamView />);
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    expect(screen.getByText("teams.view.loading")).toBeInTheDocument();
  });

  it("shows the not-found message when the team fails to load", async () => {
    teamResp = () => Promise.reject({ status: 404 });
    render(<TeamView />);
    expect(await screen.findByText("teams.view.notFound")).toBeInTheDocument();
  });

  it("renders the hero with counts, budget chip and balance chip", async () => {
    await renderView();
    expect(screen.getByText("the acme team")).toBeInTheDocument();
    expect(screen.getByText("2 members")).toBeInTheDocument();
    expect(screen.getByText("1 admin")).toBeInTheDocument();
    expect(screen.getByText("1 project")).toBeInTheDocument();
    expect(screen.getByText("2 models")).toBeInTheDocument();
    expect(screen.getByText("$8.00 / $10.00 (80%)")).toBeInTheDocument();
    expect(screen.getByText("teams.balance.available")).toBeInTheDocument();
    // budget progress card
    expect(screen.getByText("80% of monthly budget used")).toBeInTheDocument();
    expect(screen.getByText(/\$2\.00 teams.view.left/)).toBeInTheDocument();
  });

  it("shows the unlimited chip and no budget bar when budget is -1", async () => {
    teamResp = () => Promise.resolve({ ...TEAM, budget: -1 });
    await renderView();
    expect(screen.getByText("teams.view.unlimited")).toBeInTheDocument();
    expect(screen.queryByText(/of monthly budget used/)).not.toBeInTheDocument();
  });

  it("shows the depleted balance chip when balance <= 0", async () => {
    teamResp = () => Promise.resolve({ ...TEAM, balance: 0 });
    await renderView();
    expect(screen.getByText("teams.balance.depleted")).toBeInTheDocument();
  });

  it("renders resource sections: members, projects, llms, embeddings, generators", async () => {
    await renderView();
    expect(screen.getByText("bob")).toBeInTheDocument();
    expect(screen.getByText("Proj One")).toBeInTheDocument();
    expect(screen.getByText("PROJECT/0011")).toBeInTheDocument();
    expect(screen.getByText("agent")).toBeInTheDocument();
    expect(screen.getByText("gpt4")).toBeInTheDocument();
    expect(screen.getByText("embed1")).toBeInTheDocument();
    expect(screen.getByText("dalle")).toBeInTheDocument();
    // no audio generators -> empty state
    expect(screen.getByText("teams.view.noAudioGen")).toBeInTheDocument();
  });

  it("team admin sees member budget chips (capped + uncapped)", async () => {
    await renderView();
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith("/teams/5/members/budgets", "tok", { silent: true })
    );
    expect(await screen.findByText("$1.00 / $5.00")).toBeInTheDocument();
    // admin (id 1) has a null cap -> uncapped (rendered in members + admins list)
    expect(screen.getAllByText("teams.budget.uncapped").length).toBeGreaterThanOrEqual(1);
  });

  it("clicking a project row navigates to the project", async () => {
    const user = userEvent.setup();
    await renderView();
    await user.click(screen.getByText("Proj One"));
    expect(mockNavigate).toHaveBeenCalledWith("/project/11");
  });

  it("team admin action bar: analytics, wallet and edit navigation; no top-up for non-platform-admin", async () => {
    const user = userEvent.setup();
    await renderView();

    await user.click(screen.getByRole("button", { name: "teams.analytics.title" }));
    expect(mockNavigate).toHaveBeenCalledWith("/team/5/analytics");
    await user.click(screen.getByRole("button", { name: "teams.balance.ledger.title" }));
    expect(mockNavigate).toHaveBeenCalledWith("/team/5/wallet");
    await user.click(screen.getByRole("button", { name: "teams.view.edit" }));
    expect(mockNavigate).toHaveBeenCalledWith("/team/5/edit");

    expect(screen.queryByRole("button", { name: "teams.balance.topUp" })).not.toBeInTheDocument();
  });

  it("platform admin can open the top-up dialog", async () => {
    useAuth.mockReturnValue({ user: { id: 99, token: "tok", username: "root", is_admin: true } });
    const user = userEvent.setup();
    await renderView();

    await user.click(screen.getByRole("button", { name: "teams.balance.topUp" }));
    expect(screen.getByTestId("topup-dialog")).toBeInTheDocument();
  });

  it("removing a member confirms, DELETEs and refetches the team", async () => {
    const user = userEvent.setup();
    await renderView();

    // members list order: admin, bob — remove bob
    await user.click(screen.getAllByRole("button", { name: "teams.view.removeUser" })[1]);

    expect(window.confirm).toHaveBeenCalledWith("teams.view.confirmRemove");
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/teams/5/users/bob", "tok"));
    expect(toast.success).toHaveBeenCalledWith("teams.view.removed");
    await waitFor(() =>
      expect(api.get.mock.calls.filter(([p]) => p === "/teams/5")).toHaveLength(2)
    );
  });

  it("aborting the confirm leaves the member alone", async () => {
    window.confirm = jest.fn(() => false);
    const user = userEvent.setup();
    await renderView();

    await user.click(screen.getAllByRole("button", { name: "teams.view.removeUser" })[1]);
    expect(api.delete).not.toHaveBeenCalled();
  });

  it("removing an LLM DELETEs by id", async () => {
    const user = userEvent.setup();
    await renderView();

    await user.click(screen.getByRole("button", { name: "teams.view.removeLlm" }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/teams/5/llms/21", "tok"));
  });

  it("non-admin member sees no remove buttons, budget chips or transactions panel", async () => {
    useAuth.mockReturnValue({ user: { id: 2, token: "tok", username: "bob", is_admin: false } });
    await renderView();

    expect(screen.queryByRole("button", { name: "teams.view.removeUser" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "teams.view.removeLlm" })).not.toBeInTheDocument();
    expect(screen.queryByText("teams.view.transactions")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "teams.view.edit" })).not.toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalledWith("/teams/5/members/budgets", "tok", { silent: true });
  });

  it("opening the member budget editor shows the dialog for that member", async () => {
    const user = userEvent.setup();
    await renderView();

    // members list order: admin, bob
    await user.click(screen.getAllByRole("button", { name: "teams.budget.editCap" })[1]);
    const dialog = screen.getByTestId("budget-dialog");
    expect(within(dialog).getByText("bob")).toBeInTheDocument();
  });

  it("expanding the transactions panel fetches and renders the ledger", async () => {
    const user = userEvent.setup();
    await renderView();

    await user.click(screen.getByText("teams.view.transactions"));

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith("/teams/5/transactions?start=0&end=100", "tok")
    );
    const table = await screen.findByTestId("tx-table");
    await waitFor(() => {
      expect(table).toHaveTextContent("proj1");
      expect(table).toHaveTextContent("gpt4");
      expect(table).toHaveTextContent("bob");
    });
  });
});
