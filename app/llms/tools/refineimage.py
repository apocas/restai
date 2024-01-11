import base64
import io
import os
from pydantic import BaseModel
from torch.multiprocessing import Process, set_start_method, Manager

from app.models import VisionModel
try:
    set_start_method('spawn')
except RuntimeError:
    pass
from langchain.tools import BaseTool
from diffusers import DiffusionPipeline
import torch
from PIL import Image
from typing import Optional


from langchain.callbacks.manager import (
    CallbackManagerForToolRun,
)


def refine_worker(prompt, sharedmem):
    refiner = DiffusionPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-refiner-1.0",
        torch_dtype=torch.float16,
        use_safetensors=True,
        variant="fp16",
        device_map=os.environ.get("RESTAI_DEFAULT_DEVICE") or "cuda:0",
    )
    refiner.to(os.environ.get("RESTAI_DEFAULT_DEVICE") or "cuda")

    image = refiner(
        prompt=prompt,
        num_inference_steps=5,
        denoising_start=0.8,
        image=Image.open(io.BytesIO(base64.b64decode(sharedmem["model"].image))),
    ).images[0]

    image_data = io.BytesIO()
    image.save(image_data, format="JPEG")
    image_base64 = base64.b64encode(image_data.getvalue()).decode('utf-8')

    sharedmem["image"] = image_base64


class RefineImage(BaseTool):
    name = "Image refiner"
    description = "use this tool when you need to refine an image."
    return_direct = True

    def _run(self, query: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        manager = Manager()
        sharedmem = manager.dict()

        sharedmem["model"] = run_manager.tags[0]
        query = run_manager.tags[0].question

        p = Process(target=refine_worker, args=(query, sharedmem))
        p.start()
        p.join()

        return {"type": "refineimage", "image": sharedmem["image"], "prompt": query}

    async def _arun(self, query: str) -> str:
        raise NotImplementedError("N/A")
