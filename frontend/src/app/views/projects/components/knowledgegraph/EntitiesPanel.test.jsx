import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EntitiesPanel from "./EntitiesPanel";
import api from "app/utils/api";
import { toast } from "react-toastify";

jest.mock("app/utils/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  delete: jest.fn(),
}));
jest.mock("react-toastify", () => ({
  toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() },
}));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

const PROJECT = { id: 1, name: "proj" };

const ENTITIES = [
  { id: 1, name: "Acme", entity_type: "ORG", mention_count: 5 },
  { id: 2, name: "Bob", entity_type: "PERSON", mention_count: 2 },
];

let entitiesResp;

const entityListCalls = () =>
  api.get.mock.calls.filter((c) => c[0].includes("/kg/entities?"));

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  entitiesResp = { entities: ENTITIES, total: 2 };
  api.get.mockImplementation((path) => {
    if (path.includes("/kg/entities?")) return Promise.resolve(entitiesResp);
    if (path.includes("/kg/duplicates")) return Promise.resolve({ candidates: [] });
    return Promise.resolve({});
  });
  api.delete.mockResolvedValue({});
  api.patch.mockResolvedValue({});
  api.post.mockResolvedValue({});
  window.confirm = jest.fn(() => true);
});

const renderPanel = async () => {
  render(<EntitiesPanel project={PROJECT} />);
  await screen.findByText("Acme");
};

describe("EntitiesPanel listing", () => {
  it("fetches entities on mount with default pagination and renders rows", async () => {
    await renderPanel();
    expect(api.get).toHaveBeenCalledWith(
      "/projects/1/kg/entities?limit=50&offset=0",
      "tok"
    );
    expect(screen.getByText("Bob")).toBeInTheDocument();
    expect(screen.getByText("ORG")).toBeInTheDocument();
    expect(screen.getByText("PERSON")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  it("shows the empty-state alert when there are no entities", async () => {
    entitiesResp = { entities: [], total: 0 };
    render(<EntitiesPanel project={PROJECT} />);
    expect(await screen.findByText(/No entities yet/)).toBeInTheDocument();
  });

  it("refetches with the search term and resets to page 0", async () => {
    const user = userEvent.setup();
    await renderPanel();

    await user.type(screen.getByPlaceholderText("Search entities..."), "Ac");
    await waitFor(
      () => {
        const last = entityListCalls().pop();
        expect(last[0]).toContain("search=Ac");
        expect(last[0]).toContain("offset=0");
      },
      { timeout: 3000 }
    );
  });

  it("refetches when the type filter changes", async () => {
    const user = userEvent.setup();
    await renderPanel();

    await user.click(screen.getByRole("combobox", { name: "Type" }));
    await user.click(await screen.findByRole("option", { name: "Person" }));

    await waitFor(
      () => {
        const last = entityListCalls().pop();
        expect(last[0]).toContain("type=PERSON");
      },
      { timeout: 3000 }
    );
  });
});

describe("EntitiesPanel row actions", () => {
  it("delete confirms, hits the API and refreshes", async () => {
    const user = userEvent.setup();
    await renderPanel();
    const before = entityListCalls().length;

    const acmeRow = screen.getByText("Acme").closest("tr");
    await user.click(within(acmeRow).getByTestId("DeleteIcon").closest("button"));

    expect(window.confirm).toHaveBeenCalledWith(
      'Delete entity "Acme"? This removes all its mentions and relationships.'
    );
    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith("/projects/1/kg/entities/1", "tok")
    );
    await waitFor(() => expect(entityListCalls().length).toBe(before + 1));
    expect(toast.success).toHaveBeenCalledWith("Entity deleted");
  });

  it("delete aborted by confirm does nothing", async () => {
    window.confirm = jest.fn(() => false);
    const user = userEvent.setup();
    await renderPanel();

    const acmeRow = screen.getByText("Acme").closest("tr");
    await user.click(within(acmeRow).getByTestId("DeleteIcon").closest("button"));
    expect(api.delete).not.toHaveBeenCalled();
  });

  it("rename dialog patches the new name", async () => {
    const user = userEvent.setup();
    await renderPanel();

    const acmeRow = screen.getByText("Acme").closest("tr");
    await user.click(within(acmeRow).getByTestId("EditIcon").closest("button"));

    const nameField = await screen.findByLabelText("Name");
    await user.clear(nameField);
    await user.type(nameField, "ACME Corp");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        "/projects/1/kg/entities/1",
        { name: "ACME Corp" },
        "tok"
      )
    );
    expect(toast.success).toHaveBeenCalledWith("Entity renamed");
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument()
    );
  });

  it("merge dialog posts source→target with an integer target id", async () => {
    const user = userEvent.setup();
    await renderPanel();

    const acmeRow = screen.getByText("Acme").closest("tr");
    await user.click(within(acmeRow).getByTestId("MergeTypeIcon").closest("button"));

    await user.type(await screen.findByLabelText("Target entity ID"), "2");
    await user.click(screen.getByRole("button", { name: "Merge" }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/projects/1/kg/entities/1/merge",
        { target_id: 2 },
        "tok"
      )
    );
    expect(toast.success).toHaveBeenCalledWith("Entities merged");
  });
});

describe("EntitiesPanel toolbox", () => {
  it("find duplicates lists candidates and merging removes the pair", async () => {
    api.get.mockImplementation((path) => {
      if (path.includes("/kg/entities?")) return Promise.resolve(entitiesResp);
      if (path.includes("/kg/duplicates"))
        return Promise.resolve({
          candidates: [
            {
              entity_a_id: 1,
              entity_a_name: "Acme",
              entity_b_id: 2,
              entity_b_name: "ACME Inc",
              similarity: 0.92,
            },
          ],
        });
      return Promise.resolve({});
    });
    const user = userEvent.setup();
    await renderPanel();

    await user.click(screen.getByRole("button", { name: /Find Duplicates/ }));
    expect(await screen.findByText("Potential Duplicates")).toBeInTheDocument();
    expect(screen.getByText("ACME Inc")).toBeInTheDocument();
    expect(screen.getByText("92%")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Merge" }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/projects/1/kg/entities/2/merge",
        { target_id: 1 },
        "tok"
      )
    );
    // Pair removed from the dialog → success state
    expect(await screen.findByText("No potential duplicates found.")).toBeInTheDocument();
  });

  it("empty duplicate scan shows the all-clear alert", async () => {
    const user = userEvent.setup();
    await renderPanel();
    await user.click(screen.getByRole("button", { name: /Find Duplicates/ }));
    expect(await screen.findByText("No potential duplicates found.")).toBeInTheDocument();
  });

  // Kept last: the rebuild handler schedules a 3s-delayed refetch that would
  // otherwise fire mid-way through a later test.
  it("rebuild confirms and posts, toasting the scheduled message", async () => {
    api.post.mockResolvedValue({ message: "Rebuild scheduled in background" });
    const user = userEvent.setup();
    await renderPanel();

    await user.click(screen.getByRole("button", { name: /Rebuild Graph/ }));
    expect(window.confirm).toHaveBeenCalled();
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/projects/1/kg/rebuild", {}, "tok")
    );
    expect(toast.success).toHaveBeenCalledWith("Rebuild scheduled in background");
  });
});
