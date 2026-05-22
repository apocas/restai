import { useRef, useEffect, useCallback } from "react";
import { Card, Divider, Box, Button, Typography } from "@mui/material";
import { FileDownload, FileUpload } from "@mui/icons-material";
import { toast } from "react-toastify";
import { H4 } from "app/components/Typography";
import * as Blockly from "blockly";
import { registerCustomBlocks, setProjectNames } from "./blockly/blocks";
import { toolbox } from "./blockly/toolbox";

export default function BlocklyEditor({ project, projects, onSave, onReady }) {
  const editorRef = useRef(null);
  const workspaceRef = useRef(null);
  // Ref-held so the input's value can be reset between picks — otherwise
  // selecting the same filename twice in a row wouldn't re-fire onChange.
  const fileInputRef = useRef(null);

  const projectsLoaded = useRef(false);
  if (projects && projects.length > 0) {
    projectsLoaded.current = true;
  }

  useEffect(() => {
    const filtered = (projects || []).filter((p) => p.name !== project.name);
    const names = filtered.map((p) => p.name);
    setProjectNames(names, filtered);
  }, [projects, project.name]);

  useEffect(() => {
    if (!editorRef.current) return;
    // Wait for projects so saved dropdown values can validate against names.
    if (!projectsLoaded.current) return;

    // Names MUST be set before registering blocks / loading the workspace.
    const filtered = (projects || []).filter((p) => p.name !== project.name);
    const names = filtered.map((p) => p.name);
    setProjectNames(names, filtered);

    registerCustomBlocks();

    const workspace = Blockly.inject(editorRef.current, {
      toolbox,
      grid: { spacing: 20, length: 3, colour: "#ccc", snap: true },
      zoom: { controls: true, wheel: true, startScale: 1.0 },
      trashcan: true,
    });
    workspaceRef.current = workspace;

    if (project.options?.blockly_workspace) {
      try {
        Blockly.serialization.workspaces.load(
          project.options.blockly_workspace,
          workspace
        );
      } catch (e) {
        console.error("Failed to load Blockly workspace:", e);
      }
    }

    if (onReady) {
      onReady((newState) => {
        if (!workspaceRef.current) return;
        try {
          workspaceRef.current.clear();
          Blockly.serialization.workspaces.load(newState, workspaceRef.current);
        } catch (e) {
          console.error("Failed to load generated workspace:", e);
        }
      });
    }

    return () => {
      workspace.dispose();
      workspaceRef.current = null;
      if (onReady) onReady(null);
    };
  }, [project.name, projects]);

  const handleSave = useCallback(() => {
    if (!workspaceRef.current) return;
    const state = Blockly.serialization.workspaces.save(workspaceRef.current);
    onSave({ blockly_workspace: state });
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
      // Defer revoke — Safari/Firefox need the URL alive briefly.
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("Workspace exported.");
    } catch (e) {
      console.error("Export failed:", e);
      toast.error("Export failed: " + (e?.message || e));
    }
  }, [project.name]);

  const handleImportFile = useCallback((e) => {
    const file = e.target.files && e.target.files[0];
    // Reset so picking the same filename twice still re-fires onChange.
    e.target.value = "";
    if (!file || !workspaceRef.current) return;
    if (!window.confirm(
      "Replace the current workspace with the contents of this file? " +
      "Any unsaved blocks will be lost."
    )) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const text = String(reader.result || "");
        const state = JSON.parse(text);
        if (!state || typeof state !== "object") {
          throw new Error("File doesn't contain a Blockly workspace JSON object.");
        }
        workspaceRef.current.clear();
        Blockly.serialization.workspaces.load(state, workspaceRef.current);
        toast.success("Workspace loaded from " + file.name);
      } catch (err) {
        console.error("Import failed:", err);
        toast.error("Import failed: " + (err?.message || err));
      }
    };
    reader.onerror = () => {
      toast.error("Couldn't read the selected file.");
    };
    reader.readAsText(file);
  }, []);

  return (
    <Card elevation={3} sx={{ mt: 2 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", pr: 2, gap: 1, flexWrap: "wrap" }}>
        <H4 p={2}>Block Editor</H4>
        <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
          <Button
            variant="outlined"
            color="primary"
            startIcon={<FileUpload />}
            onClick={() => fileInputRef.current && fileInputRef.current.click()}
          >
            Import from file
          </Button>
          <Button
            variant="outlined"
            color="primary"
            startIcon={<FileDownload />}
            onClick={handleExport}
          >
            Export to file
          </Button>
          <Button variant="contained" color="primary" onClick={handleSave}>
            Save Blocks
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".json,application/json"
            style={{ display: "none" }}
            onChange={handleImportFile}
          />
        </Box>
      </Box>
      <Divider />
      <Typography variant="caption" color="textSecondary" sx={{ px: 2, pt: 1, display: "block" }}>
        Use "Get Input" to read the question and "Set Output" to define the answer.
        "Call Project" lets you invoke other RESTai projects.
      </Typography>
      <Box
        ref={editorRef}
        sx={{ width: "100%", height: "600px" }}
      />
    </Card>
  );
}
