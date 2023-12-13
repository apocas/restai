from typing import Any, List, Mapping, Optional

from langchain.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.llms import LLM

from vertexai.preview.generative_models import GenerativeModel, Part

class GeminiLLM(LLM):
    top_p:          Optional[float] = 1
    max_output_tokens:     Optional[int]   = 2048
    temperature:           Optional[float] = 0.1

    @property
    def _llm_type(self) -> str:
        return "GeminiLLM"
      
    @property
    def _get_model_default_parameters(self):
        return {"top_p": self.top_p, "max_output_tokens": self.max_output_tokens, "temperature": self.temperature}

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        params = {
          **self._get_model_default_parameters,
          **kwargs
        }
      
        model = GenerativeModel("gemini-pro")
        responses = model.generate_content(
            prompt,
            generation_config=params,
        )

        return responses.text

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        """Get the identifying parameters."""
        return {"top_p": self.top_p, "max_output_tokens": self.max_output_tokens, "temperature": self.temperature}