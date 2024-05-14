import base64
import io
from torch.multiprocessing import Process, set_start_method, Manager

from app.llms.workers.instantid import worker
try:
    set_start_method('spawn')
except RuntimeError:
    pass
from langchain.tools import BaseTool
from langchain.chains import LLMChain
from langchain_community.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate
from PIL import Image
from ilock import ILock, ILockException

from typing import Optional
from langchain.callbacks.manager import (
    CallbackManagerForToolRun,
)


class InstantID(BaseTool):
    name = "Avatar Generator"
    description = "use this tool when you need to draw an avatar from an image and a descripton."
    return_direct = True

    def _run(self, query: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        if run_manager.tags[0].boost == True:
            llm = ChatOpenAI(temperature=0.9, model_name="gpt-3.5-turbo")
            prompt = PromptTemplate(
                input_variables=["image_desc"],
                template="Generate a detailed prompt to generate an image based on the following description: {image_desc}",
            )
            chain = LLMChain(llm=llm, prompt=prompt)

            fprompt = chain.run(query)
        else:
            fprompt = run_manager.tags[0].question

        manager = Manager()
        sharedmem = manager.dict()
        
        if not run_manager.tags[0].image:
            raise Exception("Please provide an image to generate an avatar.")

        sharedmem["input_image"] = run_manager.tags[0].image

        img_data = base64.b64decode(sharedmem["input_image"])
        face_image = Image.open(io.BytesIO(img_data))
        height = face_image.size[1]
        if height > 1920:
            raise Exception("Send a smaller image. The maximum height is 1920 pixels.")

        sharedmem["negative_prompt"] = run_manager.tags[0].negative

        with ILock('instantid', timeout=180):
            p = Process(target=worker, args=(fprompt, sharedmem))
            p.start()
            p.join()
            p.kill()

        if not sharedmem["output_image"]:
            raise Exception("An error occurred while processing the image. Please try again.")

        return {"type": "instantid", "image": sharedmem["output_image"], "prompt": fprompt}

    async def _arun(self, query: str) -> str:
        raise NotImplementedError("N/A")