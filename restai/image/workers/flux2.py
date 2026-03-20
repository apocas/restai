import os

# os.environ["CUDA_VISIBLE_DEVICES"]="0,1,2,3"

def get_python_executable():
    current_file_path = os.path.abspath(__file__)
    project_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file_path))))

    return os.path.join(project_path, ".venvs/.venv-flux2/bin/python")


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
    from diffusers import Flux2Pipeline, AutoModel
    from diffusers.utils import load_image
    from transformers import Mistral3ForConditionalGeneration
    from PIL import Image

    repo_id = "diffusers/FLUX.2-dev-bnb-4bit"
    device = "cuda:0"
    torch_dtype = torch.bfloat16

    text_encoder = Mistral3ForConditionalGeneration.from_pretrained(
        repo_id, subfolder="text_encoder", torch_dtype=torch_dtype, device_map="cpu"
    )
    dit = AutoModel.from_pretrained(
        repo_id, subfolder="transformer", torch_dtype=torch_dtype, device_map="cpu"
    )
    pipe = Flux2Pipeline.from_pretrained(
        repo_id, text_encoder=text_encoder, transformer=dit, torch_dtype=torch_dtype
    )
    pipe.enable_model_cpu_offload()

    input_image = None
    if "input_image" in sharedmem and sharedmem["input_image"]:
        img_data = base64.b64decode(sharedmem["input_image"])
        input_image = Image.open(io.BytesIO(img_data)).convert("RGB")

    kwargs = {
        "prompt": prompt,
        "generator": torch.Generator(device=device).manual_seed(0),
        "num_inference_steps": 20,
        "guidance_scale": 4,
    }

    if input_image is not None:
        kwargs["image"] = [input_image]

    result = pipe(**kwargs).images[0]

    image_data = io.BytesIO()
    result.save(image_data, format="JPEG")
    image_base64 = base64.b64encode(image_data.getvalue()).decode("utf-8")

    sharedmem["image"] = image_base64

    flush()
