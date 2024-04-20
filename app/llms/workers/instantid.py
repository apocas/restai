import base64
import io
from diffusers.models import ControlNetModel
from huggingface_hub import hf_hub_download

import cv2
import torch
import numpy as np
import random
from PIL import Image
from insightface.app import FaceAnalysis

from app.config import RESTAI_DEFAULT_DEVICE
from app.llms.workers.pipeline_stable_diffusion_xl_instantid import StableDiffusionXLInstantIDPipeline, draw_kps

def worker(prompt, sharedmem):
    try:
        hf_hub_download(repo_id="InstantX/InstantID", filename="ControlNetModel/config.json", local_dir="./checkpoints")
        hf_hub_download(repo_id="InstantX/InstantID", filename="ControlNetModel/diffusion_pytorch_model.safetensors", local_dir="./checkpoints")
        hf_hub_download(repo_id="InstantX/InstantID", filename="ip-adapter.bin", local_dir="./checkpoints")
    except:
        pass

    img_data = base64.b64decode(sharedmem["input_image"])
    face_image = Image.open(io.BytesIO(img_data))

    negative_prompt = sharedmem["negative_prompt"]

    if not negative_prompt:
        negative_prompt = "(lowres, low quality, worst quality:1.2), (text:1.2), watermark, (frame:1.2), deformed, ugly, deformed eyes, blur, out of focus, blurry, deformed cat, deformed, photo, anthropomorphic cat, monochrome, photo, pet collar, gun, weapon, blue, 3d, drones, drone, buildings in background, green"

    app = FaceAnalysis(name='antelopev2', root='./', providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])
    app.prepare(ctx_id=0, det_size=(640, 640))

    face_adapter = f'./checkpoints/ip-adapter.bin'
    controlnet_path = f'./checkpoints/ControlNetModel'

    controlnet = ControlNetModel.from_pretrained(controlnet_path, torch_dtype=torch.float16)

    pipe = StableDiffusionXLInstantIDPipeline.from_pretrained(
        "wangqixun/YamerMIX_v8", controlnet=controlnet, torch_dtype=torch.float16
    )
    pipe.to(RESTAI_DEFAULT_DEVICE or "cuda:0")

    pipe.load_ip_adapter_instantid(face_adapter)

    face_image_cv2 = cv2.cvtColor(np.array(face_image), cv2.COLOR_RGB2BGR)
    height, width, _ = face_image_cv2.shape

    face_info = app.get(face_image_cv2)
    face_info = sorted(face_info, key=lambda x:(x['bbox'][2]-x['bbox'][0])*x['bbox'][3]-x['bbox'][1])[-1]
    face_emb = face_info['embedding']
    face_kps = draw_kps(face_image, face_info['kps'])

    control_mask = np.zeros([height, width, 3])
    x1, y1, x2, y2 = face_info["bbox"]
    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
    control_mask[y1:y2, x1:x2] = 255
    control_mask = Image.fromarray(control_mask.astype(np.uint8))

    pipe.set_ip_adapter_scale(0.8)

    generator = torch.Generator(device=RESTAI_DEFAULT_DEVICE or "cuda:0").manual_seed(random.randint(0, np.iinfo(np.int32).max))

    image = pipe(
        prompt,
        image_embeds=face_emb,
        image=face_kps,
        control_mask=control_mask,
        num_inference_steps=50,
        controlnet_conditioning_scale=0.8,
        negative_prompt=negative_prompt,
        generator=generator,
        guide_scale=0,
        height=height,
        width=width,
    ).images[0]

    output_img_data = io.BytesIO()
    image.save(output_img_data, format="JPEG")
    image_base64 = base64.b64encode(output_img_data.getvalue()).decode('utf-8')

    sharedmem["output_image"] = image_base64
