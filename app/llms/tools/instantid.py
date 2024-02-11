from torch.multiprocessing import Process, set_start_method, Manager

from app.llms.instantid.worker import instantid_worker
try:
    set_start_method('spawn')
except RuntimeError:
    pass
from langchain.tools import BaseTool
from langchain.chains import LLMChain
from langchain_community.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate

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

        sharedmem["input_image"] = run_manager.tags[0].image
        sharedmem["negative_prompt"] = run_manager.tags[0].negative

        p = Process(target=instantid_worker, args=(fprompt, sharedmem))
        p.start()
        p.join()

        return {"type": "instantid", "image": sharedmem["output_image"], "prompt": fprompt}

    async def _arun(self, query: str) -> str:
        raise NotImplementedError("N/A")