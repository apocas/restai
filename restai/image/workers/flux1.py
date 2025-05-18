import os

# os.environ["CUDA_VISIBLE_DEVICES"]="0,1,2,3"

def get_python_executable():
    current_file_path = os.path.abspath(__file__)
    project_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file_path))))
    
    return os.path.join(project_path, ".venvs/.venv-sd/bin/python")

def flush():
    import torch
    import gc
    
    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.reset_max_memory_allocated()
    torch.cuda.reset_peak_memory_stats()


def worker(prompt, sharedmem):
    import base64
    import io
    import torch
    from diffusers import DiffusionPipeline
    from transformers import T5EncoderModel, BitsAndBytesConfig

    quantization_config = BitsAndBytesConfig(load_in_8bit=True)

    model_id = "black-forest-labs/FLUX.1-schnell"
    text_encoder = T5EncoderModel.from_pretrained(
        model_id,
        subfolder="text_encoder_2",
        quantization_config=quantization_config,
        torch_dtype=torch.bfloat16,
    )

    pipe = DiffusionPipeline.from_pretrained(
        model_id,
        torch_dtype=torch.bfloat16,
        text_encoder_2=text_encoder,
        device_map="balanced",
        max_memory={0: "22GiB", "cpu": "10GiB"},
    )
    pipe.vae.enable_tiling()

    
    image = pipe(
        prompt,
        prompt_2="",
        num_images_per_prompt=1,
        guidance_scale=0.0,
        num_inference_steps=4,
        max_sequence_length=256,
        generator=torch.Generator("cpu").manual_seed(0),
    ).images[0]

    image_data = io.BytesIO()
    image.save(image_data, format="JPEG")
    image_base64 = base64.b64encode(image_data.getvalue()).decode("utf-8")

    sharedmem["image"] = image_base64
