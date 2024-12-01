from torch.multiprocessing import Process
from ilock import ILock
from fastapi import UploadFile


def generate(manager, worker, prompt:str, file: UploadFile):
    sharedmem = manager.dict()
    
    if file:
        sharedmem["file"] = file

    with ILock('audio', timeout=180):
        p = Process(target=worker, args=(prompt, sharedmem))
        p.start()
        p.join()
        p.kill()

    if "output" not in sharedmem or not sharedmem["output"]:
        raise Exception("An error occurred while processing the audio. Please try again.")

    return sharedmem["output"]