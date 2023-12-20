import base64
import io
import multiprocessing
from langchain.tools import BaseTool
from langchain.chains import LLMChain
from langchain.llms import OpenAI
from langchain.prompts import PromptTemplate
from langchain.utilities.dalle_image_generator import DallEAPIWrapper
from diffusers import DiffusionPipeline
import requests
import torch


class DalleImage(BaseTool):
    name = "Dall-E Image Generator"
    description = "use this tool when you need to generate an image using Dall-E."
    return_direct = True

    def _run(self, query: str) -> str:
        llm = OpenAI(temperature=0.9)
        prompt = PromptTemplate(
            input_variables=["image_desc"],
            template="Generate a detailed prompt to generate an image based on the following description: {image_desc}",
        )
        chain = LLMChain(llm=llm, prompt=prompt)
        prompt = chain.run(query)

        model = DallEAPIWrapper()
        model.model_name = "dall-e-3"
        
        image_url = model.run(prompt)

        response = requests.get(image_url)
        response.raise_for_status()
        image_data = response.content
        return {"image": base64.b64encode(image_data).decode('utf-8'), "prompt": prompt}

    async def _arun(self, query: str) -> str:
        raise NotImplementedError("N/A")


def sd_worker(prompt, sharedmem):
    base = DiffusionPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0", torch_dtype=torch.float16, variant="fp16", use_safetensors=True
    )
    base.to("cuda")

    refiner = DiffusionPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-refiner-1.0",
        text_encoder_2=base.text_encoder_2,
        vae=base.vae,
        torch_dtype=torch.float16,
        use_safetensors=True,
        variant="fp16",
    )
    refiner.to("cuda")

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

    def _run(self, query: str) -> str:
        llm = OpenAI(temperature=0.9)
        prompt = PromptTemplate(
            input_variables=["image_desc"],
            template="Generate a detailed prompt to generate an image based on the following description: {image_desc}",
        )
        chain = LLMChain(llm=llm, prompt=prompt)
        
        fprompt = chain.run(query)

        manager = multiprocessing.Manager()
        sharedmem = manager.dict()

        p = multiprocessing.Process(target=sd_worker, args=(fprompt, sharedmem))
        p.start()
        p.join()

        return {"image": sharedmem["image"], "prompt": fprompt}

    async def _arun(self, query: str) -> str:
        raise NotImplementedError("N/A")
