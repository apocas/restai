"""Z-Image-Turbo (Tongyi-MAI) image generator — bf16 from the official repo.

A 6B-parameter DiT distilled for very fast inference (8 steps, no
classifier-free guidance). Loaded straight from
``Tongyi-MAI/Z-Image-Turbo`` in bf16; we lean on
`enable_model_cpu_offload` to swap text encoder / transformer / VAE in
and out of GPU one at a time so the active footprint stays at the
single largest component instead of their sum. For very small cards
set ``offload=sequential`` in sharedmem to swap at the submodule level
(slower but much lower peak).

Picks up automatically: `restai/image/registry.py:seed_local_generators`
walks `image/workers/*.py` on every boot and creates a DB row for any
new module. The admin can flip `enabled`/`privacy` in the Image
Generators panel without code changes.

The worker runs in `.venv-zimage` so it can use a bleeding-edge
`diffusers` (Z-Image pipeline classes only landed in late-2025
releases, well past the 0.31 pinned in the shared `.venv-sd`).
"""
import os


def get_python_executable():
    current_file_path = os.path.abspath(__file__)
    project_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file_path))))
    return os.path.join(project_path, ".venvs/.venv-zimage/bin/python")


def flush():
    import gc
    import torch
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.reset_max_memory_allocated()
        torch.cuda.reset_peak_memory_stats()


_DEFAULT_REPO = "Tongyi-MAI/Z-Image-Turbo"


def worker(prompt, sharedmem):
    import base64
    import io
    import torch
    from diffusers import ZImagePipeline

    repo = sharedmem.get("repo") or _DEFAULT_REPO
    torch_dtype = torch.bfloat16

    pipe = ZImagePipeline.from_pretrained(repo, torch_dtype=torch_dtype)
    # Cycle modules in/out of VRAM so peak stays at the single largest
    # component, not the sum. Sequential offload swaps at the submodule
    # level (much lower peak, slower); model offload is the default.
    if (sharedmem.get("offload") or "model").lower() == "sequential":
        pipe.enable_sequential_cpu_offload()
    else:
        pipe.enable_model_cpu_offload()

    # Z-Image-Turbo is distilled — short step count, low/no CFG.
    image = pipe(
        prompt=prompt,
        num_inference_steps=int(sharedmem.get("num_inference_steps") or 8),
        guidance_scale=float(sharedmem.get("guidance_scale") or 1.0),
        generator=torch.Generator(device="cuda:0").manual_seed(
            int(sharedmem.get("seed") or 0)
        ),
    ).images[0]

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=92)
    sharedmem["image"] = base64.b64encode(buf.getvalue()).decode("utf-8")

    flush()
