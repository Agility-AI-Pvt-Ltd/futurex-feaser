from langchain_openai import ChatOpenAI
from core.config import settings

def get_llm(model: str | None = None, temperature: float = 0.7) -> ChatOpenAI:
    """
    Factory function to initialize and return the language model.
    """
    provider = settings.LLM_PROVIDER.strip().lower()

    if provider == "openrouter":
        return ChatOpenAI(
            model=model or settings.OPENROUTER_MODEL_NAME,
            openai_api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            temperature=temperature,
        )

    if provider != "openai":
        raise ValueError(f"Unsupported LLM_PROVIDER: {settings.LLM_PROVIDER}")

    return ChatOpenAI(
        model=model or "gpt-5.4-nano",
        openai_api_key=settings.OPENAI_API_KEY,
        temperature=temperature,
    )
