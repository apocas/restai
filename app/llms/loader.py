def localLoader(type, model, temperature=0.0001):
    if type == "gptq":
        return loadTransformers(model, temperature)
    else:
        raise Exception("Invalid LLM type.")


def loadTransformers(modelName, temp):
    from langchain.llms.huggingface_pipeline import HuggingFacePipeline
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline, logging

    model = AutoModelForCausalLM.from_pretrained(
        modelName, device_map="auto", trust_remote_code=False, revision="main")

    # logging.set_verbosity(logging.CRITICAL)

    tokenizer = AutoTokenizer.from_pretrained(modelName, use_fast=True)

    pipe = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        return_full_text=False,
        max_new_tokens=512,
        do_sample=True,
        temperature=temp or 0.0001,
        top_p=0.95,
        top_k=40,
        repetition_penalty=1.15
    )

    return HuggingFacePipeline(pipeline=pipe), model, tokenizer, pipe
