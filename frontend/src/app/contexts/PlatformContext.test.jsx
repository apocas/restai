import { render, screen, waitFor, act } from "@testing-library/react";
import PlatformProvider, { usePlatformCapabilities } from "./PlatformContext";

let ctx;
function Probe() {
  ctx = usePlatformCapabilities();
  return (
    <div>
      <span data-testid="loading">{String(ctx.isLoading)}</span>
      <span data-testid="app">{ctx.platformCapabilities.app_name}</span>
      <span data-testid="gpu">{String(ctx.platformCapabilities.gpu)}</span>
    </div>
  );
}

const renderPlatform = () =>
  render(
    <PlatformProvider>
      <Probe />
    </PlatformProvider>
  );

beforeEach(() => {
  ctx = undefined;
  global.fetch = jest.fn();
});

afterAll(() => {
  delete global.fetch;
});

describe("PlatformProvider", () => {
  it("loads capabilities from /setup and clears the loading flag", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ gpu: true, app_name: "Acme AI", sso: ["google"] }),
    });
    renderPlatform();
    expect(screen.getByTestId("loading")).toHaveTextContent("true");

    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
    expect(screen.getByTestId("app")).toHaveTextContent("Acme AI");
    expect(screen.getByTestId("gpu")).toHaveTextContent("true");
    expect(global.fetch).toHaveBeenCalledWith("/setup");
    expect(ctx.platformCapabilities.sso).toEqual(["google"]);
    // Absent fields fall back to safe defaults.
    expect(ctx.platformCapabilities.payments_enabled).toBe(false);
  });

  it("keeps defaults and stops loading when /setup fails", async () => {
    const spy = jest.spyOn(console, "error").mockImplementation(() => {});
    global.fetch.mockRejectedValue(new Error("network down"));
    renderPlatform();
    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
    expect(screen.getByTestId("app")).toHaveTextContent("RESTai");
    spy.mockRestore();
  });

  it("refreshCapabilities re-fetches on demand", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ app_name: "First" }),
    });
    renderPlatform();
    await waitFor(() => expect(screen.getByTestId("app")).toHaveTextContent("First"));

    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ app_name: "Second" }),
    });
    await act(async () => {
      await ctx.refreshCapabilities();
    });
    expect(screen.getByTestId("app")).toHaveTextContent("Second");
  });
});
