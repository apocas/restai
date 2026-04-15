import { useState, useEffect } from "react";
import {
  Grid, styled, Box, Card, Divider, Button,
  Switch, FormControlLabel, Typography,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Chip, LinearProgress, Checkbox
} from "@mui/material";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import { toast } from "react-toastify";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";
import api from "app/utils/api";
import { Memory } from "@mui/icons-material";
import { H4 } from "app/components/Typography";

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));

const ContentBox = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" }
}));

const FlexBox = styled(Box)({
  display: "flex",
  alignItems: "center"
});

export default function GpuInfo() {
  const auth = useAuth();
  const { refreshCapabilities } = usePlatformCapabilities();

  const [gpuEnabled, setGpuEnabled] = useState(false);
  const [gpuWorkerDevices, setGpuWorkerDevices] = useState("");
  const [saving, setSaving] = useState(false);
  const [gpuInfo, setGpuInfo] = useState([]);
  const [gpuLoading, setGpuLoading] = useState(false);

  const fetchSettings = () => {
    api.get("/settings", auth.user.token)
      .then((data) => {
        setGpuEnabled(data.gpu_enabled || false);
        setGpuWorkerDevices(data.gpu_worker_devices || "");
      })
      .catch(() => {});
  };

  const fetchGpuInfo = () => {
    setGpuLoading(true);
    api.get("/settings/gpu-info", auth.user.token)
      .then((data) => setGpuInfo(data || []))
      .catch(() => setGpuInfo([]))
      .finally(() => setGpuLoading(false));
  };

  useEffect(() => {
    document.title = "RESTai - GPU";
    fetchSettings();
    fetchGpuInfo();
  }, []);

  const handleSave = () => {
    setSaving(true);
    api.patch("/settings", { gpu_enabled: gpuEnabled, gpu_worker_devices: gpuWorkerDevices }, auth.user.token)
      .then(() => {
        toast.success("GPU settings saved");
        refreshCapabilities();
      })
      .catch(() => {})
      .finally(() => setSaving(false));
  };

  const selectedDevices = (gpuWorkerDevices || "").split(",").filter(Boolean);

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "GPU", path: "/gpu" }]} />
      </Box>

      <ContentBox>
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Card elevation={3}>
              <FlexBox>
                <Memory sx={{ ml: 2 }} />
                <H4 sx={{ p: 2 }}>GPU</H4>
              </FlexBox>
              <Divider />
              <Box sx={{ p: 3 }}>
                <Grid container spacing={3}>
                  <Grid item xs={12}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={gpuEnabled}
                          onChange={(e) => setGpuEnabled(e.target.checked)}
                          disabled={!gpuLoading && gpuInfo.length === 0}
                        />
                      }
                      label="GPU Enabled"
                    />
                    <Typography variant="caption" color="text.secondary" display="block">
                      Changes to GPU settings require application restart to take effect.
                    </Typography>
                  </Grid>

                  <Grid item xs={12}>
                    {gpuLoading && <LinearProgress sx={{ mb: 2 }} />}
                    {!gpuLoading && gpuInfo.length === 0 && (
                      <Typography variant="body2" color="text.secondary">
                        No GPUs detected.
                      </Typography>
                    )}
                    {!gpuLoading && gpuInfo.length > 0 && (
                      <>
                        <Typography variant="subtitle2" sx={{ mb: 1 }}>
                          Detected GPUs
                          {gpuInfo[0].driver_version && (
                            <Chip label={`Driver ${gpuInfo[0].driver_version}`} size="small" sx={{ ml: 1 }} />
                          )}
                          {gpuInfo[0].cuda_version && (
                            <Chip label={`CUDA ${gpuInfo[0].cuda_version}`} size="small" sx={{ ml: 1 }} />
                          )}
                        </Typography>
                        <TableContainer>
                          <Table size="small">
                            <TableHead>
                              <TableRow>
                                <TableCell sx={{ width: 60 }}>#</TableCell>
                                <TableCell>Name</TableCell>
                                <TableCell>Memory (Total)</TableCell>
                                <TableCell>Memory (Used)</TableCell>
                                <TableCell>Memory (Free)</TableCell>
                                <TableCell>Temp</TableCell>
                                <TableCell>Utilization</TableCell>
                                <TableCell>Power</TableCell>
                                <TableCell>PCI Bus</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {gpuInfo.map((gpu) => {
                                const gpuIdx = String(gpu.index);
                                const isSelected = selectedDevices.length === 0 || selectedDevices.includes(gpuIdx);
                                const handleToggleDevice = () => {
                                  let next;
                                  if (selectedDevices.length === 0) {
                                    next = gpuInfo.map((g) => String(g.index)).filter((i) => i !== gpuIdx);
                                  } else if (isSelected) {
                                    next = selectedDevices.filter((i) => i !== gpuIdx);
                                  } else {
                                    next = [...selectedDevices, gpuIdx].sort();
                                  }
                                  const allIndices = gpuInfo.map((g) => String(g.index)).sort().join(",");
                                  const nextStr = next.sort().join(",");
                                  setGpuWorkerDevices(nextStr === allIndices ? "" : nextStr);
                                };
                                return (
                                  <TableRow key={gpu.index}>
                                    <TableCell sx={{ whiteSpace: "nowrap" }}>
                                      <Checkbox
                                        checked={isSelected}
                                        onChange={handleToggleDevice}
                                        size="small"
                                        sx={{ p: 0, mr: 0.5 }}
                                      />
                                      {gpu.index}
                                    </TableCell>
                                    <TableCell><strong>{gpu.name}</strong></TableCell>
                                    <TableCell>{gpu.memory_total}</TableCell>
                                    <TableCell>{gpu.memory_used}</TableCell>
                                    <TableCell>{gpu.memory_free}</TableCell>
                                    <TableCell>{gpu.temperature}</TableCell>
                                    <TableCell>{gpu.utilization}</TableCell>
                                    <TableCell>{gpu.power_draw} / {gpu.power_limit}</TableCell>
                                    <TableCell><Typography variant="caption">{gpu.pci_bus_id}</Typography></TableCell>
                                  </TableRow>
                                );
                              })}
                            </TableBody>
                          </Table>
                        </TableContainer>
                        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
                          {gpuWorkerDevices
                            ? `Workers will use GPU(s): ${gpuWorkerDevices}`
                            : "Workers will use all available GPUs"}
                        </Typography>
                      </>
                    )}
                  </Grid>
                </Grid>
              </Box>
            </Card>
          </Grid>

          <Grid item xs={12}>
            <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
              <Button
                variant="contained"
                color="primary"
                onClick={handleSave}
                disabled={saving}
              >
                {saving ? "Saving..." : "Save GPU Settings"}
              </Button>
            </Box>
          </Grid>
        </Grid>
      </ContentBox>
    </Container>
  );
}
