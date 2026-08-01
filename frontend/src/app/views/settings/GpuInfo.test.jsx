import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import GpuInfo from "./GpuInfo";
import api from "app/utils/api";
import { toast } from "react-toastify";

jest.mock("app/utils/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  delete: jest.fn(),
}));
jest.mock("react-toastify", () => ({
  toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() },
}));
jest.mock("app/hooks/useAuth", () => jest.fn());
import useAuth from "app/hooks/useAuth";
jest.mock("app/contexts/PlatformContext", () => ({
  usePlatformCapabilities: jest.fn(),
}));
import { usePlatformCapabilities } from "app/contexts/PlatformContext";

const GPUS = [
  {
    index: 0,
    name: "NVIDIA A100",
    pci_bus_id: "0000:00:04.0",
    memory_total: "40960 MiB",
    memory_used: "1024 MiB",
    utilization: "55 %",
    temperature: "63",
    power_draw: "250",
    power_limit: "400",
    driver_version: "550.54",
    cuda_version: "12.4",
  },
  {
    index: 1,
    name: "NVIDIA L4",
    memory_total: "24576 MiB",
    memory_used: "512 MiB",
    utilization: "10 %",
    temperature: "41",
    power_draw: "40",
    power_limit: "72",
    driver_version: "550.54",
    cuda_version: "12.4",
  },
];

let settingsResp;
let gpuInfoResp;
let refreshCapabilities;

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { token: "tok", username: "admin", is_admin: true } });
  refreshCapabilities = jest.fn();
  usePlatformCapabilities.mockReturnValue({ refreshCapabilities });
  settingsResp = () => Promise.resolve({ gpu_enabled: true, gpu_worker_devices: "" });
  gpuInfoResp = () => Promise.resolve(GPUS);
  api.get.mockImplementation((path) => {
    if (path === "/settings") return settingsResp();
    if (path === "/settings/gpu-info") return gpuInfoResp();
    return Promise.resolve({});
  });
  api.patch.mockResolvedValue({});
});

describe("GpuInfo render states", () => {
  it("shows the scanning state while gpu-info is loading", () => {
    gpuInfoResp = () => new Promise(() => {});
    render(<GpuInfo />);
    expect(screen.getByText("scanning silicon…")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("shows the no-GPU empty state and disables the toggle when none are detected", async () => {
    gpuInfoResp = () => Promise.resolve([]);
    render(<GpuInfo />);

    expect(await screen.findByText("No GPUs detected on this host.")).toBeInTheDocument();
    // The GPU switch cannot be enabled without hardware.
    expect(screen.getByRole("checkbox")).toBeDisabled();
  });

  it("falls back to the no-GPU state when the gpu-info endpoint errors", async () => {
    gpuInfoResp = () => Promise.reject({ status: 500 });
    render(<GpuInfo />);
    expect(await screen.findByText("No GPUs detected on this host.")).toBeInTheDocument();
  });

  it("renders a card per GPU with driver/CUDA pills and the all-GPUs pool note", async () => {
    render(<GpuInfo />);

    expect(await screen.findByText("NVIDIA A100")).toBeInTheDocument();
    expect(screen.getByText("NVIDIA L4")).toBeInTheDocument();
    // Header pills from the first device.
    expect(screen.getByText("550.54")).toBeInTheDocument();
    expect(screen.getByText("12.4")).toBeInTheDocument();
    // Empty gpu_worker_devices → every GPU is in the pool.
    expect(screen.getByText("Worker pool → all available GPUs")).toBeInTheDocument();
    expect(screen.getByText("GPU mode active")).toBeInTheDocument();
  });

  it("shows CPU-only when gpu_enabled is off in settings", async () => {
    settingsResp = () => Promise.resolve({ gpu_enabled: false, gpu_worker_devices: "" });
    render(<GpuInfo />);
    await screen.findByText("NVIDIA A100");
    expect(screen.getByText("CPU only")).toBeInTheDocument();
  });
});

describe("GpuInfo worker pool selection", () => {
  it("excluding one GPU from the all-selected pool keeps only the others", async () => {
    const user = userEvent.setup();
    render(<GpuInfo />);
    await screen.findByText("NVIDIA A100");

    // Checkboxes: [0] = enable switch, then one per GPU card.
    const boxes = screen.getAllByRole("checkbox");
    expect(boxes).toHaveLength(3);
    await user.click(boxes[1]); // deselect GPU 0

    expect(screen.getByText("Worker pool → GPU(s) 1")).toBeInTheDocument();
  });

  it("re-selecting every GPU collapses back to the all-GPUs default", async () => {
    settingsResp = () => Promise.resolve({ gpu_enabled: true, gpu_worker_devices: "1" });
    const user = userEvent.setup();
    render(<GpuInfo />);
    await screen.findByText("NVIDIA A100");

    expect(screen.getByText("Worker pool → GPU(s) 1")).toBeInTheDocument();
    const boxes = screen.getAllByRole("checkbox");
    await user.click(boxes[1]); // select GPU 0 again → full set → ""
    expect(screen.getByText("Worker pool → all available GPUs")).toBeInTheDocument();
  });
});

describe("GpuInfo save + refresh", () => {
  it("PATCHes /settings with the toggle + device selection and refreshes capabilities", async () => {
    const user = userEvent.setup();
    render(<GpuInfo />);
    await screen.findByText("NVIDIA A100");

    const boxes = screen.getAllByRole("checkbox");
    await user.click(boxes[2]); // exclude GPU 1 → "0"
    await user.click(screen.getByRole("button", { name: /Save GPU settings/ }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        "/settings",
        { gpu_enabled: true, gpu_worker_devices: "0" },
        "tok"
      )
    );
    expect(toast.success).toHaveBeenCalledWith("GPU settings saved");
    expect(refreshCapabilities).toHaveBeenCalled();
  });

  it("the refresh action re-hits the gpu-info endpoint", async () => {
    const user = userEvent.setup();
    render(<GpuInfo />);
    await screen.findByText("NVIDIA A100");

    expect(api.get.mock.calls.filter(([p]) => p === "/settings/gpu-info")).toHaveLength(1);
    const card = screen.getByText("GPU acceleration").closest("div");
    const refreshBtn = within(card.parentElement.parentElement).getAllByRole("button")[0];
    await user.click(refreshBtn);

    await waitFor(() =>
      expect(api.get.mock.calls.filter(([p]) => p === "/settings/gpu-info")).toHaveLength(2)
    );
  });
});
