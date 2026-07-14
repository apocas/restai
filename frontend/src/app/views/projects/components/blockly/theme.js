import * as Blockly from "blockly";

// RESTai Blockly theme — turns stock Blockly into part of the platform's
// command deck. Block hues mirror the dashboard's per-section accents
// (Home.jsx), the canvas gets a cool-paper grid, and cursor / insertion /
// selection markers use the platform blue so the workspace reads as one
// visual system with the rest of the app rather than a default library canvas.
//
// Built-in block/category style names (logic_blocks, loop_blocks, …) are
// overridden so the stock Logic/Loops/Math/Text/Lists/Variables blocks pick up
// the palette; the custom RESTai blocks reference the new `restai_blocks` style.
export const restaiBlocklyTheme = Blockly.Theme.defineTheme("restai", {
  base: Blockly.Themes.Classic,
  blockStyles: {
    restai_blocks: { colourPrimary: "#1976d2", colourSecondary: "#4a97e0", colourTertiary: "#155fa8" },
    logic_blocks: { colourPrimary: "#3b5bdb", colourSecondary: "#6f88e6", colourTertiary: "#2f49af" },
    loop_blocks: { colourPrimary: "#10b981", colourSecondary: "#4fcfa3", colourTertiary: "#0c9268" },
    math_blocks: { colourPrimary: "#7c3aed", colourSecondary: "#a06ff2", colourTertiary: "#632eba" },
    text_blocks: { colourPrimary: "#0891b2", colourSecondary: "#3fb0ca", colourTertiary: "#06748e" },
    list_blocks: { colourPrimary: "#f59e0b", colourSecondary: "#f8b84a", colourTertiary: "#c47e08" },
    variable_blocks: { colourPrimary: "#64748b", colourSecondary: "#8b96a7", colourTertiary: "#505b6f" },
    variable_dynamic_blocks: { colourPrimary: "#64748b", colourSecondary: "#8b96a7", colourTertiary: "#505b6f" },
    procedure_blocks: { colourPrimary: "#475569", colourSecondary: "#74808f", colourTertiary: "#394452" },
  },
  categoryStyles: {
    restai_category: { colour: "#1976d2" },
    logic_category: { colour: "#3b5bdb" },
    loop_category: { colour: "#10b981" },
    math_category: { colour: "#7c3aed" },
    text_category: { colour: "#0891b2" },
    list_category: { colour: "#f59e0b" },
    variable_category: { colour: "#64748b" },
    procedure_category: { colour: "#475569" },
  },
  componentStyles: {
    workspaceBackgroundColour: "#f4f7fb",
    toolboxBackgroundColour: "#ffffff",
    toolboxForegroundColour: "#222a45",
    flyoutBackgroundColour: "#f4f7fb",
    flyoutForegroundColour: "#222a45",
    flyoutOpacity: 0.97,
    scrollbarColour: "#c3d0e0",
    scrollbarOpacity: 0.55,
    insertionMarkerColour: "#1976d2",
    insertionMarkerOpacity: 0.4,
    markerColour: "#1976d2",
    cursorColour: "#1976d2",
    selectedGlowColour: "#1976d2",
    selectedGlowOpacity: 0.45,
    replacementGlowColour: "#1976d2",
    replacementGlowOpacity: 0.45,
  },
  fontStyle: {
    family: 'Roboto, "Helvetica Neue", Arial, sans-serif',
    weight: "500",
    size: 12,
  },
});
