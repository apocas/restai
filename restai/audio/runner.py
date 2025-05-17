from torch.multiprocessing import Process
from ilock import ILock
from fastapi import UploadFile
import tempfile
import os
import shutil
import subprocess
import sys
import pickle


def generate(manager, worker, prompt: str, file: UploadFile, options: dict = None, venv_python: str = None):
    sharedmem = manager.dict()
    temp_file = None
    if file:
        file_ext = os.path.splitext(file.filename)[1].lower() if file.filename else ''
        temp_file = tempfile.NamedTemporaryFile(suffix=file_ext, delete=False)
        try:
            shutil.copyfileobj(file.file, temp_file)
            temp_file.close()
            sharedmem["file_path"] = temp_file.name
            sharedmem["filename"] = file.filename
            sharedmem["options"] = options
        except Exception as e:
            if temp_file:
                os.unlink(temp_file.name)
            raise e
    else:
        raise Exception("No file provided. Please upload an audio file.")

    # Save sharedmem to a temp file for IPC
    sharedmem_file = tempfile.NamedTemporaryFile(delete=False)
    with open(sharedmem_file.name, "wb") as f:
        pickle.dump(dict(sharedmem), f)

    try:
        with ILock('audio', timeout=180):
            worker_module = worker.__module__
            if venv_python is None:
                import importlib
                module = importlib.import_module(worker_module)
                if hasattr(module, 'get_python_executable'):
                    venv_python = module.get_python_executable()
                else:
                    venv_python = sys.executable  # fallback to current python
            # Set PYTHONPATH so the worker subprocess can import the restai package
            env = os.environ.copy()
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            env["PYTHONPATH"] = project_root
            subprocess.run([
                venv_python,
                os.path.join(os.path.dirname(__file__), "worker_entry.py"),
                worker_module,
                prompt,
                sharedmem_file.name
            ], check=True, env=env)

        # Load sharedmem back
        with open(sharedmem_file.name, "rb") as f:
            sharedmem_result = pickle.load(f)

        if "output" not in sharedmem_result or not sharedmem_result["output"]:
            raise Exception("An error occurred while processing the audio. Please try again.")

        return sharedmem_result["output"]
    finally:
        if temp_file:
            try:
                os.unlink(temp_file.name)
            except:
                pass
        try:
            os.unlink(sharedmem_file.name)
        except:
            pass