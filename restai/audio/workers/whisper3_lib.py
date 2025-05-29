import os

os.environ["CUDA_VISIBLE_DEVICES"] = "0,1,2,3"


def get_python_executable():
    current_file_path = os.path.abspath(__file__)
    project_path = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(current_file_path)))
    )

    return os.path.join(project_path, ".venvs/.venv-whisper_lib/bin/python")


def worker(prompt, sharedmem):
    import whisper

    model = whisper.load_model("large-v3")

    file_path = sharedmem["file_path"]
    filename = sharedmem["filename"]

    result = model.transcribe(
        file_path, language=sharedmem["options"].get("language", None), temperature=0.0
    )

    sharedmem["output"] = {"text": result["text"].strip(), "chunks": result["segments"]}
