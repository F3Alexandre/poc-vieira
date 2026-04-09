"""
Gerenciamento de contexto — controla o tamanho do contexto do agente.

Inspirado no Claude Code:
- Working Memory File: estado persistente em arquivo
- Compactação de turnos antigos: mantém só decisões, remove idas e vindas
- Descarte de resultados de busca processados: após extrair informações úteis,
  os chunks brutos podem sair do contexto
"""

import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

# Estimativa: 1 token ≈ 4 caracteres em português
CHARS_PER_TOKEN = 4

# Limite antes de compactar (80% da janela para deixar espaço para resposta)
# Para Claude Sonnet: ~160K tokens úteis de contexto
# Para GPT-4o: ~100K tokens úteis
DEFAULT_CONTEXT_LIMIT_TOKENS = 80_000


def estimate_tokens(text: str) -> int:
    """Estimativa grosseira de tokens."""
    return len(text) // CHARS_PER_TOKEN


def estimate_messages_tokens(messages: List[Dict]) -> int:
    """Estima tokens totais de uma lista de mensagens."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    total += estimate_tokens(part["text"])
    return total


def should_compact(
    messages: List[Dict],
    limit_tokens: int = DEFAULT_CONTEXT_LIMIT_TOKENS,
) -> bool:
    """Verifica se o contexto precisa ser compactado."""
    current = estimate_messages_tokens(messages)
    return current > limit_tokens


def compact_history(
    messages: List[Dict],
    working_memory_summary: str,
    keep_last_n: int = 10,
) -> List[Dict]:
    """Compacta o histórico de conversa.

    Mantém os últimos N turnos intactos e substitui os anteriores
    por um resumo baseado no Working Memory.

    Args:
        messages: Lista completa de mensagens.
        working_memory_summary: Resumo compacto do Working Memory.
        keep_last_n: Quantos turnos recentes manter.

    Returns:
        Lista compactada de mensagens.
    """
    if len(messages) <= keep_last_n:
        return messages

    recent = messages[-keep_last_n:]

    # O resumo do Working Memory substitui todo o histórico antigo
    compacted = [
        {
            "role": "user",
            "content": (
                "[CONTEXTO COMPACTADO — turnos antigos foram resumidos]\n\n"
                f"{working_memory_summary}\n\n"
                "[A conversa continua abaixo com os turnos mais recentes]"
            ),
        },
        {
            "role": "assistant",
            "content": "Entendido. Continuando a especificação com base no estado atual.",
        },
    ]

    compacted.extend(recent)

    old_tokens = estimate_messages_tokens(messages)
    new_tokens = estimate_messages_tokens(compacted)
    logger.info(
        f"Contexto compactado: {old_tokens} → {new_tokens} tokens "
        f"({len(messages)} → {len(compacted)} mensagens)"
    )

    return compacted


def format_search_results_for_context(results: List[Dict]) -> str:
    """Formata resultados de busca para injeção no contexto.

    Não injeta o conteúdo completo dos chunks — apenas título, tipo,
    confiança e um resumo do conteúdo. O agente pode buscar detalhes
    de chunks específicos se precisar.
    """
    if not results:
        return "Nenhum resultado encontrado na base de conhecimento."

    lines = [f"**Encontrados {len(results)} chunks na base:**\n"]
    for i, r in enumerate(results, 1):
        content_preview = r.get("content", "")[:200]
        if len(r.get("content", "")) > 200:
            content_preview += "..."
        lines.append(
            f"{i}. **[{r.get('chunk_type', '?')}]** {r.get('title', 'Sem título')} "
            f"(confiança: {r.get('confidence', '?')})"
        )
        lines.append(f"   {content_preview}")
        lines.append("")

    return "\n".join(lines)
