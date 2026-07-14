import { useRef, useEffect, useCallback, useState } from "react";
import { Box, Button, Tooltip } from "@mui/material";
import { FileDownload, FileUpload, Save, ViewInAr } from "@mui/icons-material";
import { toast } from "react-toastify";
import { useTranslation } from "react-i18next";
import * as Blockly from "blockly";
import { registerCustomBlocks, setProjectNames } from "./blockly/blocks";
import { getToolbox } from "./blockly/toolbox";
import { restaiBlocklyTheme } from "./blockly/theme";
import { PlaygroundTile, HeaderBar, Eyebrow, PulseDot, GhostAction, HAIRLINE } from "./generatorKit";
import { FONT_MONO } from "app/components/page/pageStyles";

const ACCENT = "#1976d2";
const SAVED = "#10b981";
const UNSAVED = "#f59e0b";

export default function BlocklyEditor({ project, projects, onSave, onReady }) {
  const { t } = useTranslation();
  const editorRef = useRef(null);
  const workspaceRef = useRef(null);
  const fileInputRef = useRef(null);
  // Set while a workspace is loaded programmatically, so those change events
  // don't flip the dirty flag.
  const loadingRef = useRef(false);

  const [dirty, setDirty] = useState(false);
  const [counts, setCounts] = useState({ blocks: 0, vars: 0 });

  const projectsLoaded = useRef(false);
  if (projects && projects.length > 0) {
    projectsLoaded.current = true;
  }

  const refreshStats = useCallback(() => {
    const ws = workspaceRef.current;
    if (!ws) return;
    setCounts({
      blocks: ws.getAllBlocks(false).length,
      vars: ws.getAllVariables().length,
    });
  }, []);

  useEffect(() => {
    const filtered = (projects || []).filter((p) => p.name !== project.name);
    setProjectNames(filtered.map((p) => p.name), filtered);
  }, [projects, project.name]);

  useEffect(() => {
    if (!editorRef.current) return;
    if (!projectsLoaded.current) return;

    const filtered = (projects || []).filter((p) => p.name !== project.name);
    setProjectNames(filtered.map((p) => p.name), filtered);

    registerCustomBlocks();

    const workspace = Blockly.inject(editorRef.current, {
      toolbox: getToolbox(t),
      theme: restaiBlocklyTheme,
      renderer: "thrasos",
      grid: { spacing: 24, length: 3, colour: "rgba(25,118,210,0.14)", snap: true },
      zoom: { controls: true, wheel: true, startScale: 1.0 },
      move: { scrollbars: true, drag: true, wheel: true },
      trashcan: true,
    });
    workspaceRef.current = workspace;

    loadingRef.current = true;
    if (project.options?.blockly_workspace) {
      try {
        Blockly.serialization.workspaces.load(project.options.blockly_workspace, workspace);
      } catch (e) {
        console.error("Failed to load Blockly workspace:", e);
      }
    }
    loadingRef.current = false;
    setDirty(false);
    refreshStats();

    // Mark unsaved on any real model change (create/delete/move/change); UI-only
    // events (select, scroll, click) and programmatic loads are ignored.
    workspace.addChangeListener((e) => {
      if (loadingRef.current || e.isUiEvent) return;
      setDirty(true);
      refreshStats();
    });

    if (onReady) {
      onReady((newState) => {
        if (!workspaceRef.current) return;
        loadingRef.current = true;
        try {
          workspaceRef.current.clear();
          Blockly.serialization.workspaces.load(newState, workspaceRef.current);
        } catch (e) {
          console.error("Failed to load generated workspace:", e);
        }
        loadingRef.current = false;
        setDirty(true); // generated but not yet saved
        refreshStats();
      });
    }

    return () => {
      workspace.dispose();
      workspaceRef.current = null;
      if (onReady) onReady(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.name, projects]);

  // Retranslate the toolbox on UI-language change without disposing the
  // workspace (so unsaved blocks survive a language switch).
  useEffect(() => {
    if (workspaceRef.current) {
      try { workspaceRef.current.updateToolbox(getToolbox(t)); } catch (e) { /* pre-inject */ }
    }
  }, [t]);

  const handleSave = useCallback(() => {
    if (!workspaceRef.current) return;
    const state = Blockly.serialization.workspaces.save(workspaceRef.current);
    onSave({ blockly_workspace: state });
    setDirty(false);
  }, [onSave]);

  const handleExport = useCallback(() => {
    if (!workspaceRef.current) return;
    try {
      const state = Blockly.serialization.workspaces.save(workspaceRef.current);
      const blob = new Blob([JSON.stringify(state, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
      const safe = (project.name || "workspace").replace(/[^A-Za-z0-9._-]/g, "_");
      const a = document.createElement("a");
      a.href = url;
      a.download = `${safe}-blocks-${stamp}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success(t("projects.edit.knowledge.ide.exported"));
    } catch (e) {
      console.error("Export failed:", e);
      toast.error(t("projects.edit.knowledge.ide.exportFailed") + " " + (e?.message || e));
    }
  }, [project.name, t]);

  const handleImportFile = useCallback((e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!file || !workspaceRef.current) return;
    if (!window.confirm(t("projects.edit.knowledge.ide.importConfirm"))) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const state = JSON.parse(String(reader.result || ""));
        if (!state || typeof state !== "object") {
          throw new Error(t("projects.edit.knowledge.ide.importInvalid"));
        }
        loadingRef.current = true;
        workspaceRef.current.clear();
        Blockly.serialization.workspaces.load(state, workspaceRef.current);
        loadingRef.current = false;
        setDirty(true);
        refreshStats();
        toast.success(t("projects.edit.knowledge.ide.imported") + " " + file.name);
      } catch (err) {
        loadingRef.current = false;
        console.error("Import failed:", err);
        toast.error(t("projects.edit.knowledge.ide.importFailed") + " " + (err?.message || err));
      }
    };
    reader.onerror = () => toast.error(t("projects.edit.knowledge.ide.importReadError"));
    reader.readAsText(file);
  }, [t, refreshStats]);

  return (
    <PlaygroundTile accent={ACCENT} sx={{ mt: 2, flex: "0 0 auto" }}>
      <HeaderBar>
        {/* Left: workspace identity + live block/variable tally */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, minWidth: 0 }}>
          <Box
            sx={{
              width: 32, height: 32, flexShrink: 0, borderRadius: 2,
              display: "inline-flex", alignItems: "center", justifyContent: "center",
              background: "rgba(25,118,210,0.10)", color: ACCENT,
              "& svg": { fontSize: 18 },
            }}
          >
            <ViewInAr />
          </Box>
          <Box sx={{ minWidth: 0 }}>
            <Eyebrow accent={ACCENT}>{t("projects.edit.knowledge.ide.workspace")}</Eyebrow>
            <Box sx={{ fontFamily: FONT_MONO, fontSize: "0.72rem", color: "rgba(15,23,42,0.5)", mt: 0.25 }}>
              {counts.blocks} {t("projects.edit.knowledge.ide.blocks")} · {counts.vars} {t("projects.edit.knowledge.ide.variables")}
            </Box>
          </Box>
        </Box>

        {/* Right: save state + actions */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mr: 0.5 }}>
            <PulseDot accent={dirty ? UNSAVED : SAVED} active={!dirty} />
            <Box
              sx={{
                fontFamily: FONT_MONO, fontSize: "0.66rem", letterSpacing: "0.1em",
                textTransform: "uppercase", fontWeight: 700,
                color: dirty ? UNSAVED : SAVED,
              }}
            >
              {dirty ? t("projects.edit.knowledge.ide.unsaved") : t("projects.edit.knowledge.ide.saved")}
            </Box>
          </Box>
          <Tooltip title={t("projects.edit.knowledge.ide.importFile")}>
            <GhostAction accent={ACCENT} onClick={() => fileInputRef.current && fileInputRef.current.click()}>
              <FileUpload fontSize="small" />
            </GhostAction>
          </Tooltip>
          <Tooltip title={t("projects.edit.knowledge.ide.exportFile")}>
            <GhostAction accent={ACCENT} onClick={handleExport}>
              <FileDownload fontSize="small" />
            </GhostAction>
          </Tooltip>
          <Button
            variant="contained"
            startIcon={<Save />}
            onClick={handleSave}
            disableElevation
            sx={{
              borderRadius: 2, background: ACCENT, fontWeight: 600,
              "&:hover": { background: "#155fa8", boxShadow: `0 8px 18px ${ACCENT}44` },
            }}
          >
            {t("projects.edit.knowledge.ide.saveBlocks")}
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".json,application/json"
            style={{ display: "none" }}
            onChange={handleImportFile}
          />
        </Box>
      </HeaderBar>

      <Box
        ref={editorRef}
        sx={{ width: "100%", height: "clamp(520px, calc(100vh - 300px), 900px)" }}
      />

      <Box
        sx={{
          borderTop: `1px solid ${HAIRLINE}`,
          px: 2, py: 1.25,
          fontFamily: FONT_MONO, fontSize: "0.68rem", letterSpacing: "0.02em",
          color: "rgba(15,23,42,0.5)",
        }}
      >
        {t("projects.edit.knowledge.ide.help")}
      </Box>
    </PlaygroundTile>
  );
}
