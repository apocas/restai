import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProjectInfo from "./ProjectInfo";
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
jest.mock("react-router-dom", () => ({ useNavigate: () => mockNavigate }));

jest.mock("boring-avatars", () => () => {
  const React = require("react");
  return React.createElement("div", { "data-testid": "avatar" });
});

const PROJECT = {
  id: 7,
  name: "myproj",
  human_name: "My Proj",
  human_description: "Answers questions",
  type: "block",
  llm: "gpt4",
  team: { id: 1, name: "acme" },
  guard: "12",
  public: true,
  options: { rate_limit: 30 },
};

const clickIcon = async (user, testid) => {
  await user.click(document.querySelector(`svg[data-testid="${testid}"]`).closest("button"));
};

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin" } });
});

describe("ProjectInfo", () => {
  it("renders the hero with name, description and option chips", () => {
    render(<ProjectInfo project={PROJECT} />);
    expect(screen.getByText("My Proj")).toBeInTheDocument();
    expect(screen.getByText("Answers questions")).toBeInTheDocument();
    expect(screen.getByText("gpt4")).toBeInTheDocument();
    expect(screen.getByText("acme")).toBeInTheDocument();
    expect(screen.getByText("Guard: 12")).toBeInTheDocument();
    expect(screen.getByText("30 req/min")).toBeInTheDocument();
    expect(screen.getByText("Shared")).toBeInTheDocument();
    expect(screen.getByText("block")).toBeInTheDocument(); // type chip
    expect(screen.getByText("0007")).toBeInTheDocument(); // padded id trail
  });

  it("hides conditional chips when the project lacks them", () => {
    render(
      <ProjectInfo
        project={{ id: 8, name: "bare", type: "agent", options: {} }}
      />
    );
    expect(screen.queryByText(/Guard:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/req\/min/)).not.toBeInTheDocument();
    expect(screen.queryByText("Shared")).not.toBeInTheDocument();
  });

  it("action toolbar navigates to edit / playground / evals / logs / api", async () => {
    const user = userEvent.setup();
    render(<ProjectInfo project={PROJECT} />);
    await clickIcon(user, "EditIcon");
    expect(mockNavigate).toHaveBeenCalledWith("/project/7/edit");
    await clickIcon(user, "SportsEsportsIcon");
    expect(mockNavigate).toHaveBeenCalledWith("/project/7/playground");
    await clickIcon(user, "ScienceIcon");
    expect(mockNavigate).toHaveBeenCalledWith("/project/7/evals");
    await clickIcon(user, "ArticleIcon");
    expect(mockNavigate).toHaveBeenCalledWith("/project/7/logs");
    await clickIcon(user, "CodeIcon");
    expect(mockNavigate).toHaveBeenCalledWith("/project/7/api");
  });

  it("shows the IDE shortcut only for block projects", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<ProjectInfo project={PROJECT} />);
    await clickIcon(user, "ViewInArIcon");
    expect(mockNavigate).toHaveBeenCalledWith("/project/7/ide");
    rerender(<ProjectInfo project={{ ...PROJECT, type: "agent" }} />);
    expect(document.querySelector('svg[data-testid="ViewInArIcon"]')).toBeNull();
  });

  it("clone dialog pre-fills the name and posts to /clone then navigates", async () => {
    api.post.mockResolvedValue({ project: 99 });
    const user = userEvent.setup();
    render(<ProjectInfo project={PROJECT} />);
    await clickIcon(user, "ContentCopyIcon");
    const input = screen.getByDisplayValue("myproj-copy");
    await user.clear(input);
    await user.type(input, "fresh-copy");
    await user.click(screen.getByRole("button", { name: "projects.actions.clone" }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/projects/7/clone",
        { name: "fresh-copy" },
        "tok"
      )
    );
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/project/99"));
  });

  it("delete asks for confirmation and only deletes on accept", async () => {
    api.delete.mockResolvedValue({});
    const user = userEvent.setup();
    const confirmSpy = jest.spyOn(window, "confirm").mockReturnValue(false);
    render(<ProjectInfo project={PROJECT} />);

    await clickIcon(user, "DeleteIcon");
    expect(api.delete).not.toHaveBeenCalled();

    confirmSpy.mockReturnValue(true);
    await clickIcon(user, "DeleteIcon");
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/projects/7", "tok"));
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/projects"));
    confirmSpy.mockRestore();
  });

  it("save-as-template publishes name/description/visibility and toasts", async () => {
    api.post.mockResolvedValue({});
    const user = userEvent.setup();
    render(<ProjectInfo project={PROJECT} />);
    await clickIcon(user, "BookmarkAddIcon");
    // Name pre-filled from human_name.
    expect(screen.getByDisplayValue("My Proj")).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "projects.template.publish" })
    );
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/projects/7/publish-template",
        { name: "My Proj", description: null, visibility: "private" },
        "tok"
      )
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });
});
