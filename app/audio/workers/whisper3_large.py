import torch
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
from fastapi import UploadFile
import soundfile as sf
import io
import tempfile
import os
import mimetypes

os.environ["CUDA_VISIBLE_DEVICES"]="0,1,2,3"

def worker(prompt, sharedmem):
    file : UploadFile = sharedmem["file"]
    
    device = os.environ.get("RESTAI_DEFAULT_DEVICE") or "cuda:0"
    torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    model_id = "openai/whisper-large-v3"

    model = AutoModelForSpeechSeq2Seq.from_pretrained(
        model_id, torch_dtype=torch_dtype, low_cpu_mem_usage=True, use_safetensors=True
    )
    model.to(device)

    processor = AutoProcessor.from_pretrained(model_id)

    pipe = pipeline(
        "automatic-speech-recognition",
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        torch_dtype=torch_dtype,
        device=device,
    )
    
    file_ext = os.path.splitext(file.filename)[1].lower()
    if not file_ext:
        content_type = file.content_type
        file_ext = mimetypes.guess_extension(content_type)

    temp_file = tempfile.NamedTemporaryFile(suffix=file_ext, delete=False)

    temp_file.write(file.file.read())
    temp_file.close()
    
    result = pipe(temp_file.name)
    
    sharedmem["output"] = result["text"].strip()