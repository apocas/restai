import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TeamEdit from "./TeamEdit";
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
let mockParams;
jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
  useParams: () => mockParams,
}));

const TEAM = {
  id: 7,
  name: "acme",
  description: "the acme team",
  budget: 25,
  users: [{ username: "admin" }, { username: "bob" }],
  admins: [{ username: "admin" }],
  projects: [{ name: "proj1" }],
  llms: [{ name: "gpt4" }],
  embeddings: [],
  image_generators: ["dalle"],
  audio_generators: [],
  branding: null,
  options: null,
};

let teamResp;
let imageResp;
let audioResp;

beforeEach(() => {
  jest.clearAllMocks();
  mockParams = { id: "7" };
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  teamResp = () => Promise.resolve(TEAM);
  imageResp = () => Promise.resolve({ generators: ["dalle"] });
  audioResp = () => Promise.resolve({ generators: [] });
  api.get.mockImplementation((path) => {
    if (path === "/teams/7") return teamResp();
    if (path === "/users") return Promise.resolve({ users: [{ username: "admin" }, { username: "bob" }, { username: "carol" }] });
    if (path === "/projects") return Promise.resolve({ projects: [{ name: "proj1" }, { name: "proj2" }] });
    if (path === "/info") return Promise.resolve({ llms: [{ name: "gpt4" }, { name: "claude" }], embeddings: [{ name: "embed1" }] });
    if (path === "/image") return imageResp();
    if (path === "/audio") return audioResp();
    return Promise.resolve({});
  });
  api.patch.mockResolvedValue({ id: 7 });
  api.post.mockResolvedValue({ id: 9 });
});

const renderEdit = async () => {
  render(<TeamEdit />);
  await screen.findByDisplayValue("acme");
};

describe("TeamEdit (existing team)", () => {
  it("shows a loading state while the team is fetched", () => {
    teamResp = () => new Promise(() => {});
    render(<TeamEdit />);
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    expect(screen.getByText("common.loading")).toBeInTheDocument();
  });

  it("loads the team and fills the general fields + hero", async () => {
    await renderEdit();
    expect(api.get).toHaveBeenCalledWith("/teams/7", "tok");
    expect(screen.getByLabelText(/teams.edit.name/)).toHaveValue("acme");
    expect(screen.getByLabelText(/teams.edit.budget/)).toHaveValue(25);
    expect(screen.getByLabelText(/teams.edit.description/)).toHaveValue("the acme team");
    expect(screen.getByText("TEAM/0007")).toBeInTheDocument();
    expect(screen.getByText("$25.00 cap")).toBeInTheDocument();
    expect(screen.getByText("2 members")).toBeInTheDocument();
    // existing members/admins rendered as chips
    expect(screen.getAllByText("admin").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("bob")).toBeInTheDocument();
  });

  it("saving PATCHes the mapped payload and navigates back to the team", async () => {
    const user = userEvent.setup();
    await renderEdit();

    const name = screen.getByLabelText(/teams.edit.name/);
    await user.clear(name);
    await user.type(name, "acme2");
    const budget = screen.getByLabelText(/teams.edit.budget/);
    await user.clear(budget);
    await user.type(budget, "100");

    await user.click(screen.getByRole("button", { name: /teams.edit.saveChanges/ }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        "/teams/7",
        expect.objectContaining({
          name: "acme2",
          budget: 100,
          users: ["admin", "bob"],
          admins: ["admin"],
          projects: ["proj1"],
          llms: ["gpt4"],
          embeddings: [],
          image_generators: ["dalle"],
          audio_generators: [],
        }),
        "tok"
      )
    );
    expect(toast.success).toHaveBeenCalledWith("teams.edit.updated");
    expect(mockNavigate).toHaveBeenCalledWith("/team/7");
  });

  it("adding a member through the picker includes them in the save payload", async () => {
    const user = userEvent.setup();
    await renderEdit();

    await user.click(screen.getByLabelText(/teams.edit.selectUsers/));
    await user.click(await screen.findByRole("option", { name: "carol" }));
    await user.click(screen.getByRole("button", { name: /teams.edit.saveChanges/ }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        "/teams/7",
        expect.objectContaining({ users: ["admin", "bob", "carol"] }),
        "tok"
      )
    );
  });

  it("invite: button disabled until a username is typed, then POSTs and clears", async () => {
    const user = userEvent.setup();
    await renderEdit();

    const sendBtn = screen.getByRole("button", { name: /teams.edit.sendInvite/ });
    expect(sendBtn).toBeDisabled();

    const field = screen.getByLabelText(/teams.edit.username/);
    await user.type(field, "  carol  ");
    expect(sendBtn).toBeEnabled();
    await user.click(sendBtn);

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/teams/7/invitations", { username: "carol" }, "tok")
    );
    expect(toast.success).toHaveBeenCalledWith("invitations.sent");
    await waitFor(() => expect(field).toHaveValue(""));
  });

  it("models tab: shows LLM/embedding pickers, image picker, and the empty-audio hint", async () => {
    const user = userEvent.setup();
    await renderEdit();

    await user.click(screen.getByRole("tab", { name: /teams.edit.tabs.models/ }));

    expect(screen.getByLabelText(/teams.edit.selectLlms/)).toBeInTheDocument();
    expect(screen.getByLabelText(/teams.edit.selectEmbeddings/)).toBeInTheDocument();
    expect(screen.getByLabelText(/teams.edit.selectImageGen/)).toBeInTheDocument();
    // no audio generators configured -> picker replaced by hint
    expect(screen.queryByLabelText(/teams.edit.selectAudioGen/)).not.toBeInTheDocument();
    expect(screen.getByText("teams.edit.noAudioGen")).toBeInTheDocument();
  });

  it("branding tab: typing an app name reveals the live preview", async () => {
    const user = userEvent.setup();
    await renderEdit();

    await user.click(screen.getByRole("tab", { name: /teams.edit.tabs.branding/ }));
    expect(screen.queryByText("teams.edit.preview")).not.toBeInTheDocument();

    await user.type(screen.getByLabelText(/teams.edit.appName/), "Zed");

    expect(screen.getByText("teams.edit.preview")).toBeInTheDocument();
    expect(screen.getByText("Zed")).toBeInTheDocument();
  });

  it("integrations tab: SMTP fields land in options and are sent on save", async () => {
    const user = userEvent.setup();
    await renderEdit();

    await user.click(screen.getByRole("tab", { name: /teams.edit.tabs.integrations/ }));
    await user.type(screen.getByLabelText(/settings.fields.smtpHost/), "smtp.acme.com");
    await user.click(screen.getByRole("button", { name: /teams.edit.saveChanges/ }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        "/teams/7",
        expect.objectContaining({
          options: expect.objectContaining({ smtp_host: "smtp.acme.com" }),
        }),
        "tok"
      )
    );
  });

  it("cancel navigates back to the team view without saving", async () => {
    const user = userEvent.setup();
    await renderEdit();
    await user.click(screen.getByRole("button", { name: /common.cancel/ }));
    expect(mockNavigate).toHaveBeenCalledWith("/team/7");
    expect(api.patch).not.toHaveBeenCalled();
  });
});

describe("TeamEdit (new team)", () => {
  beforeEach(() => {
    mockParams = {};
  });

  it("renders the create form without fetching a team and hides the invite card", async () => {
    render(<TeamEdit />);
    expect(await screen.findByText("TEAM/NEW")).toBeInTheDocument();
    expect(screen.getAllByText("teams.edit.newTitle").length).toBeGreaterThanOrEqual(1);
    expect(api.get).not.toHaveBeenCalledWith(expect.stringMatching(/^\/teams\//), expect.anything());
    expect(screen.queryByText("teams.edit.invite")).not.toBeInTheDocument();
    // unlimited budget default (-1)
    expect(screen.getByText("teams.view.unlimited")).toBeInTheDocument();
  });

  it("create POSTs /teams and navigates to the new team id", async () => {
    const user = userEvent.setup();
    render(<TeamEdit />);
    await screen.findByText("TEAM/NEW");

    await user.type(screen.getByLabelText(/teams.edit.name/), "newteam");
    await user.click(screen.getByRole("button", { name: /teams.edit.createTeam/ }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/teams",
        expect.objectContaining({ name: "newteam", budget: -1, users: [], admins: [] }),
        "tok"
      )
    );
    expect(toast.success).toHaveBeenCalledWith("teams.edit.created");
    expect(mockNavigate).toHaveBeenCalledWith("/team/9");
  });

  it("cancel from the create form goes back to the teams list", async () => {
    const user = userEvent.setup();
    render(<TeamEdit />);
    await screen.findByText("TEAM/NEW");
    await user.click(screen.getByRole("button", { name: /common.cancel/ }));
    expect(mockNavigate).toHaveBeenCalledWith("/teams");
  });
});
