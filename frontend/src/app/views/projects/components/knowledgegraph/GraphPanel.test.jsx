import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import GraphPanel from "./GraphPanel";
import api from "app/utils/api";
import { Network } from "vis-network/standalone/esm/vis-network";

jest.mock("app/utils/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  delete: jest.fn(),
}));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";

// vis-network is ESM-only — stub the constructor and record instances.
// CRA's jest config has resetMocks:true, so the implementation must be
// (re)applied in beforeEach, not in the factory.
jest.mock("vis-network/standalone/esm/vis-network", () => ({
  Network: jest.fn(),
}));
jest.mock("vis-network/styles/vis-network.css", () => ({}));

const PROJECT = { id: 1, name: "proj" };

const GRAPH = {
  nodes: [
    { id: 1, label: "Acme", type: "ORG", mention_count: 5 },
    { id: 2, label: "Bob", type: "PERSON", mention_count: 2 },
  ],
  edges: [{ from: 1, to: 2, weight: 3 }],
};

const DETAIL = {
  name: "Acme",
  entity_type: "ORG",
  mention_count: 5,
  mentions: [{ source: "doc.pdf", mention_count: 3 }],
  related: [{ id: 2, name: "Bob" }],
};

let graphResp;

const graphCalls = () => api.get.mock.calls.filter((c) => c[0].includes("/kg/graph"));

beforeEach(() => {
  jest.clearAllMocks();
  Network.mockImplementation(() => ({ on: jest.fn(), destroy: jest.fn() }));
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  graphResp = GRAPH;
  api.get.mockImplementation((path) => {
    // Fresh clone per call — returning the same reference would make React
    // bail out of the setData update on refetch (no network rebuild).
    if (path.includes("/kg/graph"))
      return Promise.resolve(JSON.parse(JSON.stringify(graphResp)));
    if (path.includes("/kg/entities/")) return Promise.resolve(DETAIL);
    return Promise.resolve({});
  });
});

describe("GraphPanel", () => {
  it("fetches the graph on mount and builds a vis Network from it", async () => {
    render(<GraphPanel project={PROJECT} />);

    await waitFor(() => expect(Network).toHaveBeenCalledTimes(1));
    expect(api.get).toHaveBeenCalledWith("/projects/1/kg/graph?limit=100", "tok");

    const [container, data, options] = Network.mock.calls[0];
    expect(container).toBeInstanceOf(HTMLElement);
    expect(data.nodes).toHaveLength(2);
    expect(data.nodes[0]).toMatchObject({ id: 1, label: "Acme", shape: "dot" });
    expect(data.edges[0]).toMatchObject({ from: 1, to: 2 });
    expect(options.physics.solver).toBe("forceAtlas2Based");
  });

  it("shows the empty-state alert and builds no network when there are no nodes", async () => {
    graphResp = { nodes: [], edges: [] };
    render(<GraphPanel project={PROJECT} />);
    expect(await screen.findByText(/No graph data yet/)).toBeInTheDocument();
    expect(Network).not.toHaveBeenCalled();
  });

  it("clicking a node fetches and renders the entity detail sidebar", async () => {
    render(<GraphPanel project={PROJECT} />);
    await waitFor(() => expect(Network).toHaveBeenCalledTimes(1));

    const instance = Network.mock.results[0].value;
    const clickHandler = instance.on.mock.calls.find((c) => c[0] === "click")[1];

    await act(async () => {
      clickHandler({ nodes: [1] });
    });

    expect(api.get).toHaveBeenCalledWith("/projects/1/kg/entities/1", "tok");
    expect(await screen.findByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("5 mentions")).toBeInTheDocument();
    expect(screen.getByText(/doc\.pdf \(3\)/)).toBeInTheDocument();
    expect(screen.getByText("Related Entities")).toBeInTheDocument();
    expect(screen.getByText("Bob")).toBeInTheDocument();
  });

  it("clicking empty canvas clears the selection", async () => {
    render(<GraphPanel project={PROJECT} />);
    await waitFor(() => expect(Network).toHaveBeenCalledTimes(1));
    const instance = Network.mock.results[0].value;
    const clickHandler = instance.on.mock.calls.find((c) => c[0] === "click")[1];

    await act(async () => {
      clickHandler({ nodes: [1] });
    });
    expect(await screen.findByText("5 mentions")).toBeInTheDocument();

    await act(async () => {
      clickHandler({ nodes: [] });
    });
    await waitFor(() =>
      expect(screen.queryByText("5 mentions")).not.toBeInTheDocument()
    );
  });

  it("changing the max-nodes limit refetches and rebuilds the network", async () => {
    const user = userEvent.setup();
    render(<GraphPanel project={PROJECT} />);
    await waitFor(() => expect(Network).toHaveBeenCalledTimes(1));

    await user.click(screen.getByRole("combobox", { name: "Max nodes" }));
    await user.click(await screen.findByRole("option", { name: "200" }));

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith("/projects/1/kg/graph?limit=200", "tok")
    );
    await waitFor(() => expect(Network).toHaveBeenCalledTimes(2));
    // The first network is destroyed before the rebuild.
    expect(Network.mock.results[0].value.destroy).toHaveBeenCalled();
  });

  it("changing the type filter adds the type param", async () => {
    const user = userEvent.setup();
    render(<GraphPanel project={PROJECT} />);
    await waitFor(() => expect(graphCalls().length).toBe(1));

    await user.click(screen.getByRole("combobox", { name: "Type filter" }));
    await user.click(await screen.findByRole("option", { name: "Organization" }));

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(
        "/projects/1/kg/graph?type=ORG&limit=100",
        "tok"
      )
    );
  });

  it("destroys the network on unmount", async () => {
    const { unmount } = render(<GraphPanel project={PROJECT} />);
    await waitFor(() => expect(Network).toHaveBeenCalledTimes(1));
    const instance = Network.mock.results[0].value;
    unmount();
    expect(instance.destroy).toHaveBeenCalled();
  });
});
