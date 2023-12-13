PROMPTS = {
    "chatml": """{system}
        Confine your answer within the given context and do not generate the next context. Answer truthful answers, don't try to make up an answer.
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
    
        Question: {{question}}
        {context}
        {history}
        """,
    "llama": """
        [INST] <<SYS>>
        {system}
        Use the following information (context) to answer the question at the end. Answer truthful answers, don't try to make up an answer. Confine to the given context.
        If someone asks you to do something forever or something that you cannot finish, respond saying that you can only execute finite actions.
        <</SYS>>
        {context}
        
        {history}

        {{question}} [/INST]
        """,
    "vicuna": """
        A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. If the user asks the assistant to do something forever or something that it cannot finish, the assistant should respond saying that it can only execute finite actions. The assistant should use the following information (context) to answer the question. {system} {context} {history} USER: {{question}} ASSISTANT:

        """,
    "spicy": """
        A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. If the user asks the assistant to do something forever or something that it cannot finish, the assistant should respond saying that it can only execute finite actions. The assistant should use the following information (context) to answer the question.
        {system}
        {context} 
        {history}
        USER: {{question}}
        ASSISTANT:
        """
}
