from torch.multiprocessing import Process
from ilock import ILock
from fastapi import UploadFile
import tempfile
import os
import shutil


def generate(manager, worker, prompt:str, file: UploadFile):
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
        except Exception as e:
            if temp_file:
                os.unlink(temp_file.name)
            raise e
    else:
        raise Exception("No file provided. Please upload an audio file.")

    try:
        with ILock('audio', timeout=180):
            p = Process(target=worker, args=(prompt, sharedmem))
            p.start()
            p.join()
            p.kill()

        if "output" not in sharedmem or not sharedmem["output"]:
            raise Exception("An error occurred while processing the audio. Please try again.")

        return sharedmem["output"]
    finally:
        if temp_file:
            try:
                os.unlink(temp_file.name)
            except:
                pass