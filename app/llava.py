import base64
from io import BytesIO
import requests
from PIL import Image

class LlavaLLM:
    def __init__(self, model):
        self.model = model
    
    def llavaInference(self, prompt, imageb64):
        import torch
        from transformers import AutoProcessor, LlavaForConditionalGeneration
        
        model = LlavaForConditionalGeneration.from_pretrained(
            self.model,
            torch_dtype=torch.float16,
            low_cpu_mem_usage=True,
            load_in_4bit=True,
            use_flash_attention_2=True
        )

        processor = AutoProcessor.from_pretrained(self.model)

        raw_image = Image.open(BytesIO(base64.b64decode(imageb64)))
        
        inputs = processor(prompt, raw_image, return_tensors='pt').to(0, torch.float16)

        output = model.generate(**inputs, max_new_tokens=200, do_sample=False)
        
        return processor.decode(output[0][2:], skip_special_tokens=True)






