"""Baidu ERNIE-Image-Turbo — DMD + RL distilled variant of ERNIE-Image."""
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


_DEFAULT_REPO = "baidu/ERNIE-Image-Turbo"


def worker(prompt, sharedmem):
    import base64
    import io
    import torch
    from diffusers import ErnieImagePipeline

    repo = sharedmem.get("repo") or _DEFAULT_REPO
    torch_dtype = torch.bfloat16

    pipe = ErnieImagePipeline.from_pretrained(repo, torch_dtype=torch_dtype)
    if (sharedmem.get("offload") or "model").lower() == "sequential":
        pipe.enable_sequential_cpu_offload()
    else:
        pipe.enable_model_cpu_offload()

    image = pipe(
        prompt=prompt,
        height=int(sharedmem.get("height") or 1024),
        width=int(sharedmem.get("width") or 1024),
        num_inference_steps=int(sharedmem.get("num_inference_steps") or 8),
        guidance_scale=float(sharedmem.get("guidance_scale") or 1.0),
        use_pe=bool(sharedmem.get("use_pe", True)),
        generator=torch.Generator(device="cuda:0").manual_seed(
            int(sharedmem.get("seed") or 0)
        ),
    ).images[0]

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=92)
    sharedmem["image"] = base64.b64encode(buf.getvalue()).decode("utf-8")

    flush()
