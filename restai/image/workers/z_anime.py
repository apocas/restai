"""SeeSee21 Z-Anime — anime-style fine-tune of Z-Image Base (6B DiT).

Full fine-tune of Alibaba's Z-Image Base (NOT a Turbo derivative or
LoRA merge), shipped as a diffusers checkpoint under the ``diffusers/``
subfolder of ``SeeSee21/Z-Anime``. Uses the standard `ZImagePipeline`
class.

Defaults here target the base checkpoint (28-50 steps, CFG 3-5).
The repo also publishes 8-step and 4-step distill variants — the
admin can point at them via the Image Generators panel:
- 8-step distill: `sharedmem["num_inference_steps"] = 8`,
  `sharedmem["guidance_scale"] = 1.0`
- 4-step distill: `sharedmem["num_inference_steps"] = 4`,
  `sharedmem["guidance_scale"] = 1.0`

Picks up automatically: `restai/image/registry.py:seed_local_generators`
walks `image/workers/*.py` on every boot and creates a DB row.

Shares `.venv-zimage` with `zimage_turbo` and `ernie_image` — same
bleeding-edge `diffusers` requirement.
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


_DEFAULT_REPO = "SeeSee21/Z-Anime"
_DEFAULT_SUBFOLDER = "diffusers"  # repo lays out HF + ComfyUI + diffusers variants


def worker(prompt, sharedmem):
    import base64
    import io
    import torch
    from diffusers import ZImagePipeline

    repo = sharedmem.get("repo") or _DEFAULT_REPO
    subfolder = sharedmem.get("subfolder") or _DEFAULT_SUBFOLDER
    torch_dtype = torch.bfloat16

    pipe = ZImagePipeline.from_pretrained(
        repo,
        subfolder=subfolder,
        torch_dtype=torch_dtype,
    )
    if (sharedmem.get("offload") or "model").lower() == "sequential":
        pipe.enable_sequential_cpu_offload()
    else:
        pipe.enable_model_cpu_offload()

    image = pipe(
        prompt=prompt,
        num_inference_steps=int(sharedmem.get("num_inference_steps") or 40),
        guidance_scale=float(sharedmem.get("guidance_scale") or 4.0),
        generator=torch.Generator(device="cuda:0").manual_seed(
            int(sharedmem.get("seed") or 0)
        ),
    ).images[0]

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=92)
    sharedmem["image"] = base64.b64encode(buf.getvalue()).decode("utf-8")

    flush()
