import os
import torch
import whisperx
import gc

from restai import config

os.environ["CUDA_VISIBLE_DEVICES"] = "0,1,2,3"

def worker(prompt, sharedmem):
    file_path = sharedmem["file_path"]
    filename = sharedmem["filename"]

    device = os.environ.get("RESTAI_DEFAULT_DEVICE") or "cuda:0"

    batch_size = 16

    model = whisperx.load_model("large-v3", "cuda", compute_type="float16")

    audio = whisperx.load_audio(file_path)
    result = model.transcribe(audio, batch_size=batch_size)

    gc.collect()
    torch.cuda.empty_cache()
    del model

    model_a, metadata = whisperx.load_align_model(
        language_code=result["language"], device=device
    )
    result = whisperx.align(
        result["segments"],
        model_a,
        metadata,
        audio,
        device,
        return_char_alignments=False,
    )

    gc.collect()
    torch.cuda.empty_cache()
    del model_a

    diarize_model = whisperx.diarize.DiarizationPipeline(
        use_auth_token=config.HF_TOKEN, device=device
    )

    diarize_segments = diarize_model(audio)
    result = whisperx.assign_word_speakers(diarize_segments, result)
    
    # Concatenate all segment texts to build the complete transcription
    full_text = " ".join([segment["text"] for segment in result["segments"]])
    
    sharedmem["output"] = {
      "text": full_text,
      "chunks": result["segments"],
      "word_chunks": result["word_segments"],
    }
