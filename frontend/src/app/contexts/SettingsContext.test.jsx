import { useContext } from "react";
import { render, screen, act } from "@testing-library/react";
import SettingsProvider, { SettingsContext } from "./SettingsContext";
import { MatxLayoutSettings } from "app/components/MatxLayout/settings";

let ctx;
function Probe() {
  ctx = useContext(SettingsContext);
  return <span data-testid="mode">{ctx.settings.layout1Settings ? "loaded" : "empty"}</span>;
}

describe("SettingsProvider", () => {
  it("defaults to MatxLayoutSettings", () => {
    render(
      <SettingsProvider>
        <Probe />
      </SettingsProvider>
    );
    expect(ctx.settings).toEqual(MatxLayoutSettings);
  });

  it("accepts an initial settings override", () => {
    const custom = { ...MatxLayoutSettings, activeLayout: "layout2" };
    render(
      <SettingsProvider settings={custom}>
        <Probe />
      </SettingsProvider>
    );
    expect(ctx.settings.activeLayout).toBe("layout2");
  });

  it("deep-merges updates instead of replacing wholesale", () => {
    render(
      <SettingsProvider>
        <Probe />
      </SettingsProvider>
    );
    const before = ctx.settings;
    act(() => ctx.updateSettings({ layout1Settings: { leftSidebar: { show: false } } }));
    // Updated leaf applied…
    expect(ctx.settings.layout1Settings.leftSidebar.show).toBe(false);
    // …while unrelated keys survive the merge.
    expect(ctx.settings.activeLayout).toBe(before.activeLayout);
  });
});
