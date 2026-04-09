"""
Client LLM abstrato — permite trocar entre providers sem mudar o pipeline.

Uso:
    client = create_llm_client("anthropic", model="claude-haiku-4-5-20251001")
    response = await client.generate(system="...", user="...")
"""

import os
import logging
from typing import Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class LLMClient(ABC):
    """Interface abstrata para clients LLM."""

    @abstractmethod
    async def generate(
        self,
        system: str,
        user: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> str:
        """Gera resposta do LLM.

        Args:
            system: System prompt.
            user: User message.
            temperature: 0.0 para determinismo (classificação), 0.7 para criatividade.
            max_tokens: Limite de tokens na resposta.

        Returns:
            Texto da resposta do LLM.
        """
        pass


class AnthropicClient(LLMClient):
    """Client para API da Anthropic (Claude)."""

    def __init__(self, model: str = "claude-haiku-4-5-20251001"):
        try:
            from anthropic import AsyncAnthropic
        except ImportError:
            raise ImportError("Instale o client: pip install anthropic")

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY não configurada")

        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model

    async def generate(
        self,
        system: str,
        user: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> str:
        logger.debug(f"Chamando Anthropic {self.model} ({len(user)} chars input)")

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )

        text = response.content[0].text
        logger.debug(f"Resposta Anthropic: {len(text)} chars")
        return text


class OpenAIClient(LLMClient):
    """Client para Azure OpenAI ou OpenAI direta."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        azure_endpoint: Optional[str] = None,
        api_version: str = "2024-10-21",
    ):
        try:
            from openai import AsyncOpenAI, AsyncAzureOpenAI
        except ImportError:
            raise ImportError("Instale o client: pip install openai")

        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("AZURE_OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY ou AZURE_OPENAI_API_KEY não configurada")

        if azure_endpoint:
            self.client = AsyncAzureOpenAI(
                api_key=api_key,
                azure_endpoint=azure_endpoint,
                api_version=api_version,
            )
        else:
            self.client = AsyncOpenAI(api_key=api_key)

        self.model = model

    async def generate(
        self,
        system: str,
        user: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> str:
        logger.debug(f"Chamando OpenAI {self.model} ({len(user)} chars input)")

        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )

        text = response.choices[0].message.content
        logger.debug(f"Resposta OpenAI: {len(text)} chars")
        return text


def create_llm_client(
    provider: str = "anthropic",
    model: Optional[str] = None,
    **kwargs,
) -> LLMClient:
    """Factory para criar o client LLM.

    Args:
        provider: "anthropic" ou "openai" ou "azure_openai"
        model: Nome do modelo. Se None, usa o default do provider.
        **kwargs: Argumentos adicionais (azure_endpoint, etc.)
    """
    if provider == "anthropic":
        return AnthropicClient(model=model or "claude-haiku-4-5-20251001")
    elif provider == "openai":
        return OpenAIClient(model=model or "gpt-4o-mini", **kwargs)
    elif provider == "azure_openai":
        return OpenAIClient(
            model=model or "gpt-4o-mini",
            azure_endpoint=kwargs.get("azure_endpoint") or os.environ.get("AZURE_OPENAI_ENDPOINT"),
            **{k: v for k, v in kwargs.items() if k != "azure_endpoint"},
        )
    else:
        raise ValueError(f"Provider desconhecido: {provider}. Válidos: anthropic, openai, azure_openai")
