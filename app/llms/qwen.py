import base64
import io
import os
import tempfile
from PIL import Image


class QwenLLM:
    def __init__(self, model):
        self.modelid = model

        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch
        torch.manual_seed(1234)

        self.tokenizer = AutoTokenizer.from_pretrained(self.modelid, trust_remote_code=True)

        self.model = AutoModelForCausalLM.from_pretrained(self.modelid, device_map=os.environ.get("RESTAI_DEFAULT_DEVICE") or "cuda:0", trust_remote_code=True).eval()
    
    def inference(self, input, image, history = None):
        import imghdr

        image_data = base64.b64decode(image)

        image_format = imghdr.what(None, h=image_data)
        if not image_format:
            raise ValueError("Invalid image format")

        with tempfile.NamedTemporaryFile(suffix=f".{image_format}", delete=False) as temp_file:
            temp_file.write(image_data)
            temp_file_path = temp_file.name

        query = self.tokenizer.from_list_format([
            {'image': temp_file_path},
            {'text': input.strip()},
        ])

        response, history = self.model.chat(self.tokenizer, query=query, history=history)

        image = self.tokenizer.draw_bbox_on_latest_picture(response, history)

        if image:
          pil_image = Image.fromarray(image.get_image())
          image_data = io.BytesIO()
          pil_image.save(image_data, format="JPEG")
          image_base64 = base64.b64encode(image_data.getvalue()).decode('utf-8')
        else:
          image_base64 = None
       
        return response, image_base64, history





