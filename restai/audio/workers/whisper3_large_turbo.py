import os

os.environ["CUDA_VISIBLE_DEVICES"] = "0,1,2,3"


def worker(prompt, sharedmem):
    import torch
    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

    file_path = sharedmem["file_path"]
    filename = sharedmem["filename"]

    device = os.environ.get("RESTAI_DEFAULT_DEVICE") or "cuda:0"
    torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    model_id = "openai/whisper-large-v3-turbo"

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

    gkwargs = {}
    if sharedmem["options"] and "language" in sharedmem["options"]:
        gkwargs["language"] = sharedmem["options"]["language"]

    result = pipe(file_path, return_timestamps=True, generate_kwargs=gkwargs)

    if isinstance(result, dict) and "text" in result and "chunks" in result:
        sharedmem["output"] = {
            "text": result["text"].strip(),
            "chunks": [
                {
                    "text": chunk["text"].strip(),
                    "timestamp": chunk.get("timestamp", None),
                }
                for chunk in result["chunks"]
            ],
        }
    elif isinstance(result, dict) and "text" in result:
        sharedmem["output"] = {"text": result["text"].strip(), "chunks": []}
    elif isinstance(result, dict) and "chunks" in result:
        sharedmem["output"] = {
            "text": " ".join([chunk["text"] for chunk in result["chunks"]]).strip(),
            "chunks": [
                {
                    "text": chunk["text"].strip(),
                    "timestamp": chunk.get("timestamp", None),
                }
                for chunk in result["chunks"]
            ],
        }
    else:
        sharedmem["output"] = {"text": str(result).strip(), "chunks": []}
