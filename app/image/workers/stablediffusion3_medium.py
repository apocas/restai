import base64
import io
import os
from diffusers import StableDiffusion3Pipeline
import torch

from app.config import RESTAI_DEFAULT_DEVICE

os.environ["CUDA_VISIBLE_DEVICES"]="0,1,2,3"

def worker(prompt, sharedmem):
    base = StableDiffusion3Pipeline.from_pretrained("stabilityai/stable-diffusion-3-medium-diffusers", torch_dtype=torch.float16)
    base.to(RESTAI_DEFAULT_DEVICE or "cuda")

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
