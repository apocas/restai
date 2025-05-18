import os

#os.environ["CUDA_VISIBLE_DEVICES"]="0,1,2,3"

def get_python_executable():
    current_file_path = os.path.abspath(__file__)
    project_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file_path))))
    
    return os.path.join(project_path, ".venvs/.venv-sd/bin/python")

def worker(prompt, sharedmem):
    import base64
    import io
    from diffusers import DiffusionPipeline
    import torch

    from restai.config import RESTAI_DEFAULT_DEVICE

    base = DiffusionPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0", torch_dtype=torch.float16, variant="fp16", use_safetensors=True
    )
    base.to(RESTAI_DEFAULT_DEVICE or "cuda")

    refiner = DiffusionPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-refiner-1.0",
        text_encoder_2=base.text_encoder_2,
        vae=base.vae,
        torch_dtype=torch.float16,
        use_safetensors=True,
        variant="fp16",
    )

    refiner.to(RESTAI_DEFAULT_DEVICE or "cuda")

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
