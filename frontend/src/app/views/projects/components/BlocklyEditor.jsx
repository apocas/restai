import { useRef, useEffect, useCallback } from "react";
import { Card, Divider, Box, Button, Typography } from "@mui/material";
import { H4 } from "app/components/Typography";
import * as Blockly from "blockly";
import { registerCustomBlocks, setProjectNames } from "./blockly/blocks";
import { toolbox } from "./blockly/toolbox";

export default function BlocklyEditor({ project, projects, onSave }) {
  const editorRef = useRef(null);
  const workspaceRef = useRef(null);

  // Track whether projects have been fetched at least once
  const projectsLoaded = useRef(false);
  if (projects && projects.length > 0) {
    projectsLoaded.current = true;
  }

  // Update the dynamic dropdown whenever projects change
  useEffect(() => {
    const filtered = (projects || []).filter((p) => p.name !== project.name);
    const names = filtered.map((p) => p.name);
    setProjectNames(names, filtered);
  }, [projects, project.name]);

  useEffect(() => {
    if (!editorRef.current) return;
    // Wait for the projects list to load before injecting,
    // so saved dropdown values can be validated against real project names.
    if (!projectsLoaded.current) return;

    // Set names before registering blocks / loading workspace
    const filtered = (projects || []).filter((p) => p.name !== project.name);
    const names = filtered.map((p) => p.name);
    setProjectNames(names, filtered);

    // Register custom block definitions (dropdown reads names dynamically)
    registerCustomBlocks();

    // Inject workspace
    const workspace = Blockly.inject(editorRef.current, {
      toolbox,
      grid: { spacing: 20, length: 3, colour: "#ccc", snap: true },
      zoom: { controls: true, wheel: true, startScale: 1.0 },
      trashcan: true,
    });
    workspaceRef.current = workspace;

    // Load saved state if it exists
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

    return () => {
      workspace.dispose();
      workspaceRef.current = null;
    };
  }, [project.name, projects]);

  const handleSave = useCallback(() => {
    if (!workspaceRef.current) return;
    const state = Blockly.serialization.workspaces.save(workspaceRef.current);
    onSave({ blockly_workspace: state });
  }, [onSave]);

  return (
    <Card elevation={3} sx={{ mt: 2 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", pr: 2 }}>
        <H4 p={2}>Block Editor</H4>
        <Button variant="contained" color="primary" onClick={handleSave}>
          Save Blocks
        </Button>
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
