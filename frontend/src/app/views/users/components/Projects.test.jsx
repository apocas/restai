import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Projects from "./Projects";
import api from "app/utils/api";
import useAuth from "app/hooks/useAuth";

jest.mock("app/utils/api", () => ({ patch: jest.fn() }));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));
jest.mock("app/hooks/useAuth", () => jest.fn());
// boring-avatars is ESM-only ("type": "module") — CRA jest can't transform it.
jest.mock("boring-avatars", () => () => null);

const ALL_PROJECTS = [
  { id: 1, name: "alpha", human_name: "Alpha Bot" },
  { id: 2, name: "beta", human_name: "Beta Bot" },
];

const makeTarget = () => ({
  username: "bob",
  projects: [{ id: 1, name: "alpha" }],
});

let locationMock;
beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  api.patch.mockResolvedValue({});
  locationMock = { href: "", pathname: "/admin/user/bob" };
  delete window.location;
  window.location = locationMock;
});

describe("Projects", () => {
  it("lists the user's projects enriched from the global project list", () => {
    render(<Projects user={makeTarget()} projects={ALL_PROJECTS} />);

    expect(screen.getByText("users.userProjects.title")).toBeInTheDocument();
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("(ID: 1)")).toBeInTheDocument();
    // human_name is lowercased for display.
    expect(screen.getByText("alpha bot")).toBeInTheDocument();
    // Not associated → not shown as a card.
    expect(screen.queryByText("beta")).not.toBeInTheDocument();
  });

  it("hides associate/dissociate controls from non-admins", () => {
    useAuth.mockReturnValue({ user: { token: "tok", username: "bob", is_admin: false } });
    render(<Projects user={makeTarget()} projects={ALL_PROJECTS} />);

    expect(screen.queryByRole("button", { name: "users.userProjects.associate" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "users.userProjects.dissociate" })).not.toBeInTheDocument();
  });

  it("associates a selected project and patches the full name list", async () => {
    const user = userEvent.setup();
    render(<Projects user={makeTarget()} projects={ALL_PROJECTS} />);

    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByRole("option", { name: "beta (ID: 2)" }));
    await user.click(screen.getByRole("button", { name: "users.userProjects.associate" }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        "/users/bob",
        { projects: ["alpha", "beta"] },
        "tok"
      )
    );
    expect(locationMock.href).toBe("/admin/user/bob");
  });

  it("does nothing when associate is clicked with no project selected", async () => {
    const user = userEvent.setup();
    render(<Projects user={makeTarget()} projects={ALL_PROJECTS} />);

    await user.click(screen.getByRole("button", { name: "users.userProjects.associate" }));

    expect(api.patch).not.toHaveBeenCalled();
  });

  it("dissociates a project and patches the remaining names", async () => {
    const user = userEvent.setup();
    render(<Projects user={makeTarget()} projects={ALL_PROJECTS} />);

    await user.click(screen.getByRole("button", { name: "users.userProjects.dissociate" }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith("/users/bob", { projects: [] }, "tok")
    );
    expect(locationMock.href).toBe("/admin/user/bob");
  });

  it("never mutates the user prop when associating or dissociating", async () => {
    const user = userEvent.setup();
    const target = makeTarget();
    const originalProjects = target.projects;
    render(<Projects user={target} projects={ALL_PROJECTS} />);

    await user.click(screen.getByRole("button", { name: "users.userProjects.dissociate" }));
    await waitFor(() => expect(api.patch).toHaveBeenCalled());

    // The prop object must be untouched — the PATCH payload is derived,
    // not the result of an in-place filter/push on user.projects.
    expect(target.projects).toBe(originalProjects);
    expect(target.projects).toEqual([{ id: 1, name: "alpha" }]);
  });
});
