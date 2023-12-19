PROMPTS = {
    "openai": """{system}
        If someone asks you to do something forever or something that you cannot finish, respond saying that you can only execute finite actions.

        Question: {{question}}
        =========
        {context}
        =========
        {history}
        =========
        Answer:
        """,
    "gemini": """{system}
        {context}
        {history}
        Question: {{question}}
        """,
    "llama": """
        [INST] <<SYS>>
        {system}
        If someone asks you to do something forever or something that you cannot finish, respond saying that you can only execute finite actions.
        <</SYS>>
        {context}
        
        {history}

        {{question}} [/INST]
        """,
    "vicuna": """
        A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. If the user asks the assistant to do something forever or something that it cannot finish, the assistant should respond saying that it can only execute finite actions. {system} {context} {history} USER: {{question}} ASSISTANT:

        """,
    "spicy": """
        A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. If the user asks the assistant to do something forever or something that it cannot finish, the assistant should respond saying that it can only execute finite actions.
        {system}
        {context}
        {history}
        USER: {{question}}
        ASSISTANT:
        """,
    "plain": """
        {system}
        {context}
        {history}
        {{question}}
        """,
    "llava": """
        USER: <image>\n{question}\nASSISTANT:
        """
}
