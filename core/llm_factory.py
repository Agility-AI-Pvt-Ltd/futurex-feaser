from langchain_openai import ChatOpenAI
from core.config import settings

def get_llm(model: str = "gpt-4o-mini", temperature: float = 0.7) -> ChatOpenAI:
    """
    Factory function to initialize and return the language model.
    """
    return ChatOpenAI(
        model=model,
        openai_api_key=settings.OPENAI_API_KEY,
        temperature=temperature,
    )
