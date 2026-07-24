"""Factory del modelo de chat (Gemini) usado por los nodos del grafo."""

from langchain_google_genai import ChatGoogleGenerativeAI

from expense_agent.core.config import Settings


def get_chat_model(settings: Settings, temperature: float = 0.0) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.gemini_api_key,
        temperature=temperature,
    )
