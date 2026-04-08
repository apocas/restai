import { useEffect, useRef, useState } from "react";
import {
  Alert, Box, Card, Chip, CircularProgress, MenuItem, TextField, Typography,
} from "@mui/material";
import { Network } from "vis-network/standalone/esm/vis-network";
import "vis-network/styles/vis-network.css";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";

const TYPE_COLORS = {
  PERSON: { background: "#42a5f5", border: "#1976d2" },
  ORG: { background: "#66bb6a", border: "#2e7d32" },
  LOC: { background: "#ffa726", border: "#e65100" },
  MISC: { background: "#bdbdbd", border: "#616161" },
  DATE: { background: "#ab47bc", border: "#6a1b9a" },
};

export default function GraphPanel({ project }) {
  const auth = useAuth();
  const containerRef = useRef(null);
  const networkRef = useRef(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState("");
  const [limit, setLimit] = useState(100);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (typeFilter) params.set("type", typeFilter);
    params.set("limit", limit);
    api.get(`/projects/${project.id}/kg/graph?${params}`, auth.user.token)
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [project.id, typeFilter, limit]);

  useEffect(() => {
    if (!data || !containerRef.current) return;
    if (data.nodes.length === 0) return;

    const nodes = data.nodes.map((n) => {
      const colors = TYPE_COLORS[n.type] || TYPE_COLORS.MISC;
      return {
        id: n.id,
        label: n.label,
        color: colors,
        font: { color: "#212121", size: 13, strokeWidth: 3, strokeColor: "#ffffff" },
        size: Math.max(15, Math.min(40, 10 + Math.log2(n.mention_count + 1) * 5)),
        shape: "dot",
        title: `${n.label}\n${n.type} • ${n.mention_count} mentions`,
      };
    });
    const edges = data.edges.map((e) => ({
      from: e.from,
      to: e.to,
      width: Math.max(1, Math.min(8, e.weight)),
      color: { color: "#cfd8dc", highlight: "#42a5f5" },
      smooth: { type: "continuous" },
    }));

    const network = new Network(
      containerRef.current,
      { nodes, edges },
      {
        physics: {
          forceAtlas2Based: { gravitationalConstant: -50, springLength: 100, springConstant: 0.08 },
          solver: "forceAtlas2Based",
          stabilization: { iterations: 200 },
        },
        interaction: { hover: true, tooltipDelay: 200 },
        nodes: { borderWidth: 2 },
      }
    );
    networkRef.current = network;

    network.on("click", (params) => {
      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0];
        api.get(`/projects/${project.id}/kg/entities/${nodeId}`, auth.user.token)
          .then(setSelected)
          .catch(() => {});
      } else {
        setSelected(null);
      }
    });

    return () => { network.destroy(); };
  }, [data]);

  return (
    <Box>
      <Box sx={{ display: "flex", gap: 2, mb: 2, alignItems: "center", flexWrap: "wrap" }}>
        <TextField
          size="small" select label="Type filter" value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          sx={{ minWidth: 150 }}
        >
          <MenuItem value="">All types</MenuItem>
          <MenuItem value="PERSON">Person</MenuItem>
          <MenuItem value="ORG">Organization</MenuItem>
          <MenuItem value="LOC">Location</MenuItem>
          <MenuItem value="MISC">Other</MenuItem>
        </TextField>
        <TextField
          size="small" select label="Max nodes" value={limit}
          onChange={(e) => setLimit(parseInt(e.target.value))}
          sx={{ minWidth: 120 }}
        >
          {[50, 100, 200, 500].map((n) => (
            <MenuItem key={n} value={n}>{n}</MenuItem>
          ))}
        </TextField>
        <Box sx={{ display: "flex", gap: 1, alignItems: "center", ml: "auto" }}>
          {Object.entries(TYPE_COLORS).slice(0, 4).map(([type, colors]) => (
            <Chip key={type} label={type} size="small" sx={{
              bgcolor: colors.background + "20",
              color: colors.border,
              fontWeight: 600,
            }} />
          ))}
        </Box>
      </Box>

      {loading ? (
        <Box sx={{ textAlign: "center", py: 6 }}><CircularProgress /></Box>
      ) : !data || data.nodes.length === 0 ? (
        <Alert severity="info">No graph data yet. Ingest documents with knowledge graph enabled to populate.</Alert>
      ) : (
        <Box sx={{ display: "flex", gap: 2 }}>
          <Card variant="outlined" sx={{ flex: 1, height: 600, position: "relative" }}>
            <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
          </Card>
          {selected && (
            <Card variant="outlined" sx={{ width: 300, p: 2, height: 600, overflow: "auto" }}>
              <Typography variant="subtitle1" fontWeight={600}>{selected.name}</Typography>
              <Chip label={selected.entity_type} size="small" sx={{
                bgcolor: (TYPE_COLORS[selected.entity_type]?.background || "#999") + "20",
                color: TYPE_COLORS[selected.entity_type]?.border || "#999",
                mt: 1, mb: 2,
              }} />
              <Typography variant="caption" color="text.secondary" display="block">
                {selected.mention_count} mentions
              </Typography>
              <Typography variant="subtitle2" sx={{ mt: 2, mb: 1 }}>Sources</Typography>
              {(selected.mentions || []).slice(0, 20).map((m, i) => (
                <Typography key={i} variant="caption" display="block" sx={{ wordBreak: "break-all", mb: 0.5 }}>
                  • {m.source} ({m.mention_count})
                </Typography>
              ))}
              {selected.related?.length > 0 && (
                <>
                  <Typography variant="subtitle2" sx={{ mt: 2, mb: 1 }}>Related Entities</Typography>
                  {selected.related.slice(0, 10).map((r) => (
                    <Chip key={r.id} label={r.name} size="small" sx={{ mr: 0.5, mb: 0.5 }} />
                  ))}
                </>
              )}
            </Card>
          )}
        </Box>
      )}
    </Box>
  );
}
