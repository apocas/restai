PROMPTS = {
    "openai": """{system}
        Question: {{query_str}}
        =========
        Answer:
        """,
    "gemini": """{system}\nQuestion: {{query_str}}""",
    "llama": """[INST]<<SYS>>\n{system}\n<</SYS>>\n\n{{query_str}}[/INST]""",
    "vicuna": """A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. If the user asks the assistant to do something forever or something that it cannot finish, the assistant should respond saying that it can only execute finite actions. {system} USER: {{query_str}} ASSISTANT:""",
    "spicy": """A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. If the user asks the assistant to do something forever or something that it cannot finish, the assistant should respond saying that it can only execute finite actions.\n{system}\nUSER: {{query_str}}\nASSISTANT:""",
    "plain": """{system}\n{query_str}""",
    "llava": """USER: <image>\n{query_str}\nASSISTANT:""",
    "mistral": """[INST] {system} {{query_str}} [/INST]"""
}
