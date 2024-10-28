from torch.multiprocessing import Process, set_start_method, Manager
from ilock import ILock, ILockException

try:
    set_start_method('spawn')
except RuntimeError:
    pass

from app.models.models import ImageModel

def generate(worker, imageModel: ImageModel):
    manager = Manager()
    sharedmem = manager.dict()
    
    if imageModel.image:
        sharedmem["input_image"] = imageModel.image

    with ILock('stablediffusion', timeout=180):
        p = Process(target=worker, args=(imageModel.prompt, sharedmem))
        p.start()
        p.join()
        p.kill()

    if "image" not in sharedmem or not sharedmem["image"]:
        raise Exception("An error occurred while processing the image. Please try again.")

    return sharedmem["image"]