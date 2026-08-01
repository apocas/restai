import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import OllamaModels from "./OllamaModels";
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

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}));

// Breadcrumb pulls NavLink from react-router-dom — stub the whole thing.
jest.mock("app/components/Breadcrumb", () => () => null);

// ESM-only leaf widgets — stub.
jest.mock("@microlink/react-json-view", () => (props) =>
  require("react").createElement(
    "pre",
    { "data-testid": "json-view" },
    JSON.stringify(props.src)
  )
);

// mui-datatables: dump every row, running each column's customBodyRender so
// the real per-row action buttons (Add / Pull) are clickable in tests.
jest.mock("mui-datatables", () => (props) => {
  const React = require("react");
  return React.createElement(
    "div",
    { "data-testid": "datatable" },
    React.createElement("div", { "data-testid": "datatable-title" }, props.title),
    props.data.map((row, ri) =>
      React.createElement(
        "div",
        { key: ri, "data-testid": `row-${ri}` },
        props.columns.map((col, ci) => {
          const body = col.options && col.options.customBodyRender;
          return React.createElement(
            "span",
            { key: ci },
            body ? body(row[ci]) : String(row[ci])
          );
        })
      )
    )
  );
});

const LOCAL_MODELS = [
  {
    name: "llama3",
    size: 4 * 1024 * 1024 * 1024,
    modified_at: "2025-01-01T00:00:00Z",
    details: { families: ["llama"] },
  },
  {
    name: "nomic-embed-text",
    embedding_length: 768,
    capabilities: ["embedding"],
    details: {},
  },
  {
    name: "llava",
    details: { families: ["clip", "llama"] },
  },
];

const CLOUD_MODELS = [
  { name: "gpt-oss:120b-cloud", details: {} },
  { name: "cloud-embed-thing", details: {} },
];

beforeAll(() => {
  // jsdom doesn't implement scrollIntoView; the add-form scrolls itself into view.
  window.HTMLElement.prototype.scrollIntoView = jest.fn();
});

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  api.post.mockImplementation((path) => {
    if (path === "/tools/ollama/models") return Promise.resolve(LOCAL_MODELS);
    if (path === "/tools/ollama/cloud/models") return Promise.resolve(CLOUD_MODELS);
    if (path === "/tools/ollama/pull") return Promise.resolve({});
    if (path === "/llms") return Promise.resolve({ id: 9 });
    if (path === "/embeddings") return Promise.resolve({ id: 4 });
    return Promise.resolve({});
  });
});

const connectLocal = async (user) => {
  await user.click(screen.getByRole("button", { name: /Connect/ }));
  await screen.findByTestId("datatable");
};

const listCalls = (path) => api.post.mock.calls.filter((c) => c[0] === path);

describe("OllamaModels local listing", () => {
  it("connects with the default host/port and lists models by kind", async () => {
    const user = userEvent.setup();
    render(<OllamaModels />);
    await connectLocal(user);

    expect(api.post).toHaveBeenCalledWith(
      "/tools/ollama/models",
      { host: "localhost", port: 11434 },
      "tok"
    );
    expect(screen.getByTestId("datatable-title")).toHaveTextContent("Available Ollama Models");
    expect(screen.getByText("llama3")).toBeInTheDocument();
    expect(screen.getByText("nomic-embed-text")).toBeInTheDocument();
    // Type chips: llama3=LLM, nomic=Embedding, llava=Vision
    expect(screen.getByText("Embedding")).toBeInTheDocument();
    expect(screen.getByText("Vision")).toBeInTheDocument();
    expect(toast.success).toHaveBeenCalledWith(
      "Found 3 models on Ollama instance at localhost:11434"
    );
  });

  it("uses edited host/port in the connect payload", async () => {
    const user = userEvent.setup();
    render(<OllamaModels />);

    const host = screen.getByLabelText(/Host/);
    await user.clear(host);
    await user.type(host, "gpubox");
    await connectLocal(user);

    expect(api.post).toHaveBeenCalledWith(
      "/tools/ollama/models",
      { host: "gpubox", port: 11434 },
      "tok"
    );
  });

  it("shows no table and no pull section when the connect fails", async () => {
    const errSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    api.post.mockRejectedValue(new Error("boom"));
    const user = userEvent.setup();
    render(<OllamaModels />);

    await user.click(screen.getByRole("button", { name: /Connect/ }));
    await waitFor(() => expect(errSpy).toHaveBeenCalled());
    expect(screen.queryByTestId("datatable")).not.toBeInTheDocument();
    expect(screen.queryByText("Pull New Model")).not.toBeInTheDocument();
    errSpy.mockRestore();
  });
});

describe("OllamaModels pulling", () => {
  it("pulls a new model by name and refreshes the listing", async () => {
    const user = userEvent.setup();
    render(<OllamaModels />);
    await connectLocal(user);

    await user.type(screen.getByLabelText(/Model Name/), "gemma");
    await user.click(screen.getByRole("button", { name: /Pull Model/ }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/tools/ollama/pull",
        { name: "gemma", host: "localhost", port: 11434 },
        "tok"
      )
    );
    expect(toast.info).toHaveBeenCalledWith(expect.stringContaining("Pulling model gemma"));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Successfully pulled model gemma"));
    // Initial connect + post-pull refresh
    await waitFor(() => expect(listCalls("/tools/ollama/models")).toHaveLength(2));
  });

  it("re-pulls an existing model from its row action", async () => {
    const user = userEvent.setup();
    render(<OllamaModels />);
    await connectLocal(user);

    const row0 = screen.getByTestId("row-0");
    await user.click(row0.querySelector('[title="Pull/Update Model"]'));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/tools/ollama/pull",
        { name: "llama3", host: "localhost", port: 11434 },
        "tok"
      )
    );
  });
});

describe("OllamaModels add-to-system", () => {
  it("creates a plain Ollama LLM with local base_url and navigates to the created id", async () => {
    const user = userEvent.setup();
    render(<OllamaModels />);
    await connectLocal(user);

    await user.click(screen.getByTestId("row-0").querySelector('[title="Add to System"]'));
    expect(screen.getByRole("heading", { name: "Add Model to System" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add Model to System" }));

    await waitFor(() => expect(listCalls("/llms")).toHaveLength(1));
    const payload = listCalls("/llms")[0][1];
    expect(payload).toMatchObject({
      name: "llama3",
      class_name: "Ollama",
      privacy: "private",
      description: "Ollama model llama3 from localhost:11434",
    });
    expect(JSON.parse(payload.options)).toEqual({
      model: "llama3",
      temperature: 0.1,
      keep_alive: 0,
      request_timeout: 120,
      base_url: "http://localhost:11434",
    });
    expect(mockNavigate).toHaveBeenCalledWith("/llm/9");
  });

  it("picks the multimodal class for clip-family models", async () => {
    const user = userEvent.setup();
    render(<OllamaModels />);
    await connectLocal(user);

    await user.click(screen.getByTestId("row-2").querySelector('[title="Add to System"]'));
    await user.click(screen.getByRole("button", { name: "Add Model to System" }));

    await waitFor(() => expect(listCalls("/llms")).toHaveLength(1));
    expect(listCalls("/llms")[0][1].class_name).toBe("OllamaMultiModal2");
  });

  it("creates an OllamaEmbeddings row for embedding-capable models", async () => {
    const user = userEvent.setup();
    render(<OllamaModels />);
    await connectLocal(user);

    await user.click(screen.getByTestId("row-1").querySelector('[title="Add to System"]'));
    await user.click(screen.getByRole("button", { name: "Add Model to System" }));

    await waitFor(() => expect(listCalls("/embeddings")).toHaveLength(1));
    const payload = listCalls("/embeddings")[0][1];
    expect(payload).toMatchObject({
      name: "nomic-embed-text",
      class_name: "OllamaEmbeddings",
      dimension: 768,
      privacy: "private",
    });
    expect(JSON.parse(payload.options)).toEqual({
      model_name: "nomic-embed-text",
      base_url: "http://localhost:11434",
      keep_alive: 0,
      mirostat: 0,
    });
    expect(listCalls("/llms")).toHaveLength(0);
    expect(mockNavigate).toHaveBeenCalledWith("/embedding/4");
  });

  it("sanitizes illegal characters in the RESTai name but keeps the upstream model id", async () => {
    api.post.mockImplementation((path) => {
      if (path === "/tools/ollama/models")
        return Promise.resolve([{ name: "hf.co/library/foo", details: {} }]);
      if (path === "/llms") return Promise.resolve({ id: 11 });
      return Promise.resolve({});
    });
    const user = userEvent.setup();
    render(<OllamaModels />);
    await connectLocal(user);

    await user.click(screen.getByTestId("row-0").querySelector('[title="Add to System"]'));
    await user.click(screen.getByRole("button", { name: "Add Model to System" }));

    await waitFor(() => expect(listCalls("/llms")).toHaveLength(1));
    const payload = listCalls("/llms")[0][1];
    expect(payload.name).toBe("hf.co_library_foo");
    expect(JSON.parse(payload.options).model).toBe("hf.co/library/foo");
    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining("renamed from"));
  });

  it("cancel closes the add form without posting", async () => {
    const user = userEvent.setup();
    render(<OllamaModels />);
    await connectLocal(user);

    await user.click(screen.getByTestId("row-0").querySelector('[title="Add to System"]'));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText("Add Model to System")).not.toBeInTheDocument();
    expect(listCalls("/llms")).toHaveLength(0);
  });
});

describe("OllamaModels cloud mode", () => {
  const connectCloud = async (user) => {
    await user.click(screen.getByRole("tab", { name: /Ollama Cloud/ }));
    await user.type(screen.getByLabelText(/API Key/), "ollama_secret");
    await user.click(screen.getByRole("button", { name: /Connect/ }));
    await screen.findByTestId("datatable");
  };

  it("requires an API key before connecting", async () => {
    const user = userEvent.setup();
    render(<OllamaModels />);
    await user.click(screen.getByRole("tab", { name: /Ollama Cloud/ }));
    expect(screen.getByRole("button", { name: /Connect/ })).toBeDisabled();
  });

  it("lists cloud models with the key in the request body", async () => {
    const user = userEvent.setup();
    render(<OllamaModels />);
    await connectCloud(user);

    expect(api.post).toHaveBeenCalledWith(
      "/tools/ollama/cloud/models",
      { api_key: "ollama_secret" },
      "tok"
    );
    expect(screen.getByTestId("datatable-title")).toHaveTextContent(
      "Available Ollama Cloud Models"
    );
    // Pull is local-only — no pull buttons in cloud mode.
    expect(document.querySelector('[title="Pull/Update Model"]')).toBeNull();
    expect(screen.queryByText("Pull New Model")).not.toBeInTheDocument();
  });

  it("creates an OllamaCloud LLM carrying the api_key and cloud base_url", async () => {
    const user = userEvent.setup();
    render(<OllamaModels />);
    await connectCloud(user);

    await user.click(screen.getByTestId("row-0").querySelector('[title="Add to System"]'));
    await user.click(screen.getByRole("button", { name: "Add Model to System" }));

    await waitFor(() => expect(listCalls("/llms")).toHaveLength(1));
    const payload = listCalls("/llms")[0][1];
    expect(payload).toMatchObject({
      name: "gpt-oss:120b-cloud",
      class_name: "OllamaCloud",
      description: "Ollama model gpt-oss:120b-cloud from Ollama Cloud",
    });
    expect(JSON.parse(payload.options)).toMatchObject({
      model: "gpt-oss:120b-cloud",
      base_url: "https://ollama.com",
      api_key: "ollama_secret",
    });
    expect(mockNavigate).toHaveBeenCalledWith("/llm/9");
  });

  it("blocks adding embedding-looking models from the cloud", async () => {
    const user = userEvent.setup();
    render(<OllamaModels />);
    await connectCloud(user);

    await user.click(screen.getByTestId("row-1").querySelector('[title="Add to System"]'));
    await user.click(screen.getByRole("button", { name: "Add Model to System" }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Ollama Cloud doesn't expose embedding models. Pick an LLM instead."
      )
    );
    expect(listCalls("/embeddings")).toHaveLength(0);
    expect(listCalls("/llms")).toHaveLength(0);
    // Form stays open so the user can cancel.
    expect(screen.getByRole("heading", { name: "Add Model to System" })).toBeInTheDocument();
  });

  it("switching modes clears the previous listing", async () => {
    const user = userEvent.setup();
    render(<OllamaModels />);
    await connectLocal(user);
    expect(screen.getByTestId("datatable")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /Ollama Cloud/ }));
    expect(screen.queryByTestId("datatable")).not.toBeInTheDocument();
  });
});
