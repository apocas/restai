class Model:
    def __init__(
            self,
            model_name,
            llm,
            prompt,
            privacy,
            model=None,
            tokenizer=None,
            pipe=None,
            type=None):
        self.model_name = model_name
        self.llm = llm
        self.prompt = prompt
        self.privacy = privacy
        self.model = model
        self.tokenizer = tokenizer
        self.pipe = pipe
        self.type = type

    def __str__(self):
        return self.model_name

    def __repr__(self):
        return self.model_name

    def __eq__(self, other):
        return self.model_name == other.model_name

    def __hash__(self):
        return hash(self.model_name)
