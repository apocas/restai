import os


def get_python_executable():
    current_file_path = os.path.abspath(__file__)
    project_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file_path))))

    return os.path.join(project_path, ".venvs/.venv-granite-speech/bin/python")


def worker(prompt, sharedmem):
    import torch
    import torchaudio
    from transformers import AutoProcessor, AutoModelForSpeechSeq2Seq

    file_path = sharedmem["file_path"]

    device = os.environ.get("RESTAI_DEFAULT_DEVICE") or "cuda:0"

    model_name = "ibm-granite/granite-speech-3.3-8b"
    processor = AutoProcessor.from_pretrained(model_name)
    tokenizer = processor.tokenizer
    model = AutoModelForSpeechSeq2Seq.from_pretrained(
        model_name,
        device_map=device,
        dtype=torch.bfloat16,
    )

    wav, sr = torchaudio.load(file_path, normalize=True)
    # Convert to mono if needed
    if wav.shape[0] > 1:
        wav = wav.mean(dim=0, keepdim=True)
    # Resample to 16kHz if needed
    if sr != 16000:
        wav = torchaudio.transforms.Resample(sr, 16000)(wav)

    # Build prompt
    language = None
    if sharedmem.get("options") and "language" in sharedmem["options"]:
        language = sharedmem["options"]["language"]

    if language:
        user_prompt = f"<|audio|>transcribe the speech into {language} written format."
    else:
        user_prompt = "<|audio|>can you transcribe the speech into a written format?"

    chat = [
        {"role": "user", "content": user_prompt},
    ]
    text_prompt = tokenizer.apply_chat_template(chat, tokenize=False, add_generation_prompt=True)

    model_inputs = processor(text_prompt, wav, device=device, return_tensors="pt").to(device)
    model_outputs = model.generate(**model_inputs, max_new_tokens=500, do_sample=False, num_beams=1)

    num_input_tokens = model_inputs["input_ids"].shape[-1]
    new_tokens = torch.unsqueeze(model_outputs[0, num_input_tokens:], dim=0)
    output_text = tokenizer.batch_decode(
        new_tokens, add_special_tokens=False, skip_special_tokens=True
    )

    text = output_text[0].strip() if output_text else ""

    sharedmem["output"] = {"text": text, "chunks": []}
