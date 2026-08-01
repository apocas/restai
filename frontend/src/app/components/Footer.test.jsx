import { render, screen, waitFor } from "@testing-library/react";
import Footer from "./Footer";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";

jest.mock("app/hooks/useAuth", () => jest.fn());
jest.mock("app/utils/api", () => ({ get: jest.fn() }));
jest.mock("app/contexts/PlatformContext", () => ({
  usePlatformCapabilities: jest.fn(),
}));

beforeEach(() => {
  jest.clearAllMocks();
  usePlatformCapabilities.mockReturnValue({
    platformCapabilities: { hide_branding: false },
  });
  useAuth.mockReturnValue({ isAuthenticated: false, user: null });
  api.get.mockResolvedValue({});
});

describe("Footer", () => {
  it("shows the branding line and Source link when branding is visible", () => {
    render(<Footer />);
    expect(screen.getByText(/Powered by/i)).toBeInTheDocument();
    const source = screen.getByRole("link", { name: /source/i });
    expect(source).toHaveAttribute("href", "https://github.com/apocas/restai");
  });

  it("hides the branding line when hide_branding is set", () => {
    usePlatformCapabilities.mockReturnValue({
      platformCapabilities: { hide_branding: true },
    });
    render(<Footer />);
    expect(screen.queryByText(/Powered by/i)).not.toBeInTheDocument();
    // Source link stays regardless.
    expect(screen.getByRole("link", { name: /source/i })).toBeInTheDocument();
  });

  it("does not fetch version info when unauthenticated", () => {
    render(<Footer />);
    expect(api.get).not.toHaveBeenCalled();
  });

  it("fetches and renders the version pill when authenticated", async () => {
    useAuth.mockReturnValue({ isAuthenticated: true, user: { token: "tok" } });
    api.get.mockImplementation((path) => {
      if (path === "/version") return Promise.resolve({ version: "1.2.3" });
      return Promise.resolve({ current: "1.2.3", update_available: false });
    });

    render(<Footer />);

    const pill = await screen.findByRole("link", { name: /v\s*1\.2\.3/i });
    expect(pill).toHaveAttribute(
      "href",
      "https://github.com/apocas/restai/releases/tag/v1.2.3"
    );
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith("/version", "tok", expect.any(Object));
      expect(api.get).toHaveBeenCalledWith("/version/check", "tok", expect.any(Object));
    });
    expect(screen.queryByText(/Update v/i)).not.toBeInTheDocument();
  });

  it("shows the update pill when an update is available", async () => {
    useAuth.mockReturnValue({ isAuthenticated: true, user: { token: "tok" } });
    api.get.mockImplementation((path) => {
      if (path === "/version") return Promise.resolve({ version: "1.2.3" });
      return Promise.resolve({
        current: "1.2.3",
        update_available: true,
        latest: "1.3.0",
        latest_url: "https://example.com/release",
      });
    });

    render(<Footer />);

    const update = await screen.findByRole("link", { name: /update v1\.3\.0/i });
    expect(update).toHaveAttribute("href", "https://example.com/release");
  });

  it("survives version endpoints failing", async () => {
    useAuth.mockReturnValue({ isAuthenticated: true, user: { token: "tok" } });
    api.get.mockRejectedValue(new Error("boom"));

    render(<Footer />);

    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
    expect(screen.getByText(/Powered by/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /v\d/ })).not.toBeInTheDocument();
  });
});
