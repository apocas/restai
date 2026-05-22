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
                    venv_python = sys.executable

            env = os.environ.copy()
            # Project root is 3 levels up: restai/restai/image/runner.py
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            env["PYTHONPATH"] = project_root

            from restai import config
            if config.GPU_WORKER_DEVICES:
                env["CUDA_VISIBLE_DEVICES"] = config.GPU_WORKER_DEVICES

            # When parent stdout isn't a TTY (systemd/docker/k8s), tqdm/HF
            # carriage-return + ANSI escapes get logged by journald as
            # `[NNN blob data]` lines. Disable progress bars so journald sees plain text.
            if not sys.stdout.isatty():
                env.setdefault("TQDM_DISABLE", "1")
                env.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

            # Inherit parent stdout/stderr so diffusers progress bars and tracebacks
            # land in the API console live (capturing left admins staring at a silent terminal).
            result = subprocess.run([
                venv_python,
                os.path.join(os.path.dirname(__file__), "worker_entry.py"),
                worker_module,
                sharedmem.get("prompt", ""),
                sharedmem_file.name
            ], env=env)
            if result.returncode != 0:
                import logging
                logging.error(f"Image worker {worker_module} failed (exit {result.returncode}) — traceback above.")
                raise subprocess.CalledProcessError(result.returncode, result.args)

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