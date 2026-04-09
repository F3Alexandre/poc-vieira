"""
Chunker — segmenta e classifica texto bruto em chunks de conhecimento.

O LLM recebe o texto completo de um documento e retorna um JSON array
com os chunks extraídos, cada um com metadados de classificação.

REGRA CRÍTICA: o LLM NÃO pode sumarizar. Ele reorganiza e classifica,
mas preserva 100% da informação original.
"""

import re
import json
import logging
from typing import List, Dict, Any

from src.knowledge.schema import CHUNK_TYPES, SOURCE_TYPES, DOMAINS

logger = logging.getLogger(__name__)


CHUNKER_SYSTEM_PROMPT = """Você é um archivista especializado em documentação de produto de software.
Sua tarefa é receber um texto bruto (transcrição de reunião, documento de produto, mensagens de chat, documento de cliente) e segmentá-lo em unidades lógicas de conhecimento.

## REGRAS CRÍTICAS — LEIA COM ATENÇÃO

1. **NUNCA sumarize.** NUNCA remova informação. NUNCA simplifique. Você reorganiza para clareza e classifica, mas preserva TODO o conteúdo original. Se o texto original diz "prazo de 30 dias corridos a partir da data de entrega confirmada", seu chunk deve conter essa frase completa, não "prazo de 30 dias".

2. **Preserve ambiguidades.** Se o texto é ambíguo ou contraditório, NÃO resolva a ambiguidade. Preserve-a e marque explicitamente:
   - Para ambiguidades: adicione "[AMBIGUIDADE: descrição]" no conteúdo do chunk
   - Para contradições internas: adicione "[CONTRADIÇÃO: descrição]" no conteúdo do chunk
   - Para decisões pendentes: adicione "[PENDÊNCIA: descrição]" no conteúdo do chunk

3. **Cada chunk deve ser auto-contido.** Alguém deve conseguir entender o chunk sem ler o documento original. Se uma regra de negócio depende de contexto mencionado em outro trecho, inclua esse contexto no chunk.

4. **Um chunk = uma unidade lógica.** Se uma reunião discutiu 4 regras de negócio e 2 decisões técnicas, gere 6 chunks (um por unidade). NÃO agrupe tudo em um único chunk gigante. NÃO separe uma regra de negócio em dois chunks se ela é uma unidade lógica.

5. **Granularidade:** cada chunk deve ter entre 100-600 palavras. Se um bloco lógico é menor que 100 palavras, considere se ele é realmente uma unidade independente ou se deveria ser parte de outro chunk. Se excede 600 palavras, provavelmente são duas unidades distintas.

6. **Tags devem incluir sinônimos.** Se o texto menciona "devolução", as tags devem incluir também "estorno", "reversão", "return". Se menciona "PJ", incluir "empresa", "corporativo", "B2B". Isso é CRÍTICO para a busca lexical funcionar.

## CLASSIFICAÇÃO

Para cada chunk, classifique com:

### chunk_type (OBRIGATÓRIO — escolha EXATAMENTE UM):
- `regra_negocio` — lógica de negócio, condições, exceções, limites, regras de validação
- `fluxo_usuario` — passo-a-passo de interação do usuário com o sistema
- `decisao_tecnica` — escolhas de arquitetura, stack, padrões, endpoints, protocolos
- `requisito_nao_funcional` — performance, segurança, acessibilidade, disponibilidade, retenção
- `definicao_escopo` — o que está dentro e fora do escopo da feature
- `restricao` — limitações conhecidas, débitos técnicos, gargalos, rate limits
- `criterio_aceite` — condições de aceite já definidas ou discutidas
- `integracao` — pontos de contato com outros sistemas, APIs, webhooks, filas
- `vocabulario` — definições de termos do domínio, glossário
- `contexto_negocio` — background, motivação, justificativa de negócio, métricas, impacto

### domain (OBRIGATÓRIO — escolha EXATAMENTE UM):
- `financeiro` — pagamentos, estornos, faturamento, custos
- `logistica` — envio, entrega, coleta, rastreio, etiquetas
- `pos_venda` — devoluções, trocas, suporte, reclamações, NPS
- `cadastro` — usuários, contas, perfis, contratos
- `autenticacao` — login, SSO, permissões, tokens
- `integracao` — APIs externas, webhooks, mensageria, filas
- `relatorios` — dashboards, métricas, analytics, exports

### confidence (OBRIGATÓRIO):
- `high` — informação de documento formal (PRD, contrato, ata aprovada, spec técnica)
- `medium` — informação de decisão verbal em reunião gravada ou grooming formal
- `low` — menção informal em chat, sugestão sem confirmação, opinião individual

### feature (OBRIGATÓRIO):
- Identificador snake_case da funcionalidade. Ex: `devolucao_produtos`, `checkout_pagamento`
- Se o documento discute mais de uma feature, crie chunks separados para cada

## FORMATO DE SAÍDA

Responda APENAS com um JSON array. Sem texto antes ou depois. Sem markdown code fences.
Sem explicações. APENAS o JSON puro.

Cada elemento do array deve ter EXATAMENTE esta estrutura:
{
  "title": "Título descritivo (max 100 chars)",
  "content": "Texto completo do chunk, preservando toda a informação original...",
  "chunk_type": "regra_negocio",
  "feature": "devolucao_produtos",
  "domain": "pos_venda",
  "confidence": "high",
  "tags": ["devolucao", "estorno", "prazo", "pessoa_fisica"],
  "participants": ["ana_po", "carlos_arq"],
  "related_features": ["garantia", "checkout_pagamento"]
}

Os campos participants e related_features podem ser arrays vazios se não aplicável."""


def build_chunker_user_prompt(
    raw_text: str,
    source_ref: str,
    source_type: str,
) -> str:
    """Constrói o user prompt para o chunker.

    Inclui o texto bruto e metadados de contexto para o LLM.
    """
    return f"""Arquivo fonte: {source_ref}
Tipo de fonte: {source_type}
Classificação esperada de confidence baseada no tipo de fonte: {_confidence_hint(source_type)}

Texto bruto a segmentar e classificar:
---
{raw_text}
---

Segmente este texto em chunks de conhecimento seguindo TODAS as regras do system prompt.
Retorne APENAS um JSON array válido."""


def _confidence_hint(source_type: str) -> str:
    """Dica de confiança baseada no tipo de fonte."""
    hints = {
        "transcricao_reuniao": "medium (decisões verbais em reunião)",
        "documento_produto": "high (documento formal de produto)",
        "documento_cliente": "high (documento contratual/formal do cliente)",
        "chat": "low (conversa informal, menções sem confirmação)",
        "card_devops": "high (card aprovado/formalizado)",
        "documentacao_tecnica": "high (documentação técnica formal)",
        "decisao_registro": "high (ata de reunião com decisões registradas)",
    }
    return hints.get(source_type, "medium")


async def chunk_and_classify(
    raw_text: str,
    source_ref: str,
    source_type: str,
    llm_client,
) -> List[Dict[str, Any]]:
    """Envia texto para o LLM e retorna chunks classificados.

    Inclui parsing robusto do JSON (o LLM pode retornar com code fences
    ou texto extra) e validação dos campos.

    Args:
        raw_text: Texto bruto extraído do arquivo.
        source_ref: Caminho do arquivo original (para referência).
        source_type: Tipo da fonte (transcricao_reuniao, documento_produto, etc.).
        llm_client: Client LLM (Anthropic ou OpenAI).

    Returns:
        Lista de dicts, cada um representando um chunk classificado.

    Raises:
        ValueError: Se o LLM retornar resposta não-parseável após retries.
    """
    system = CHUNKER_SYSTEM_PROMPT
    user = build_chunker_user_prompt(raw_text, source_ref, source_type)

    # Tentar até 2 vezes (1 tentativa + 1 retry)
    last_error = None
    for attempt in range(2):
        try:
            response = await llm_client.generate(
                system=system,
                user=user if attempt == 0 else user + "\n\nATENÇÃO: sua resposta anterior não era um JSON válido. Retorne APENAS o JSON array, sem markdown, sem explicações.",
                temperature=0.0,  # Determinismo para classificação
                max_tokens=4096,
            )

            chunks = _parse_llm_response(response)
            _validate_chunks(chunks, source_ref)

            logger.info(
                f"Chunking concluído: {source_ref} → "
                f"{len(chunks)} chunks (tentativa {attempt + 1})"
            )
            return chunks

        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            logger.warning(
                f"Tentativa {attempt + 1} falhou para {source_ref}: {e}. "
                f"{'Retrying...' if attempt == 0 else 'Desistindo.'}"
            )

    raise ValueError(
        f"Falha ao processar {source_ref} após 2 tentativas. "
        f"Último erro: {last_error}"
    )


def _parse_llm_response(response: str) -> List[Dict]:
    """Parse robusto da resposta do LLM.

    O LLM pode retornar:
    - JSON puro (ideal)
    - JSON dentro de ```json ... ``` (comum)
    - JSON com texto antes/depois (raro)
    - JSON com trailing commas (raro)
    """
    text = response.strip()

    # 1. Remover code fences se presentes
    if "```" in text:
        # Extrair conteúdo entre code fences
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()

    # 2. Encontrar o array JSON (pode ter texto antes/depois)
    # Buscar o primeiro '[' e o último ']'
    start = text.find('[')
    end = text.rfind(']')

    if start == -1 or end == -1 or end <= start:
        raise json.JSONDecodeError(
            f"Não encontrado JSON array na resposta. Início: {text[:200]}",
            text, 0
        )

    json_str = text[start:end + 1]

    # 3. Remover trailing commas (LLMs às vezes geram isso)
    json_str = re.sub(r",\s*([}\]])", r"\1", json_str)

    # 4. Parse
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"JSON inválido: {e.msg}. Primeiros 500 chars: {json_str[:500]}",
            json_str, e.pos
        )

    if not isinstance(data, list):
        raise ValueError(f"Esperado JSON array, recebido {type(data).__name__}")

    if len(data) == 0:
        raise ValueError("JSON array vazio — nenhum chunk extraído")

    return data


def _validate_chunks(chunks: List[Dict], source_ref: str) -> None:
    """Valida os chunks retornados pelo LLM.

    Verifica campos obrigatórios, valores de enum, e tamanho.
    Corrige problemas menores automaticamente (normalização).
    Levanta ValueError para problemas graves.
    """
    required_fields = ["title", "content", "chunk_type", "feature", "domain", "confidence"]

    for i, chunk in enumerate(chunks):
        # Verificar campos obrigatórios
        for field in required_fields:
            if field not in chunk or not chunk[field]:
                raise ValueError(
                    f"Chunk {i} de {source_ref}: campo '{field}' ausente ou vazio. "
                    f"Title: {chunk.get('title', 'SEM TÍTULO')}"
                )

        # Validar enums
        if chunk["chunk_type"] not in CHUNK_TYPES:
            logger.warning(
                f"Chunk {i}: chunk_type '{chunk['chunk_type']}' inválido. "
                f"Tentando mapear..."
            )
            mapped = _try_map_chunk_type(chunk["chunk_type"])
            if mapped:
                chunk["chunk_type"] = mapped
            else:
                raise ValueError(
                    f"Chunk {i}: chunk_type '{chunk['chunk_type']}' não mapeável. "
                    f"Válidos: {CHUNK_TYPES}"
                )

        if chunk["confidence"] not in ["high", "medium", "low"]:
            chunk["confidence"] = "medium"  # Fallback seguro

        if chunk["domain"] not in DOMAINS:
            logger.warning(
                f"Chunk {i}: domain '{chunk['domain']}' inválido. "
                f"Usando 'pos_venda' como fallback."
            )
            chunk["domain"] = "pos_venda"

        # Normalizar feature para snake_case
        chunk["feature"] = chunk["feature"].lower().replace(" ", "_").replace("-", "_")

        # Garantir que tags, participants, related_features são listas
        for list_field in ["tags", "participants", "related_features"]:
            if list_field not in chunk or not isinstance(chunk[list_field], list):
                chunk[list_field] = []

        # Truncar título se necessário
        if len(chunk["title"]) > 200:
            chunk["title"] = chunk["title"][:197] + "..."

        # Verificar tamanho do conteúdo
        word_count = len(chunk["content"].split())
        if word_count < 20:
            logger.warning(
                f"Chunk {i} '{chunk['title']}': conteúdo muito curto "
                f"({word_count} palavras). Pode ser insuficiente para busca."
            )


def _try_map_chunk_type(invalid_type: str) -> str:
    """Tenta mapear um chunk_type inválido para um válido.

    LLMs às vezes inventam tipos próximos dos válidos.
    """
    mappings = {
        "regra_de_negocio": "regra_negocio",
        "regras_negocio": "regra_negocio",
        "business_rule": "regra_negocio",
        "fluxo_de_usuario": "fluxo_usuario",
        "user_flow": "fluxo_usuario",
        "decisao_tecnica_arquitetura": "decisao_tecnica",
        "technical_decision": "decisao_tecnica",
        "requisito_nao_funcional_performance": "requisito_nao_funcional",
        "nfr": "requisito_nao_funcional",
        "escopo": "definicao_escopo",
        "fora_do_escopo": "definicao_escopo",
        "scope": "definicao_escopo",
        "limitacao": "restricao",
        "constraint": "restricao",
        "integration": "integracao",
        "contexto": "contexto_negocio",
        "background": "contexto_negocio",
        "motivacao": "contexto_negocio",
        "glossario": "vocabulario",
        "definicao": "vocabulario",
        "acceptance_criteria": "criterio_aceite",
    }

    normalized = invalid_type.lower().strip()
    return mappings.get(normalized)
