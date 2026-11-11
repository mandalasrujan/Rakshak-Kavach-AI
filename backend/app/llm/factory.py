from app.core.config import LLMSettings
from app.llm.base import LLMNotConfiguredError, LLMProvider
from app.llm.fake import FakeLLMProvider
from app.llm.gemini import GeminiProvider


def create_llm_provider(settings: LLMSettings) -> LLMProvider:
    if settings.llm_provider == "fake":
        return FakeLLMProvider()
    if not (
        settings.gemini_api_key and settings.gemini_chat_model and settings.gemini_embedding_model
    ):
        raise LLMNotConfiguredError(
            "set GEMINI_API_KEY, GEMINI_CHAT_MODEL and GEMINI_EMBEDDING_MODEL"
        )
    return GeminiProvider(
        api_key=settings.gemini_api_key.get_secret_value(),
        chat_model=settings.gemini_chat_model,
        embedding_model=settings.gemini_embedding_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )
