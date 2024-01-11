import base64
import io
import os
from torch.multiprocessing import Process, set_start_method, Manager
try:
    set_start_method('spawn')
except RuntimeError:
    pass
from langchain.tools import BaseTool
from langchain.chains import LLMChain
from langchain.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate
from diffusers import DiffusionPipeline
import torch
from typing import Optional
from langchain.callbacks.manager import (
    CallbackManagerForToolRun,
)


def sd_worker(prompt, sharedmem):
    base = DiffusionPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0", torch_dtype=torch.float16, variant="fp16", use_safetensors=True
    )
    base.to(os.environ.get("RESTAI_DEFAULT_DEVICE") or "cuda")

    refiner = DiffusionPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-refiner-1.0",
        text_encoder_2=base.text_encoder_2,
        vae=base.vae,
        torch_dtype=torch.float16,
        use_safetensors=True,
        variant="fp16",
    )
    refiner.to(os.environ.get("RESTAI_DEFAULT_DEVICE") or "cuda")

    image = base(
        prompt=prompt,
        num_inference_steps=40,
        denoising_end=0.8,
        output_type="latent",
    ).images
    image = refiner(
        prompt=prompt,
        num_inference_steps=40,
        denoising_start=0.8,
        image=image,
    ).images[0]

    image_data = io.BytesIO()
    image.save(image_data, format="JPEG")
    image_base64 = base64.b64encode(image_data.getvalue()).decode('utf-8')

    sharedmem["image"] = image_base64


class StableDiffusionImage(BaseTool):
    name = "Stable Diffusion Image Generator"
    description = "use this tool when you need to generate an image using Stable Diffusion."
    return_direct = True
    disableboost = False

    def _run(self, query: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        if run_manager.tags[0].disableboost == False:
            llm = ChatOpenAI(temperature=0.9, model_name="gpt-3.5-turbo")
            prompt = PromptTemplate(
                input_variables=["image_desc"],
                template="Generate a detailed prompt to generate an image based on the following description: {image_desc}",
            )
            chain = LLMChain(llm=llm, prompt=prompt)

            fprompt = chain.run(query)
        else:
            fprompt = run_manager.tags[0].question

        manager = Manager()
        sharedmem = manager.dict()

        p = Process(target=sd_worker, args=(fprompt, sharedmem))
        p.start()
        p.join()

        return {"type": "stablediffusion", "image": sharedmem["image"], "prompt": fprompt}

    async def _arun(self, query: str) -> str:
        raise NotImplementedError("N/A")