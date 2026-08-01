import { render, screen, act } from "@testing-library/react";
import useSettings from "./useSettings";
import SettingsProvider from "app/contexts/SettingsContext";
import { MatxLayoutSettings } from "app/components/MatxLayout/settings";

let ctx;
function Probe() {
  ctx = useSettings();
  return (
    <div>
      <span data-testid="theme">{ctx.settings.activeTheme}</span>
      <span data-testid="layout">{ctx.settings.activeLayout}</span>
    </div>
  );
}

beforeEach(() => {
  ctx = undefined;
});

describe("useSettings", () => {
  it("exposes the default MatxLayoutSettings under a provider", () => {
    render(
      <SettingsProvider>
        <Probe />
      </SettingsProvider>
    );
    expect(screen.getByTestId("theme")).toHaveTextContent(MatxLayoutSettings.activeTheme);
    expect(screen.getByTestId("layout")).toHaveTextContent("layout1");
    expect(typeof ctx.updateSettings).toBe("function");
  });

  it("uses provider-supplied initial settings", () => {
    render(
      <SettingsProvider settings={{ ...MatxLayoutSettings, activeTheme: "purple1" }}>
        <Probe />
      </SettingsProvider>
    );
    expect(screen.getByTestId("theme")).toHaveTextContent("purple1");
  });

  it("updateSettings deep-merges updates into the current settings", () => {
    render(
      <SettingsProvider>
        <Probe />
      </SettingsProvider>
    );

    act(() => {
      ctx.updateSettings({ activeTheme: "red" });
    });
    expect(screen.getByTestId("theme")).toHaveTextContent("red");
    // Untouched keys survive the merge.
    expect(screen.getByTestId("layout")).toHaveTextContent("layout1");
    expect(ctx.settings.footer.show).toBe(true);
  });

  it("returns the inert default context outside a provider", () => {
    render(<Probe />);
    expect(ctx.settings).toBe(MatxLayoutSettings);
    // Default updateSettings is a no-op that must not throw.
    expect(() => ctx.updateSettings({ activeTheme: "red" })).not.toThrow();
  });
});
