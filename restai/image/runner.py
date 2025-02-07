from torch.multiprocessing import Process
from ilock import ILock

from restai.models.models import ImageModel

def generate(manager, worker, imageModel: ImageModel):
    sharedmem = manager.dict()
    
    if imageModel.image:
        sharedmem["input_image"] = imageModel.image

    with ILock('image', timeout=180):
        p = Process(target=worker, args=(imageModel.prompt, sharedmem))
        p.start()
        p.join()
        p.kill()

    if "image" not in sharedmem or not sharedmem["image"]:
        raise Exception("An error occurred while processing the image. Please try again.")

    return sharedmem["image"]