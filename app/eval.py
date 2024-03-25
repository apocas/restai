from llama_index.core.llms.llm import LLM
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.metrics import AnswerRelevancyMetric
from deepeval.test_case import LLMTestCase

class DeepEvalLLM(DeepEvalBaseLLM):
    def __init__(
        self,
        model: LLM
    ):
        self.model = model

    def load_model(self):
        return self.model

    def generate(self, prompt: str) -> str:
        return self.model.complete(prompt).text

    async def a_generate(self, prompt: str) -> str:
        res = await self.model.complete(prompt)
        return res.text

    def get_model_name(self):
        return "Custom LLamaindex LLM"
      
def evalRAG(question, response, llm):
    if response is not None:
        actual_output = response.response
        retrieval_context = [node.get_content() for node in response.source_nodes]
    else:
        return None

    test_case = LLMTestCase(
        input=question,
        actual_output=actual_output,
        retrieval_context=retrieval_context
    )
    
    llm = DeepEvalLLM(model=llm)
    
    metric = AnswerRelevancyMetric(threshold=0.5, model=llm, include_reason=True, async_mode=False)
    metric.measure(test_case)
    
    return metric