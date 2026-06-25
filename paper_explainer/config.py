import os
from dotenv import load_dotenv


load_dotenv()


def build_llm():
    """
    Build the LLM client.

    Important:
    The page-by-page explanation step sends images to the model.
    Therefore, your model must support vision input.

    Examples:
    - OpenAI: gpt-4o, gpt-4.1, gpt-4o-mini
    - Other providers: make sure the model accepts image_url input
    """

    provider = os.getenv("LLM_PROVIDER", "openai").lower().strip()

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        model_name = os.getenv("OPENAI_MODEL", "gpt-4o")

        return ChatOpenAI(
            model=model_name,
            temperature=0.2,
        )

    if provider == "cerebras":
        from langchain_cerebras import ChatCerebras

        api_key = os.getenv("CEREBRAS_API_KEY")
        model_name = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b")

        if not api_key:
            raise ValueError("CEREBRAS_API_KEY is missing from your .env file.")

        return ChatCerebras(
            model=model_name,
            api_key=api_key,
            temperature=0.2,
        )

    raise ValueError(
        f"Unsupported LLM_PROVIDER: {provider}. "
        "Use either 'openai' or 'cerebras'."
    )


MyLLM = build_llm()
