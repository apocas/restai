class LLM:
    def __init__(self, model_name, props, llm=None) -> None:
        self.model_name = model_name
        self.props = props
        self.llm = llm

    def __str__(self):
        return self.model_name

    def __repr__(self):
        return self.model_name

    def __eq__(self, other):
        return self.model_name == other.model_name

    def __hash__(self):
        return hash(self.model_name)
