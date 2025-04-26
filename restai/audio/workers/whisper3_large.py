import mimetypes
import os
import tempfile

import torch
from fastapi import UploadFile
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

os.environ["CUDA_VISIBLE_DEVICES"]="0,1,2,3"

def worker(prompt, sharedmem):
    file_path = sharedmem["file_path"]
    filename = sharedmem["filename"]
    
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
    
    result = pipe(file_path, return_timestamps=True)
    
    if isinstance(result, dict) and "text" in result:
        sharedmem["output"] = result["text"].strip()
    elif isinstance(result, dict) and "chunks" in result:
        full_text = " ".join([chunk["text"] for chunk in result["chunks"]])
        sharedmem["output"] = full_text.strip()
    else:
        sharedmem["output"] = str(result).strip()