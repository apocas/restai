import base64
import io
import torch
from diffusers import FluxPipeline
import gc
from diffusers import FluxTransformer2DModel
from diffusers import AutoencoderKL
from diffusers.image_processor import VaeImageProcessor

from app.config import RESTAI_DEFAULT_DEVICE

def flush():
    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.reset_max_memory_allocated()
    torch.cuda.reset_peak_memory_stats()

def worker(prompt, sharedmem):

    pipeline = FluxPipeline.from_pretrained(
        "black-forest-labs/FLUX.1-dev",
        transformer=None,
        vae=None,
        device_map="balanced",
        max_memory={0: "24GB", 1: "24GB"},
        torch_dtype=torch.bfloat16
    )
    with torch.no_grad():
        print("Encoding prompts.")
        prompt_embeds, pooled_prompt_embeds, text_ids = pipeline.encode_prompt(
            prompt=prompt, prompt_2=None, max_sequence_length=512
        )

    del pipeline.text_encoder
    del pipeline.text_encoder_2
    del pipeline.tokenizer
    del pipeline.tokenizer_2
    del pipeline

    flush()
    
    transformer = FluxTransformer2DModel.from_pretrained(
        "black-forest-labs/FLUX.1-dev",
        subfolder="transformer",
        device_map="auto",
        torch_dtype=torch.bfloat16
    )
    
    pipeline = FluxPipeline.from_pretrained(
        "black-forest-labs/FLUX.1-dev",
        text_encoder=None,
        text_encoder_2=None,
        tokenizer=None,
        tokenizer_2=None,
        vae=None,
        transformer=transformer,
        torch_dtype=torch.bfloat16
    )

    print("Running denoising.")
    height, width = 768, 1360
    latents = pipeline(
        prompt_embeds=prompt_embeds,
        pooled_prompt_embeds=pooled_prompt_embeds,
        num_inference_steps=50,
        guidance_scale=3.5,
        height=height,
        width=width,
        output_type="latent",
    ).images
    
    del pipeline.transformer
    del pipeline

    flush()
    
    vae = AutoencoderKL.from_pretrained("black-forest-labs/FLUX.1-dev", subfolder="vae", torch_dtype=torch.bfloat16).to("cuda")
    vae_scale_factor = 2 ** (len(vae.config.block_out_channels))
    image_processor = VaeImageProcessor(vae_scale_factor=vae_scale_factor)

    with torch.no_grad():
        print("Running decoding.")
        latents = FluxPipeline._unpack_latents(latents, height, width, vae_scale_factor)
        latents = (latents / vae.config.scaling_factor) + vae.config.shift_factor

        image = vae.decode(latents, return_dict=False)[0]
        image = image_processor.postprocess(image, output_type="pil")
        
        image_data = io.BytesIO()
        image[0].save(image_data, format="JPEG")
        image_base64 = base64.b64encode(image_data.getvalue()).decode('utf-8')

        sharedmem["image"] = image_base64
