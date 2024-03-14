import base64
import io
import os
import torch
from diffusers import StableDiffusionXLPipeline, UNet2DConditionModel, EulerDiscreteScheduler
from huggingface_hub import hf_hub_download
from safetensors.torch import load_file

def worker(prompt, sharedmem):
    base = "stabilityai/stable-diffusion-xl-base-1.0"
    repo = "ByteDance/SDXL-Lightning"
    ckpt = "sdxl_lightning_4step_unet.safetensors"
    default_device = os.environ.get("RESTAI_DEFAULT_DEVICE") or "cuda"

    unet = UNet2DConditionModel.from_config(base, subfolder="unet").to(default_device, torch.float16)
    unet.load_state_dict(load_file(hf_hub_download(repo, ckpt), device=default_device))
    pipe = StableDiffusionXLPipeline.from_pretrained(base, unet=unet, torch_dtype=torch.float16, variant="fp16").to(default_device)

    pipe.scheduler = EulerDiscreteScheduler.from_config(pipe.scheduler.config, timestep_spacing="trailing")

    image = pipe(prompt, num_inference_steps=4, guidance_scale=0).images[0]

    image_data = io.BytesIO()
    image.save(image_data, format="JPEG")
    image_base64 = base64.b64encode(image_data.getvalue()).decode('utf-8')

    sharedmem["image"] = image_base64
