import os


def get_python_executable():
    current_file_path = os.path.abspath(__file__)
    project_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file_path))))
    
    return os.path.join(project_path, ".venvs/.venv-sd/bin/python")

def worker(prompt, sharedmem):
    import base64
    import io
    from diffusers import StableDiffusion3Pipeline
    import torch
    import restai.config as _cfg

    # `_cfg.RESTAI_DEFAULT_DEVICE` is derived from `gpu_worker_devices`
    # in /admin/gpu (first index in the worker pool, "cuda:N", or
    # "cuda:0" when the pool is empty/all-available).
    base = StableDiffusion3Pipeline.from_pretrained("stabilityai/stable-diffusion-3-medium-diffusers", torch_dtype=torch.float16)
    base.to(_cfg.RESTAI_DEFAULT_DEVICE)

    image = base(
        prompt=prompt,
        negative_prompt="",
        num_inference_steps=28,
        guidance_scale=7.0,
    ).images[0]
    
    image_data = io.BytesIO()
    image.save(image_data, format="JPEG")
    image_base64 = base64.b64encode(image_data.getvalue()).decode('utf-8')

    sharedmem["image"] = image_base64
