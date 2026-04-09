# SPEC — Etapa 3: Pipeline de Ingestão (Bronze → Silver)

## Objetivo

Implementar o pipeline que transforma dados brutos da camada Bronze (transcrições, documentos, chats) em chunks classificados e enriquecidos na camada Silver. O pipeline opera em 3 estágios: extração de texto, chunking + classificação via LLM, e inserção na Silver com validação.

Este é o componente mais sensível do sistema: a qualidade dos chunks determina diretamente a qualidade das buscas do agente e, por consequência, dos cards gerados. O principal risco é **perda de informação** durante o chunking — o LLM pode sumarizar ou descartar detalhes que parecem irrelevantes mas são cruciais para regras de negócio.

## Dependências

- **Etapa 1 concluída** — dados bronze existem em `data/bronze/`
- **Etapa 2 concluída** — schema Silver funcional, `src/knowledge/schema.py` importável
- **Acesso a API de LLM** — Anthropic (Claude) ou Azure OpenAI
- **Bibliotecas Python:**
  - `anthropic` (se usando Claude) OU `openai` (se usando Azure OpenAI)
  - Nenhuma outra dependência externa

```bash
# Instalar apenas o client do LLM que será usado
pip install anthropic
# OU
pip install openai
```

## Estrutura de arquivos

```
src/
└── ingestion/
    ├── __init__.py
    ├── extractor.py         # Extração de texto por MIME type
    ├── chunker.py           # Chunking + classificação via LLM (prompts + parsing)
    ├── pipeline.py          # Orquestrador do pipeline completo
    └── llm_client.py        # Abstração do client LLM (Anthropic ou OpenAI)
scripts/
├── run_ingestion.py         # Script CLI para rodar o pipeline
└── seed_bronze.py           # (da Etapa 1) Gera dados simulados
tests/
└── test_ingestion.py        # Testes do pipeline
```

---

## Parte 1: Extrator de texto (`src/ingestion/extractor.py`)

Para o MVP, suportamos apenas `.md` e `.txt`. A arquitetura prevê extensão para PDF, DOCX e imagens.

```python
"""
Extrator de texto — converte arquivos brutos em texto plano.

MVP: suporta .md e .txt (leitura direta).
Futuro: adicionar PDF (pdf-parse/pymupdf), DOCX (python-docx), imagens (OCR via Tesseract).
"""

import os
from typing import Tuple

# Mapeamento de extensão → tipo de extração
SUPPORTED_EXTENSIONS = {
    ".md": "text",
    ".txt": "text",
    ".csv": "text",
    # Futuro:
    # ".pdf": "pdf",
    # ".docx": "docx",
    # ".png": "ocr",
    # ".jpg": "ocr",
}


def extract_text(file_path: str) -> Tuple[str, str]:
    """Extrai texto bruto de um arquivo.
    
    Args:
        file_path: Caminho do arquivo na Bronze.
        
    Returns:
        Tupla (texto_extraído, mime_type).
        
    Raises:
        ValueError: Se o tipo de arquivo não é suportado.
        FileNotFoundError: Se o arquivo não existe.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")
    
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Tipo de arquivo não suportado: {ext}. "
            f"Suportados: {list(SUPPORTED_EXTENSIONS.keys())}"
        )
    
    extraction_type = SUPPORTED_EXTENSIONS[ext]
    
    if extraction_type == "text":
        return _extract_text_file(file_path), f"text/{ext.lstrip('.')}"
    
    # Futuro: outros tipos
    raise ValueError(f"Extração do tipo '{extraction_type}' não implementada")


def _extract_text_file(file_path: str) -> str:
    """Lê arquivo de texto plano com detecção de encoding."""
    encodings = ["utf-8", "latin-1", "cp1252"]
    
    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                content = f.read()
            return content.strip()
        except UnicodeDecodeError:
            continue
    
    raise ValueError(f"Não foi possível decodificar {file_path} com nenhum encoding suportado")


def get_source_type_from_path(file_path: str) -> str:
    """Infere o source_type baseado no diretório do arquivo.
    
    Mapeamento:
        data/bronze/calls/    → transcricao_reuniao
        data/bronze/docs/     → documento_produto
        data/bronze/chats/    → chat
        
    Para o MVP, os diretórios são fixos. Futuro: configurável.
    """
    # Normalizar path
    normalized = file_path.replace("\\", "/")
    
    if "/calls/" in normalized:
        return "transcricao_reuniao"
    elif "/chats/" in normalized:
        return "chat"
    elif "/docs/" in normalized:
        # Heurística: se contém "requisitos-cliente" ou "cliente" no nome, é doc do cliente
        basename = os.path.basename(normalized).lower()
        if "cliente" in basename or "enterprise" in basename or "contrato" in basename:
            return "documento_cliente"
        return "documento_produto"
    
    # Fallback
    return "documento_produto"
```

---

## Parte 2: Client LLM abstrato (`src/ingestion/llm_client.py`)

Abstração que permite trocar entre Anthropic e OpenAI sem mudar o resto do código.

```python
"""
Client LLM abstrato — permite trocar entre providers sem mudar o pipeline.

Uso:
    client = create_llm_client("anthropic", model="claude-haiku-4-5-20251001")
    response = await client.generate(system="...", user="...")
"""

import os
import json
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
```

---

## Parte 3: Chunker + Classificador via LLM (`src/ingestion/chunker.py`)

Este é o componente central do pipeline. O LLM recebe texto bruto e retorna chunks classificados.

### Prompts

```python
"""
Chunker — segmenta e classifica texto bruto em chunks de conhecimento.

O LLM recebe o texto completo de um documento e retorna um JSON array
com os chunks extraídos, cada um com metadados de classificação.

REGRA CRÍTICA: o LLM NÃO pode sumarizar. Ele reorganiza e classifica,
mas preserva 100% da informação original.
"""

import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Lista de chunk_types válidos — importada do schema para manter consistência
from src.knowledge.schema import CHUNK_TYPES, SOURCE_TYPES, DOMAINS


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
```

### Processamento da resposta do LLM

```python
import re


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
```

---

## Parte 4: Pipeline orquestrador (`src/ingestion/pipeline.py`)

```python
"""
Pipeline de ingestão — orquestra extração, chunking e inserção na Silver.

Uso:
    stats = await run_ingestion("data/bronze", "data/silver/knowledge.db", llm_client)
    print(f"Processados: {stats['files_processed']} arquivos, {stats['chunks_created']} chunks")
"""

import os
import uuid
import json
import logging
import asyncio
from typing import Dict, Any, List
from datetime import datetime, timezone

from src.ingestion.extractor import extract_text, get_source_type_from_path, SUPPORTED_EXTENSIONS
from src.ingestion.chunker import chunk_and_classify
from src.knowledge.schema import Chunk, init_db, insert_chunk, insert_chunks_batch, get_db_stats

logger = logging.getLogger(__name__)


async def run_ingestion(
    bronze_dir: str,
    db_path: str,
    llm_client,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Executa o pipeline completo de ingestão Bronze → Silver.
    
    Percorre todos os arquivos suportados em bronze_dir,
    extrai texto, chunka via LLM, classifica e insere na Silver.
    
    Args:
        bronze_dir: Diretório raiz da Bronze (ex: "data/bronze").
        db_path: Caminho do banco Silver (ex: "data/silver/knowledge.db").
        llm_client: Client LLM para chunking.
        dry_run: Se True, processa mas não insere no banco (para debug).
        
    Returns:
        Dict com estatísticas:
        {
            "files_processed": int,
            "files_skipped": int,
            "chunks_created": int,
            "chunks_by_type": {chunk_type: count},
            "chunks_by_source": {source_type: count},
            "errors": [{"file": str, "error": str}],
            "duration_seconds": float,
        }
    """
    start_time = datetime.now(timezone.utc)
    
    stats = {
        "files_processed": 0,
        "files_skipped": 0,
        "chunks_created": 0,
        "chunks_by_type": {},
        "chunks_by_source": {},
        "errors": [],
        "duration_seconds": 0.0,
    }
    
    # Inicializar banco
    if not dry_run:
        conn = init_db(db_path)
    
    # Descobrir todos os arquivos suportados
    files = _discover_files(bronze_dir)
    logger.info(f"Encontrados {len(files)} arquivos para processar em {bronze_dir}")
    
    if not files:
        logger.warning(f"Nenhum arquivo suportado encontrado em {bronze_dir}")
        return stats
    
    # Processar cada arquivo
    for file_path in files:
        logger.info(f"Processando: {file_path}")
        
        try:
            # Etapa 1: Extração de texto
            raw_text, mime_type = extract_text(file_path)
            
            if len(raw_text.strip()) < 50:
                logger.warning(f"Arquivo muito curto, pulando: {file_path} ({len(raw_text)} chars)")
                stats["files_skipped"] += 1
                continue
            
            # Inferir source_type
            source_type = get_source_type_from_path(file_path)
            
            # Etapa 2+3: Chunking + Classificação via LLM
            chunks_data = await chunk_and_classify(
                raw_text=raw_text,
                source_ref=file_path,
                source_type=source_type,
                llm_client=llm_client,
            )
            
            logger.info(f"  → {len(chunks_data)} chunks extraídos de {os.path.basename(file_path)}")
            
            # Etapa 4: Conversão para Chunk e inserção na Silver
            chunks_to_insert = []
            for chunk_data in chunks_data:
                chunk = Chunk(
                    id=str(uuid.uuid4()),
                    title=chunk_data["title"],
                    content=chunk_data["content"],
                    feature=chunk_data["feature"],
                    domain=chunk_data["domain"],
                    chunk_type=chunk_data["chunk_type"],
                    source_type=source_type,
                    source_ref=file_path,
                    confidence=chunk_data.get("confidence", "medium"),
                    tags=chunk_data.get("tags", []),
                    participants=chunk_data.get("participants", []),
                    related_features=chunk_data.get("related_features", []),
                )
                
                # Validar chunk
                errors = chunk.validate()
                if errors:
                    logger.warning(
                        f"  Chunk '{chunk.title}' tem erros de validação: {errors}. "
                        f"Pulando."
                    )
                    continue
                
                chunks_to_insert.append(chunk)
                
                # Atualizar contadores
                ct = chunk.chunk_type
                stats["chunks_by_type"][ct] = stats["chunks_by_type"].get(ct, 0) + 1
                st = chunk.source_type
                stats["chunks_by_source"][st] = stats["chunks_by_source"].get(st, 0) + 1
            
            # Inserir em lote
            if not dry_run and chunks_to_insert:
                insert_chunks_batch(conn, chunks_to_insert)
            
            stats["chunks_created"] += len(chunks_to_insert)
            stats["files_processed"] += 1
            
        except Exception as e:
            logger.error(f"Erro ao processar {file_path}: {e}")
            stats["errors"].append({
                "file": file_path,
                "error": str(e),
            })
    
    # Fechar banco
    if not dry_run:
        conn.close()
    
    # Calcular duração
    end_time = datetime.now(timezone.utc)
    stats["duration_seconds"] = (end_time - start_time).total_seconds()
    
    # Log resumo
    logger.info(
        f"Pipeline concluído em {stats['duration_seconds']:.1f}s: "
        f"{stats['files_processed']} arquivos processados, "
        f"{stats['chunks_created']} chunks criados, "
        f"{len(stats['errors'])} erros"
    )
    
    return stats


def _discover_files(bronze_dir: str) -> List[str]:
    """Descobre todos os arquivos suportados recursivamente no diretório bronze."""
    files = []
    
    for root, dirs, filenames in os.walk(bronze_dir):
        # Ignorar diretórios ocultos
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        
        for filename in sorted(filenames):
            ext = os.path.splitext(filename)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                files.append(os.path.join(root, filename))
    
    return files
```

---

## Parte 5: Script CLI (`scripts/run_ingestion.py`)

```python
#!/usr/bin/env python3
"""
Script para rodar o pipeline de ingestão via linha de comando.

Uso:
    python scripts/run_ingestion.py
    python scripts/run_ingestion.py --dry-run
    python scripts/run_ingestion.py --provider openai --model gpt-4o-mini
    python scripts/run_ingestion.py --bronze-dir data/bronze --db-path data/silver/knowledge.db
"""

import os
import sys
import asyncio
import argparse
import logging
import json

# Adicionar raiz do projeto ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ingestion.pipeline import run_ingestion
from src.ingestion.llm_client import create_llm_client
from src.knowledge.schema import init_db, get_db_stats


def parse_args():
    parser = argparse.ArgumentParser(description="Pipeline de ingestão Bronze → Silver")
    parser.add_argument("--bronze-dir", default="data/bronze", help="Diretório Bronze")
    parser.add_argument("--db-path", default="data/silver/knowledge.db", help="Caminho do banco Silver")
    parser.add_argument("--provider", default="anthropic", choices=["anthropic", "openai", "azure_openai"])
    parser.add_argument("--model", default=None, help="Modelo LLM (default depende do provider)")
    parser.add_argument("--dry-run", action="store_true", help="Processar sem inserir no banco")
    parser.add_argument("--verbose", action="store_true", help="Log detalhado")
    return parser.parse_args()


async def main():
    args = parse_args()
    
    # Configurar logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    
    logger = logging.getLogger("ingestion")
    
    # Verificar que bronze existe
    if not os.path.exists(args.bronze_dir):
        logger.error(f"Diretório bronze não encontrado: {args.bronze_dir}")
        logger.error("Execute a Etapa 1 primeiro (scripts/seed_bronze.py)")
        sys.exit(1)
    
    # Criar LLM client
    try:
        llm_client = create_llm_client(
            provider=args.provider,
            model=args.model,
        )
        logger.info(f"LLM client criado: {args.provider} ({args.model or 'default'})")
    except (ImportError, ValueError) as e:
        logger.error(f"Erro ao criar LLM client: {e}")
        sys.exit(1)
    
    # Rodar pipeline
    logger.info(f"{'[DRY RUN] ' if args.dry_run else ''}Iniciando ingestão...")
    logger.info(f"  Bronze: {args.bronze_dir}")
    logger.info(f"  Silver: {args.db_path}")
    
    stats = await run_ingestion(
        bronze_dir=args.bronze_dir,
        db_path=args.db_path,
        llm_client=llm_client,
        dry_run=args.dry_run,
    )
    
    # Exibir resultados
    print("\n" + "=" * 60)
    print("RESULTADO DA INGESTÃO")
    print("=" * 60)
    print(f"Arquivos processados:  {stats['files_processed']}")
    print(f"Arquivos pulados:      {stats['files_skipped']}")
    print(f"Chunks criados:        {stats['chunks_created']}")
    print(f"Tempo total:           {stats['duration_seconds']:.1f}s")
    
    if stats["chunks_by_type"]:
        print("\nChunks por tipo:")
        for ct, count in sorted(stats["chunks_by_type"].items()):
            print(f"  {ct}: {count}")
    
    if stats["chunks_by_source"]:
        print("\nChunks por fonte:")
        for st, count in sorted(stats["chunks_by_source"].items()):
            print(f"  {st}: {count}")
    
    if stats["errors"]:
        print(f"\nERROS ({len(stats['errors'])}):")
        for err in stats["errors"]:
            print(f"  {err['file']}: {err['error']}")
    
    # Mostrar stats do banco (se não dry run)
    if not args.dry_run:
        print("\n" + "-" * 60)
        print("ESTADO DA BASE SILVER")
        print("-" * 60)
        conn = init_db(args.db_path)
        db_stats = get_db_stats(conn)
        conn.close()
        print(f"Total chunks:    {db_stats['total_chunks']}")
        print(f"Chunks ativos:   {db_stats['active_chunks']}")
        if db_stats["chunks_by_feature"]:
            print("Por feature:")
            for feat, count in db_stats["chunks_by_feature"].items():
                print(f"  {feat}: {count}")
    
    print("\n" + "=" * 60)
    
    # Exit code baseado em erros
    if stats["errors"]:
        logger.warning(f"{len(stats['errors'])} erros durante a ingestão")
        sys.exit(1 if stats["files_processed"] == 0 else 0)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Parte 6: Testes (`tests/test_ingestion.py`)

```python
"""
Testes do pipeline de ingestão.

Testa extração, parsing de resposta LLM, validação, e pipeline completo.
Usa um mock do LLM client para não depender de API externa nos testes.

Rodar: python tests/test_ingestion.py
Ou: python -m pytest tests/test_ingestion.py -v
"""

import os
import sys
import json
import asyncio
import tempfile
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.ingestion.extractor import extract_text, get_source_type_from_path
from src.ingestion.chunker import (
    _parse_llm_response,
    _validate_chunks,
    chunk_and_classify,
    CHUNKER_SYSTEM_PROMPT,
)
from src.ingestion.pipeline import run_ingestion, _discover_files
from src.knowledge.schema import init_db, get_db_stats


# === Mock LLM Client ===

class MockLLMClient:
    """LLM client falso que retorna chunks pré-definidos.
    
    Usado para testar o pipeline sem depender de API externa.
    """
    
    def __init__(self, response: str = None):
        self._response = response or self._default_response()
        self.call_count = 0
    
    async def generate(self, system: str, user: str, temperature: float = 0.0, max_tokens: int = 4096) -> str:
        self.call_count += 1
        return self._response
    
    def _default_response(self) -> str:
        """Resposta padrão simulando o chunking de uma transcrição."""
        return json.dumps([
            {
                "title": "Regra de prazo de devolução para PF",
                "content": "O prazo de devolução para pessoa física é de 30 dias corridos a partir da data de entrega do produto. Para PJ com contrato enterprise, o prazo é definido pelo contrato, podendo ser 60 ou 90 dias.",
                "chunk_type": "regra_negocio",
                "feature": "devolucao_produtos",
                "domain": "pos_venda",
                "confidence": "medium",
                "tags": ["devolucao", "prazo", "pessoa_fisica", "30_dias", "pj", "enterprise"],
                "participants": ["ana_po", "carlos_arq"],
                "related_features": []
            },
            {
                "title": "Decisão técnica: API assíncrona para estorno",
                "content": "Carlos sugere usar mensageria assíncrona (fila SQS) para o processo de estorno, para não bloquear o usuário aguardando resposta do gateway de pagamento. A chamada ao gateway XPay será desacoplada da requisição do cliente.",
                "chunk_type": "decisao_tecnica",
                "feature": "devolucao_produtos",
                "domain": "financeiro",
                "confidence": "medium",
                "tags": ["estorno", "api", "assincrono", "sqs", "gateway", "xpay"],
                "participants": ["carlos_arq"],
                "related_features": ["checkout_pagamento"]
            },
            {
                "title": "Fluxo principal de solicitação de devolução",
                "content": "1. Cliente acessa Meus Pedidos. 2. Seleciona o pedido. 3. Clica em Solicitar Devolução. 4. Escolhe motivo da devolução. 5. Confirma solicitação. 6. Recebe protocolo de acompanhamento. O fluxo foi discutido informalmente na reunião sem confirmação formal.",
                "chunk_type": "fluxo_usuario",
                "feature": "devolucao_produtos",
                "domain": "pos_venda",
                "confidence": "medium",
                "tags": ["fluxo", "devolucao", "meus_pedidos", "solicitacao"],
                "participants": ["ana_po", "pedro_dev"],
                "related_features": []
            },
        ], ensure_ascii=False)


# === Testes de extração ===

def test_extract_text_md():
    """Extrai texto de arquivo markdown."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8")
    tmp.write("# Título\n\nConteúdo com acentuação: devolução, estorno.")
    tmp.close()
    
    text, mime = extract_text(tmp.name)
    assert "devolução" in text
    assert "estorno" in text
    assert mime == "text/md"
    
    os.unlink(tmp.name)
    print("✓ test_extract_text_md")


def test_extract_text_file_not_found():
    """Extração falha com FileNotFoundError para arquivo inexistente."""
    try:
        extract_text("/tmp/nao_existe_xyz.md")
        assert False, "Deveria ter levantado FileNotFoundError"
    except FileNotFoundError:
        pass
    print("✓ test_extract_text_file_not_found")


def test_extract_text_unsupported():
    """Extração falha com ValueError para tipo não suportado."""
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    
    try:
        extract_text(tmp.name)
        assert False, "Deveria ter levantado ValueError"
    except ValueError as e:
        assert "não suportado" in str(e).lower()
    
    os.unlink(tmp.name)
    print("✓ test_extract_text_unsupported")


def test_source_type_inference():
    """Infere source_type corretamente baseado no path."""
    assert get_source_type_from_path("data/bronze/calls/grooming.md") == "transcricao_reuniao"
    assert get_source_type_from_path("data/bronze/chats/slack.md") == "chat"
    assert get_source_type_from_path("data/bronze/docs/prd.md") == "documento_produto"
    assert get_source_type_from_path("data/bronze/docs/requisitos-cliente-enterprise.md") == "documento_cliente"
    print("✓ test_source_type_inference")


# === Testes de parsing ===

def test_parse_clean_json():
    """Parse de JSON limpo sem code fences."""
    response = '[{"title": "Test", "content": "Content"}]'
    result = _parse_llm_response(response)
    assert len(result) == 1
    assert result[0]["title"] == "Test"
    print("✓ test_parse_clean_json")


def test_parse_json_with_code_fences():
    """Parse de JSON dentro de code fences markdown."""
    response = '```json\n[{"title": "Test", "content": "Content"}]\n```'
    result = _parse_llm_response(response)
    assert len(result) == 1
    print("✓ test_parse_json_with_code_fences")


def test_parse_json_with_extra_text():
    """Parse de JSON com texto extra antes e depois."""
    response = 'Aqui estão os chunks:\n[{"title": "Test", "content": "Content"}]\nFim.'
    result = _parse_llm_response(response)
    assert len(result) == 1
    print("✓ test_parse_json_with_extra_text")


def test_parse_json_with_trailing_commas():
    """Parse de JSON com trailing commas (erro comum de LLMs)."""
    response = '[{"title": "Test", "content": "Content",}]'
    result = _parse_llm_response(response)
    assert len(result) == 1
    print("✓ test_parse_json_with_trailing_commas")


def test_parse_invalid_json():
    """Parse falha com JSONDecodeError para texto não-JSON."""
    try:
        _parse_llm_response("Isso não é JSON nenhum")
        assert False, "Deveria ter levantado exceção"
    except (json.JSONDecodeError, ValueError):
        pass
    print("✓ test_parse_invalid_json")


def test_parse_empty_array():
    """Parse falha com ValueError para array vazio."""
    try:
        _parse_llm_response("[]")
        assert False, "Deveria ter levantado ValueError"
    except ValueError as e:
        assert "vazio" in str(e).lower()
    print("✓ test_parse_empty_array")


# === Testes de validação ===

def test_validate_valid_chunks():
    """Validação aceita chunks corretos."""
    chunks = [
        {
            "title": "Regra de prazo",
            "content": "Prazo de 30 dias corridos para pessoa física.",
            "chunk_type": "regra_negocio",
            "feature": "devolucao_produtos",
            "domain": "pos_venda",
            "confidence": "high",
            "tags": ["prazo"],
            "participants": [],
            "related_features": [],
        }
    ]
    # Não deve levantar exceção
    _validate_chunks(chunks, "test.md")
    print("✓ test_validate_valid_chunks")


def test_validate_missing_field():
    """Validação rejeita chunk sem campo obrigatório."""
    chunks = [{"title": "Test", "content": "Content"}]  # Sem chunk_type, feature, domain
    try:
        _validate_chunks(chunks, "test.md")
        assert False, "Deveria ter levantado ValueError"
    except ValueError as e:
        assert "ausente" in str(e).lower() or "chunk_type" in str(e).lower()
    print("✓ test_validate_missing_field")


def test_validate_invalid_chunk_type_mapped():
    """Validação mapeia chunk_type inválido para válido quando possível."""
    chunks = [
        {
            "title": "Test",
            "content": "Content here sufficient length to pass checks for validation purposes.",
            "chunk_type": "regra_de_negocio",  # Inválido mas mapeável
            "feature": "test",
            "domain": "pos_venda",
            "confidence": "high",
            "tags": [],
            "participants": [],
            "related_features": [],
        }
    ]
    _validate_chunks(chunks, "test.md")
    assert chunks[0]["chunk_type"] == "regra_negocio"  # Mapeado
    print("✓ test_validate_invalid_chunk_type_mapped")


def test_validate_normalizes_feature():
    """Validação normaliza feature para snake_case."""
    chunks = [
        {
            "title": "Test",
            "content": "Content here sufficient.",
            "chunk_type": "regra_negocio",
            "feature": "Devolução de Produtos",  # Não snake_case
            "domain": "pos_venda",
            "confidence": "high",
            "tags": [],
            "participants": [],
            "related_features": [],
        }
    ]
    _validate_chunks(chunks, "test.md")
    assert chunks[0]["feature"] == "devolução_de_produtos"
    print("✓ test_validate_normalizes_feature")


# === Teste de chunking com mock ===

def test_chunk_and_classify_with_mock():
    """Chunking completo com LLM mockado."""
    mock_client = MockLLMClient()
    
    result = asyncio.run(chunk_and_classify(
        raw_text="Texto bruto de teste com conteúdo suficiente para processamento.",
        source_ref="data/bronze/calls/test.md",
        source_type="transcricao_reuniao",
        llm_client=mock_client,
    ))
    
    assert len(result) == 3
    assert result[0]["chunk_type"] == "regra_negocio"
    assert result[1]["chunk_type"] == "decisao_tecnica"
    assert result[2]["chunk_type"] == "fluxo_usuario"
    assert mock_client.call_count == 1
    print("✓ test_chunk_and_classify_with_mock")


# === Teste de pipeline completo ===

def test_pipeline_end_to_end_with_mock():
    """Pipeline completo: bronze → chunking mockado → silver."""
    # Criar estrutura bronze temporária
    tmp_dir = tempfile.mkdtemp()
    bronze_dir = os.path.join(tmp_dir, "bronze")
    calls_dir = os.path.join(bronze_dir, "calls")
    os.makedirs(calls_dir)
    
    # Criar arquivo de teste
    with open(os.path.join(calls_dir, "test-grooming.md"), "w", encoding="utf-8") as f:
        f.write("# Grooming\n\nDiscussão sobre devolução de produtos com regras de negócio e decisões técnicas relevantes para o desenvolvimento da feature.")
    
    # Banco temporário
    db_path = os.path.join(tmp_dir, "silver", "test.db")
    
    # Rodar pipeline
    mock_client = MockLLMClient()
    stats = asyncio.run(run_ingestion(
        bronze_dir=bronze_dir,
        db_path=db_path,
        llm_client=mock_client,
    ))
    
    # Verificar resultado
    assert stats["files_processed"] == 1
    assert stats["chunks_created"] == 3
    assert stats["errors"] == []
    
    # Verificar banco
    conn = init_db(db_path)
    db_stats = get_db_stats(conn)
    assert db_stats["total_chunks"] == 3
    assert "regra_negocio" in db_stats["chunks_by_type"]
    
    # Verificar FTS5 funciona
    cursor = conn.execute("""
        SELECT c.title FROM chunks c
        JOIN chunks_fts fts ON c.id = fts.id
        WHERE chunks_fts MATCH 'devolução'
    """)
    fts_results = cursor.fetchall()
    assert len(fts_results) > 0, "FTS5 deveria encontrar chunks sobre devolução"
    
    conn.close()
    
    # Limpar
    import shutil
    shutil.rmtree(tmp_dir)
    
    print("✓ test_pipeline_end_to_end_with_mock")


def test_discover_files():
    """Descoberta de arquivos encontra apenas tipos suportados."""
    tmp_dir = tempfile.mkdtemp()
    
    # Criar arquivos diversos
    os.makedirs(os.path.join(tmp_dir, "calls"))
    open(os.path.join(tmp_dir, "calls", "test.md"), "w").close()
    open(os.path.join(tmp_dir, "calls", "test.txt"), "w").close()
    open(os.path.join(tmp_dir, "calls", "test.pdf"), "w").close()     # Não suportado
    open(os.path.join(tmp_dir, "calls", ".hidden.md"), "w").close()   # Incluído (não é dir oculto)
    os.makedirs(os.path.join(tmp_dir, ".git"))                        # Dir oculto
    open(os.path.join(tmp_dir, ".git", "config.md"), "w").close()     # Dentro de dir oculto
    
    files = _discover_files(tmp_dir)
    
    assert len(files) == 3  # test.md, test.txt, .hidden.md
    assert all(f.endswith((".md", ".txt")) for f in files)
    assert not any(".git" in f for f in files)
    
    import shutil
    shutil.rmtree(tmp_dir)
    
    print("✓ test_discover_files")


def test_pipeline_skips_short_files():
    """Pipeline pula arquivos muito curtos (< 50 chars)."""
    tmp_dir = tempfile.mkdtemp()
    bronze_dir = os.path.join(tmp_dir, "bronze", "docs")
    os.makedirs(bronze_dir)
    
    with open(os.path.join(bronze_dir, "short.md"), "w") as f:
        f.write("Muito curto")  # < 50 chars
    
    db_path = os.path.join(tmp_dir, "silver", "test.db")
    mock_client = MockLLMClient()
    
    stats = asyncio.run(run_ingestion(
        bronze_dir=os.path.join(tmp_dir, "bronze"),
        db_path=db_path,
        llm_client=mock_client,
    ))
    
    assert stats["files_skipped"] == 1
    assert stats["files_processed"] == 0
    assert mock_client.call_count == 0  # LLM nem foi chamado
    
    import shutil
    shutil.rmtree(tmp_dir)
    
    print("✓ test_pipeline_skips_short_files")


def test_pipeline_dry_run():
    """Dry run processa mas não insere no banco."""
    tmp_dir = tempfile.mkdtemp()
    bronze_dir = os.path.join(tmp_dir, "bronze", "calls")
    os.makedirs(bronze_dir)
    
    with open(os.path.join(bronze_dir, "test.md"), "w", encoding="utf-8") as f:
        f.write("# Test\n\nConteúdo suficiente para não ser pulado pelo filtro de tamanho mínimo do pipeline de ingestão.")
    
    db_path = os.path.join(tmp_dir, "silver", "test.db")
    mock_client = MockLLMClient()
    
    stats = asyncio.run(run_ingestion(
        bronze_dir=os.path.join(tmp_dir, "bronze"),
        db_path=db_path,
        llm_client=mock_client,
        dry_run=True,
    ))
    
    assert stats["files_processed"] == 1
    assert stats["chunks_created"] == 3
    # Banco NÃO deve existir
    assert not os.path.exists(db_path)
    
    import shutil
    shutil.rmtree(tmp_dir)
    
    print("✓ test_pipeline_dry_run")


# === RUNNER ===

if __name__ == "__main__":
    tests = [
        # Extração
        test_extract_text_md,
        test_extract_text_file_not_found,
        test_extract_text_unsupported,
        test_source_type_inference,
        # Parsing
        test_parse_clean_json,
        test_parse_json_with_code_fences,
        test_parse_json_with_extra_text,
        test_parse_json_with_trailing_commas,
        test_parse_invalid_json,
        test_parse_empty_array,
        # Validação
        test_validate_valid_chunks,
        test_validate_missing_field,
        test_validate_invalid_chunk_type_mapped,
        test_validate_normalizes_feature,
        # Chunking
        test_chunk_and_classify_with_mock,
        # Pipeline
        test_pipeline_end_to_end_with_mock,
        test_discover_files,
        test_pipeline_skips_short_files,
        test_pipeline_dry_run,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print(f"\n{'=' * 50}")
    print(f"Resultado: {passed} passed, {failed} failed, {passed + failed} total")
    
    if failed > 0:
        sys.exit(1)
```

---

## Validação final da Etapa 3

```bash
# 1. Verificar que os arquivos existem
ls -la src/ingestion/__init__.py
ls -la src/ingestion/extractor.py
ls -la src/ingestion/chunker.py
ls -la src/ingestion/pipeline.py
ls -la src/ingestion/llm_client.py
ls -la scripts/run_ingestion.py
ls -la tests/test_ingestion.py

# 2. Rodar testes (não precisa de API key — usa mock)
python tests/test_ingestion.py

# Esperado:
# ✓ test_extract_text_md
# ✓ test_extract_text_file_not_found
# ✓ test_extract_text_unsupported
# ✓ test_source_type_inference
# ✓ test_parse_clean_json
# ✓ test_parse_json_with_code_fences
# ✓ test_parse_json_with_extra_text
# ✓ test_parse_json_with_trailing_commas
# ✓ test_parse_invalid_json
# ✓ test_parse_empty_array
# ✓ test_validate_valid_chunks
# ✓ test_validate_missing_field
# ✓ test_validate_invalid_chunk_type_mapped
# ✓ test_validate_normalizes_feature
# ✓ test_chunk_and_classify_with_mock
# ✓ test_pipeline_end_to_end_with_mock
# ✓ test_discover_files
# ✓ test_pipeline_skips_short_files
# ✓ test_pipeline_dry_run
#
# Resultado: 19 passed, 0 failed, 19 total

# 3. Teste com LLM real (requer API key)
# Só rodar se tiver a key configurada
export ANTHROPIC_API_KEY="sk-..."
python scripts/run_ingestion.py --verbose

# Esperado:
# - 5 arquivos processados
# - 15-30 chunks criados (3-6 por arquivo)
# - 0 erros
# - Base Silver populada

# 4. Verificar base após ingestão real
python -c "
from src.knowledge.schema import init_db, get_db_stats
from src.knowledge.manifest import get_feature_summary_text

conn = init_db('data/silver/knowledge.db')
stats = get_db_stats(conn)
print(f'Total chunks: {stats[\"total_chunks\"]}')
print(f'Por tipo: {stats[\"chunks_by_type\"]}')
print(f'Por feature: {stats[\"chunks_by_feature\"]}')
print()
print(get_feature_summary_text(conn))
conn.close()
"

# 5. Testar busca na base populada (integração com Etapa 2)
python -c "
from src.knowledge.search import KnowledgeBaseSearch, SearchQuery

search = KnowledgeBaseSearch('data/silver/knowledge.db')

# Busca textual
results = search.search(SearchQuery(
    text='prazo devolução pessoa física',
    feature='devolucao_produtos',
    top_k=5,
))
print(f'Busca \"prazo devolução PF\": {len(results)} resultados')
for r in results:
    print(f'  [{r.chunk_type}] {r.title} (confiança: {r.confidence})')

# Feature context
all_chunks = search.get_feature_context('devolucao_produtos')
total_tokens = search.estimate_feature_tokens('devolucao_produtos')
print(f'\nFeature context: {len(all_chunks)} chunks, ~{total_tokens} tokens estimados')

search.close()
"
```

## Critérios de aceite da Etapa 3

- [ ] `src/ingestion/extractor.py` — extrai texto de .md e .txt, infere source_type pelo path
- [ ] `src/ingestion/llm_client.py` — abstração funcional com Anthropic e OpenAI/Azure
- [ ] `src/ingestion/chunker.py` — system prompt completo, parsing robusto de JSON (code fences, trailing commas, texto extra), validação com mapeamento de tipos inválidos, normalização de feature
- [ ] `src/ingestion/pipeline.py` — orquestra extração → chunking → inserção, com batch insert, stats, logging, tratamento de erros por arquivo
- [ ] `scripts/run_ingestion.py` — CLI funcional com argumentos (--provider, --model, --dry-run, --verbose)
- [ ] Todos os 19 testes passam SEM API key (mock LLM)
- [ ] Com API key real: 5 arquivos bronze geram 15-30 chunks na Silver
- [ ] Chunks na Silver têm metadados corretos (verificável via `get_db_stats`)
- [ ] FTS5 encontra chunks após ingestão (busca por "devolução" retorna resultados)
- [ ] Pipeline é idempotente — rodar duas vezes não duplica chunks (verificar por source_ref)
- [ ] Dry run funciona (processa sem criar banco)

## Notas para implementação

**Ponto de atenção 1:** O prompt do chunker é o componente mais sensível. Se os chunks estiverem saindo com sumarização ou classificação errada, itere o prompt antes de mexer no código. O prompt é mais barato de mudar que a lógica.

**Ponto de atenção 2:** O parsing do JSON é onde mais coisas quebram. LLMs retornam JSON dentro de code fences, com trailing commas, com texto extra, com aspas escapadas errado. O `_parse_llm_response` cobre os casos mais comuns, mas pode precisar de ajuste se o modelo retornar algo inesperado.

**Ponto de atenção 3:** A idempotência do pipeline NÃO está implementada nesta spec (para simplificar o MVP). Se rodar o pipeline duas vezes, vai duplicar os chunks. Para o MVP isso é aceitável — basta deletar o banco e rodar de novo. Para produção, adicionar verificação por source_ref + hash do conteúdo.
