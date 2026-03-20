from torch.multiprocessing import Process
from ilock import ILock
import tempfile
import os
import subprocess
import sys
import pickle

from restai.models.models import ImageModel

def generate(manager, worker, imageModel, options: dict = None, venv_python: str = None):
    sharedmem = manager.dict()
    if hasattr(imageModel, 'image') and imageModel.image:
        sharedmem["input_image"] = imageModel.image

    sharedmem["prompt"] = imageModel.prompt
    sharedmem["options"] = options

    # Save sharedmem to a temp file for IPC
    sharedmem_file = tempfile.NamedTemporaryFile(delete=False)
    with open(sharedmem_file.name, "wb") as f:
        pickle.dump(dict(sharedmem), f)

    try:
        with ILock('image', timeout=180):
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
            # Project root is 3 levels up from this file (restai/restai/image/runner.py)
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            env["PYTHONPATH"] = project_root

            # Set CUDA_VISIBLE_DEVICES from settings if configured
            from restai import config
            if config.GPU_WORKER_DEVICES:
                env["CUDA_VISIBLE_DEVICES"] = config.GPU_WORKER_DEVICES

            result = subprocess.run([
                venv_python,
                os.path.join(os.path.dirname(__file__), "worker_entry.py"),
                worker_module,
                sharedmem.get("prompt", ""),
                sharedmem_file.name
            ], capture_output=True, text=True, env=env)
            if result.returncode != 0:
                import logging
                logging.error(f"Image worker {worker_module} failed (exit {result.returncode}):\n{result.stderr}")
                raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)

        # Load sharedmem back
        with open(sharedmem_file.name, "rb") as f:
            sharedmem_result = pickle.load(f)

        if "image" not in sharedmem_result or not sharedmem_result["image"]:
            raise Exception("An error occurred while processing the image. Please try again.")

        return sharedmem_result["image"]
    finally:
        try:
            os.unlink(sharedmem_file.name)
        except:
            pass