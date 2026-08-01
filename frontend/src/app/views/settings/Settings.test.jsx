import { render as rtlRender, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import SettingsPage from "./Settings";

// ProjectTabNav's useMediaQuery takes a function query — needs a real theme.
const theme = createTheme();
const render = (ui) => rtlRender(<ThemeProvider theme={theme}>{ui}</ThemeProvider>);
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
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";
jest.mock("app/contexts/PlatformContext", () => ({
  usePlatformCapabilities: jest.fn(),
}));
import { usePlatformCapabilities } from "app/contexts/PlatformContext";

// Full settings payload — the component does setForm(data) (full replace),
// so the mock must carry every key the form binds or inputs go uncontrolled.
const makeSettings = (overrides = {}) => ({
  app_name: "AcmeAI",
  logo_url: "",
  hide_branding: false,
  max_audio_upload_size: "25",
  data_retention_days: "30",
  currency: "EUR",
  redis_host: "redis.local",
  redis_port: "6379",
  redis_password: "",
  redis_database: "0",
  auth_disable_local: false,
  sso_auto_create_user: true,
  sso_allowed_domains: "*",
  sso_google_client_id: "google-id",
  sso_google_client_secret: "supersecret",
  sso_google_redirect_uri: "",
  sso_google_scope: "openid email profile",
  sso_microsoft_client_id: "",
  sso_microsoft_client_secret: "",
  sso_microsoft_tenant_id: "",
  sso_microsoft_redirect_uri: "",
  sso_microsoft_scope: "openid email profile",
  sso_github_client_id: "",
  sso_github_client_secret: "",
  sso_github_redirect_uri: "",
  sso_github_scope: "user:email",
  sso_oidc_client_id: "",
  sso_oidc_client_secret: "",
  sso_oidc_provider_url: "",
  sso_oidc_redirect_uri: "",
  sso_oidc_scopes: "openid email profile",
  sso_oidc_provider_name: "SSO",
  sso_auto_restricted: true,
  sso_auto_team_id: "",
  sso_oidc_email_claim: "email",
  mcp_enabled: false,
  docker_enabled: true,
  docker_url: "tcp://docker:2375",
  docker_image: "python:3.12-slim",
  docker_timeout: "600",
  docker_network: "none",
  docker_read_only: true,
  browser_enabled: false,
  browser_image: "mcr.microsoft.com/playwright/python:v1.48.0-jammy",
  browser_network: "bridge",
  browser_timeout: 900,
  system_llm: "gpt4",
  enforce_2fa: false,
  vectordb_chromadb_enabled: true,
  vectordb_chromadb_host: "",
  vectordb_chromadb_port: "",
  vectordb_pgvector_enabled: false,
  vectordb_pgvector_host: "",
  vectordb_pgvector_port: "5432",
  vectordb_pgvector_user: "",
  vectordb_pgvector_password: "",
  vectordb_pgvector_db: "restai_vectors",
  vectordb_weaviate_enabled: false,
  vectordb_weaviate_host: "",
  vectordb_weaviate_port: "8080",
  vectordb_weaviate_grpc_port: "50051",
  vectordb_weaviate_api_key: "",
  vectordb_pinecone_enabled: false,
  vectordb_pinecone_api_key: "",
  vectordb_pinecone_index: "",
  ldap_enabled: false,
  ldap_server_host: "",
  ldap_server_port: "",
  ldap_attribute_for_mail: "mail",
  ldap_attribute_for_username: "uid",
  ldap_search_base: "",
  ldap_search_filters: "",
  ldap_app_dn: "",
  ldap_app_password: "",
  ldap_use_tls: false,
  ldap_ca_cert_file: "",
  ldap_ciphers: "",
  smtp_host: "smtp.acme.io",
  smtp_port: "587",
  smtp_user: "",
  smtp_password: "",
  smtp_from: "",
  email_default_to: "",
  payment_enabled: false,
  payment_stripe_enabled: false,
  payment_stripe_secret_key: "",
  payment_stripe_publishable_key: "",
  payment_stripe_webhook_secret: "",
  payment_paypal_enabled: false,
  payment_paypal_client_id: "",
  payment_paypal_client_secret: "",
  payment_paypal_webhook_id: "",
  payment_paypal_mode: "sandbox",
  ...overrides,
});

let settingsResp;
let refreshCapabilities;

beforeEach(() => {
  jest.clearAllMocks();
  window.history.replaceState(null, "", "/");
  Element.prototype.scrollIntoView = jest.fn();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  refreshCapabilities = jest.fn();
  usePlatformCapabilities.mockReturnValue({ refreshCapabilities });
  settingsResp = () => Promise.resolve(makeSettings());
  api.get.mockImplementation((path) => {
    if (path === "/settings") return settingsResp();
    if (path === "/teams") return Promise.resolve({ teams: [{ id: 7, name: "acme-team" }] });
    if (path === "/llms") return Promise.resolve([{ id: 1, name: "gpt4" }, { id: 2, name: "llama3" }]);
    if (path === "/version") return Promise.resolve({ telemetry: true });
    return Promise.resolve({});
  });
  api.patch.mockImplementation(() => Promise.resolve(makeSettings()));
  api.post.mockResolvedValue({});
});

const renderSettings = async () => {
  render(<SettingsPage />);
  // Wait for the fetched settings to land in the form.
  await screen.findByDisplayValue("AcmeAI");
};

describe("Settings initial load", () => {
  it("fetches /settings, /teams, /llms and /version on mount and fills the form", async () => {
    await renderSettings();

    expect(api.get).toHaveBeenCalledWith("/settings", "tok");
    expect(api.get).toHaveBeenCalledWith("/teams", "tok");
    expect(api.get).toHaveBeenCalledWith("/llms", "tok");
    expect(api.get).toHaveBeenCalledWith("/version", "tok", { silent: true });

    expect(screen.getByLabelText("settings.fields.appName")).toHaveValue("AcmeAI");
    expect(screen.getByLabelText("settings.fields.redisHost")).toHaveValue("redis.local");
    // System LLM select shows the fetched value.
    expect(screen.getByText("gpt4")).toBeInTheDocument();
  });

  it("renders the docker sub-fields only when docker is enabled", async () => {
    await renderSettings();
    expect(screen.getByLabelText("settings.fields.dockerUrl")).toHaveValue("tcp://docker:2375");
  });

  it("hides docker sub-fields when docker is disabled", async () => {
    settingsResp = () => Promise.resolve(makeSettings({ docker_enabled: false }));
    render(<SettingsPage />);
    await screen.findByDisplayValue("AcmeAI");
    expect(screen.queryByLabelText("settings.fields.dockerUrl")).not.toBeInTheDocument();
  });
});

describe("Settings section navigation", () => {
  it("switches to the notifications tab and shows the SMTP fields", async () => {
    const user = userEvent.setup();
    await renderSettings();

    expect(screen.queryByLabelText("settings.fields.smtpHost")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "settings.sections.notifications" }));
    expect(screen.getByLabelText("settings.fields.smtpHost")).toHaveValue("smtp.acme.io");
    // General tab content is gone.
    expect(screen.queryByLabelText("settings.fields.appName")).not.toBeInTheDocument();
  });

  it("switches to the vectordbs tab and shows the pinecone card", async () => {
    const user = userEvent.setup();
    await renderSettings();
    await user.click(screen.getByRole("button", { name: "settings.sections.vectordbs" }));
    expect(screen.getByLabelText("settings.fields.vectordbPineconeIndex")).toBeInTheDocument();
  });

  it("deep-links via #microsoft hash to the authentication tab", async () => {
    window.history.replaceState(null, "", "/#microsoft");
    render(<SettingsPage />);

    // Authentication tab content is active (tenant id lives only there);
    // the general tab (app name field) is not rendered.
    expect(await screen.findByLabelText("settings.fields.tenantId")).toBeInTheDocument();
    expect(screen.queryByLabelText("settings.fields.appName")).not.toBeInTheDocument();
    await waitFor(() => expect(Element.prototype.scrollIntoView).toHaveBeenCalled());
  });
});

describe("Settings save", () => {
  it("PATCHes the edited form with numeric fields parsed to ints", async () => {
    const user = userEvent.setup();
    await renderSettings();

    const appName = screen.getByLabelText("settings.fields.appName");
    await user.clear(appName);
    await user.type(appName, "RenamedAI");

    await user.click(screen.getByRole("button", { name: "settings.helpers.saveSettings" }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        "/settings",
        expect.objectContaining({
          app_name: "RenamedAI",
          // "25"/"30"/"600" strings from the server get parsed on save.
          max_audio_upload_size: 25,
          data_retention_days: 30,
          docker_timeout: 600,
        }),
        "tok"
      )
    );
    expect(toast.success).toHaveBeenCalledWith("settings.saved");
    expect(refreshCapabilities).toHaveBeenCalled();
  });

  it("saves an edited secret field (Google client secret) from the authentication tab", async () => {
    const user = userEvent.setup();
    await renderSettings();

    await user.click(screen.getByRole("button", { name: "settings.sections.authentication" }));
    // Expand the Google SSO card.
    await user.click(screen.getByText("Google"));

    // Google's card holds the first clientSecret field (LDAP card above it
    // uses ldapAppPassword); all Collapse contents stay mounted.
    const secret = screen.getAllByLabelText("settings.fields.clientSecret")[0];
    expect(secret).toHaveValue("supersecret");
    await user.clear(secret);
    await user.type(secret, "new-secret-42");

    await user.click(screen.getByRole("button", { name: "settings.helpers.saveSettings" }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        "/settings",
        expect.objectContaining({ sso_google_client_secret: "new-secret-42" }),
        "tok"
      )
    );
  });
});

describe("Settings docker test-connection", () => {
  it("POSTs /settings/docker/test and shows the connected version", async () => {
    api.post.mockResolvedValue({ server_version: "27.1.1" });
    const user = userEvent.setup();
    await renderSettings();

    await user.click(screen.getByRole("button", { name: "settings.fields.testDocker" }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/settings/docker/test", {}, "tok")
    );
    expect(await screen.findByText("Connected (Docker 27.1.1)")).toBeInTheDocument();
  });

  it("shows the error detail when the docker test fails", async () => {
    api.post.mockRejectedValue({ detail: "no route to host" });
    const user = userEvent.setup();
    await renderSettings();

    await user.click(screen.getByRole("button", { name: "settings.fields.testDocker" }));
    expect(await screen.findByText("no route to host")).toBeInTheDocument();
  });

  it("disables the docker test button when no docker URL is set", async () => {
    settingsResp = () => Promise.resolve(makeSettings({ docker_url: "" }));
    render(<SettingsPage />);
    await screen.findByDisplayValue("AcmeAI");
    expect(screen.getByRole("button", { name: "settings.fields.testDocker" })).toBeDisabled();
  });
});

describe("Settings authentication tab", () => {
  it("lists teams in the SSO default-team select", async () => {
    const user = userEvent.setup();
    await renderSettings();

    await user.click(screen.getByRole("button", { name: "settings.sections.authentication" }));
    const combos = screen.getAllByRole("combobox");
    // Default team select is the only combobox on the authentication tab.
    await user.click(combos[0]);
    const listbox = await screen.findByRole("listbox");
    expect(within(listbox).getByText("acme-team")).toBeInTheDocument();
  });
});
