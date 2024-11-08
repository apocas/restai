import base64
import io
from diffusers import BitsAndBytesConfig, SD3Transformer2DModel
from diffusers import StableDiffusion3Pipeline
import torch
from transformers import T5EncoderModel

from app.config import RESTAI_DEFAULT_DEVICE


def worker(prompt, sharedmem):
    model_id = "stabilityai/stable-diffusion-3.5-medium"

    nf4_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16
    )
    model_nf4 = SD3Transformer2DModel.from_pretrained(
        model_id,
        subfolder="transformer",
        quantization_config=nf4_config,
        torch_dtype=torch.bfloat16
    )

    t5_nf4 = T5EncoderModel.from_pretrained("diffusers/t5-nf4", torch_dtype=torch.bfloat16)

    pipeline = StableDiffusion3Pipeline.from_pretrained(
        model_id, 
        transformer=model_nf4,
        text_encoder_3=t5_nf4,
        torch_dtype=torch.bfloat16
    )
    pipeline.enable_model_cpu_offload()

    image = pipeline(
        prompt=prompt,
        num_inference_steps=40,
        guidance_scale=4.5,
        max_sequence_length=512,
    ).images[0]


    image_data = io.BytesIO()
    image.save(image_data, format="JPEG")
    image_base64 = base64.b64encode(image_data.getvalue()).decode('utf-8')

    sharedmem["image"] = image_base64
