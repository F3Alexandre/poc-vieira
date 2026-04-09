# MVP — Base de Conhecimento Central + Agente de Specs

## Visão geral

**Objetivo:** Demo funcional end-to-end de um sistema que ingere documentação de produto, cria uma base de conhecimento estruturada, e usa um agente conversacional para gerar User Stories completas a partir dessa base.

**Prazo:** Quinta-feira (1 dia completo de desenvolvimento).

**Restrição:** Tudo deve funcionar localmente. Integração com Azure DevOps é simulada — output final são arquivos Markdown seguindo o template de cards.

**Stack sugerida:** Python 3.11+, SQLite com FTS5 (base Silver), rank_bm25 ou bm25s (busca textual), API do LLM (Anthropic Claude ou Azure OpenAI), FastAPI ou CLI para o agente, arquivos .md como output de cards.

---

## Estrutura de diretórios do projeto

```
knowledge-base-mvp/
├── data/
│   ├── bronze/              # Dados brutos simulados
│   │   ├── calls/           # Transcrições de reuniões (.md ou .txt)
│   │   ├── docs/            # Documentos de produto (.md)
│   │   └── chats/           # Mensagens de chat (.md)
│   ├── silver/              # Chunks processados (SQLite DB)
│   │   └── knowledge.db     # Base de conhecimento
│   └── output/              # Cards gerados
│       └── cards/           # Arquivos .md dos work items
├── src/
│   ├── ingestion/           # Pipeline de ingestão
│   │   ├── extractor.py     # Extração de texto por tipo de arquivo
│   │   ├── chunker.py       # Segmentação via LLM
│   │   ├── classifier.py    # Classificação multi-label
│   │   └── pipeline.py      # Orquestrador do pipeline
│   ├── knowledge/           # Base de conhecimento
│   │   ├── schema.py        # Schema da Silver (SQLite + FTS5)
│   │   ├── search.py        # Interface de busca (filtro metadados + BM25)
│   │   ├── manifest.py      # Manifesto de features (view materializado)
│   │   └── cache.py         # Cache de busca e de feature
│   ├── agent/               # Agente conversacional
│   │   ├── agent.py         # Loop principal do agente
│   │   ├── prompts.py       # System prompt, templates, glossário
│   │   ├── tools.py         # Skills/tools do agente
│   │   ├── memory.py        # Working memory + compactação
│   │   └── checklist.py     # Checklist interno do template
│   ├── output/              # Geração de cards
│   │   ├── card_generator.py    # Gera o Markdown do card
│   │   └── card_template.py     # Template estruturado
│   └── config.py            # Configurações gerais
├── tests/
│   ├── test_ingestion.py
│   ├── test_search.py
│   ├── test_agent.py
│   └── test_card_generation.py
├── scripts/
│   ├── seed_bronze.py       # Gera dados simulados
│   ├── run_ingestion.py     # Roda o pipeline de ingestão
│   └── run_agent.py         # Inicia o agente (CLI ou API)
├── requirements.txt
└── README.md
```

---

## ETAPA 1 — Dados simulados (Bronze)
**Tempo estimado: 1-2 horas**
**Prioridade: CRÍTICA — tudo depende disso**
**Teste: verificar que os arquivos existem e são legíveis**

### O que fazer

Criar 3-5 documentos simulados de uma feature fictícia mas realista. Sugestão: feature "Devolução de Produtos" de um e-commerce, porque tem regras de negócio complexas, exceções, integrações e fluxos claros.

### Dados a criar

#### 1.1 — Transcrição de grooming (`data/bronze/calls/grooming-devolucao-2026-04-01.md`)

Simular uma transcrição de reunião de grooming onde PO, arquiteto e dev discutem a feature de devolução. Deve conter:
- Discussão sobre regras de devolução (prazo de 30 dias, exceções para PJ com contrato)
- Decisão técnica sobre API de estorno integrada com gateway de pagamento
- Fluxo do usuário discutido informalmente
- Uma ambiguidade não resolvida (ex: devolução parcial — devolver apenas 1 item de um pedido com 3)
- Menção a performance: "precisa ser rápido, não pode demorar"
- Participantes: Ana (PO), Carlos (Arquiteto), Pedro (Dev)

Formato: texto corrido simulando fala, com identificação de quem falou.

```markdown
# Grooming — Devolução de Produtos
**Data:** 2026-04-01
**Participantes:** Ana (PO), Carlos (Arquiteto), Pedro (Dev)

**Ana:** Pessoal, vamos definir a feature de devolução. O cliente precisa conseguir solicitar a devolução de um produto pelo app e pelo site...

**Carlos:** Precisamos definir o prazo. Pelo CDC é 7 dias pra arrependimento, mas comercialmente a gente oferece 30 dias, certo?

**Ana:** Isso, 30 dias para pessoa física. Para PJ com contrato enterprise, o prazo é o que estiver no contrato, pode ser 60 ou 90 dias...

[continuar com 800-1200 palavras cobrindo todos os pontos acima]
```

#### 1.2 — Documento de produto (`data/bronze/docs/prd-devolucao-v2.md`)

Um PRD (Product Requirements Document) mais formal cobrindo:
- Visão geral da feature
- Personas afetadas (cliente PF, cliente PJ, operador de suporte)
- Regras de negócio formalizadas (incluindo as que foram discutidas no grooming)
- Requisitos não funcionais (SLA de 200ms, disponibilidade 99.9%)
- Integrações necessárias (gateway de pagamento, sistema de logística reversa, SAC)
- O que está fora do escopo (troca de produto — é outra feature)

Formato: markdown estruturado com headers.

#### 1.3 — Chat de alinhamento (`data/bronze/chats/slack-devolucao-2026-04-03.md`)

Simular mensagens de Slack/Teams onde:
- Pedro (dev) pergunta sobre edge case: "e se o produto já foi usado?"
- Ana (PO) responde: "produto usado não aceita devolução, exceto defeito"
- Carlos (arquiteto) menciona: "o endpoint de estorno do gateway tem rate limit de 100 req/min"
- Alguém menciona informalmente: "acho que deveria ter uma tela de acompanhamento do status da devolução"

Formato: mensagens com timestamp e autor.

#### 1.4 — Documento do cliente (`data/bronze/docs/requisitos-cliente-enterprise.md`)

Simular um documento de requisitos de um cliente enterprise que tem condições especiais:
- Prazo de devolução de 90 dias
- Necessidade de aprovação por gestor antes da devolução
- Integração com ERP do cliente via webhook
- Relatório mensal de devoluções

#### 1.5 — Ata de refinamento técnico (`data/bronze/calls/refinamento-tecnico-devolucao-2026-04-05.md`)

Simular uma ata onde:
- Decisão: API REST com endpoint POST /api/v1/returns
- Decisão: status machine com estados: requested → approved → shipping → received → refunded
- Decisão: usar mensageria (SQS/RabbitMQ) para comunicação com logística
- Decisão: idempotência no endpoint de estorno (evitar estorno duplicado)
- Dúvida pendente: como lidar com devolução parcial (não resolvido ainda)

### Como testar

```bash
# Verificar que os arquivos existem e têm conteúdo
find data/bronze -type f -name "*.md" | while read f; do
  echo "$f: $(wc -w < $f) palavras"
done
# Esperado: 5 arquivos, cada um com 200-500 palavras
```

---

## ETAPA 2 — Schema da base Silver (SQLite + FTS5)
**Tempo estimado: 1-2 horas**
**Prioridade: CRÍTICA**
**Dependência: nenhuma**
**Teste: criar banco, inserir chunk de teste, consultar via FTS5**

### O que fazer

Criar o schema SQLite com duas tabelas: `chunks` (dados estruturados) e `chunks_fts` (índice full-text search via FTS5).

### Schema detalhado (`src/knowledge/schema.py`)

```python
import sqlite3
import json
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass, field, asdict

# --- Enums controlados ---

CHUNK_TYPES = [
    "regra_negocio",
    "fluxo_usuario",
    "decisao_tecnica",
    "requisito_nao_funcional",
    "definicao_escopo",
    "restricao",
    "criterio_aceite",
    "integracao",
    "vocabulario",
    "contexto_negocio",
]

SOURCE_TYPES = [
    "transcricao_reuniao",
    "documento_produto",
    "documento_cliente",
    "chat",
    "card_devops",
    "documentacao_tecnica",
    "decisao_registro",
]

CONFIDENCE_LEVELS = ["high", "medium", "low"]

DOMAINS = [
    "financeiro",
    "logistica",
    "pos_venda",
    "cadastro",
    "autenticacao",
    "integracao",
    "relatorios",
    # Extensível — novos domínios adicionados conforme necessidade
]

# --- Dataclass do chunk ---

@dataclass
class Chunk:
    id: str                          # UUID gerado na ingestão
    title: str                       # Título descritivo gerado pelo LLM
    content: str                     # Texto completo do chunk (sem sumarização)
    feature: str                     # Enum — identificador da funcionalidade
    domain: str                      # Enum — domínio de negócio
    chunk_type: str                  # Enum — tipo da informação
    source_type: str                 # Enum — origem do dado
    source_ref: str                  # Caminho do arquivo bronze original
    confidence: str                  # high | medium | low
    tags: List[str] = field(default_factory=list)
    participants: List[str] = field(default_factory=list)
    related_features: List[str] = field(default_factory=list)
    language: str = "pt-br"
    status: str = "active"           # active | deprecated | superseded
    superseded_by: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        now = datetime.utcnow().isoformat() + "Z"
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

# --- Criação do banco ---

CREATE_CHUNKS_TABLE = """
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    feature TEXT NOT NULL,
    domain TEXT NOT NULL,
    chunk_type TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    confidence TEXT NOT NULL DEFAULT 'medium',
    tags TEXT NOT NULL DEFAULT '[]',           -- JSON array
    participants TEXT NOT NULL DEFAULT '[]',   -- JSON array
    related_features TEXT NOT NULL DEFAULT '[]', -- JSON array
    language TEXT NOT NULL DEFAULT 'pt-br',
    status TEXT NOT NULL DEFAULT 'active',
    superseded_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

CREATE_FTS_TABLE = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    id UNINDEXED,
    title,
    content,
    tags,
    tokenize='unicode61 remove_diacritics 2'
);
"""

# Triggers para manter FTS sincronizado
CREATE_FTS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(id, title, content, tags)
    VALUES (new.id, new.title, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    DELETE FROM chunks_fts WHERE id = old.id;
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    DELETE FROM chunks_fts WHERE id = old.id;
    INSERT INTO chunks_fts(id, title, content, tags)
    VALUES (new.id, new.title, new.content, new.tags);
END;
"""

# Índices para filtros de metadados (pré-BM25)
CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_chunks_feature ON chunks(feature);
CREATE INDEX IF NOT EXISTS idx_chunks_domain ON chunks(domain);
CREATE INDEX IF NOT EXISTS idx_chunks_chunk_type ON chunks(chunk_type);
CREATE INDEX IF NOT EXISTS idx_chunks_status ON chunks(status);
CREATE INDEX IF NOT EXISTS idx_chunks_confidence ON chunks(confidence);
CREATE INDEX IF NOT EXISTS idx_chunks_feature_domain ON chunks(feature, domain);
"""

def init_db(db_path: str) -> sqlite3.Connection:
    """Inicializa o banco com schema completo."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(CREATE_CHUNKS_TABLE)
    conn.executescript(CREATE_FTS_TABLE)
    conn.executescript(CREATE_FTS_TRIGGERS)
    conn.executescript(CREATE_INDEXES)
    conn.commit()
    return conn

def insert_chunk(conn: sqlite3.Connection, chunk: Chunk) -> None:
    """Insere um chunk na base."""
    conn.execute("""
        INSERT INTO chunks (
            id, title, content, feature, domain, chunk_type,
            source_type, source_ref, confidence, tags, participants,
            related_features, language, status, superseded_by,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        chunk.id, chunk.title, chunk.content, chunk.feature,
        chunk.domain, chunk.chunk_type, chunk.source_type,
        chunk.source_ref, chunk.confidence,
        json.dumps(chunk.tags), json.dumps(chunk.participants),
        json.dumps(chunk.related_features), chunk.language,
        chunk.status, chunk.superseded_by,
        chunk.created_at, chunk.updated_at
    ))
    conn.commit()
```

### Como testar

```bash
python -c "
from src.knowledge.schema import init_db, insert_chunk, Chunk
import uuid

conn = init_db('data/silver/knowledge.db')
chunk = Chunk(
    id=str(uuid.uuid4()),
    title='Regra de prazo de devolução para PF',
    content='O prazo de devolução para pessoa física é de 30 dias corridos a partir da data de entrega do produto. Após esse prazo, a devolução não é aceita exceto em casos de defeito de fabricação cobertos pela garantia.',
    feature='devolucao_produtos',
    domain='pos_venda',
    chunk_type='regra_negocio',
    source_type='documento_produto',
    source_ref='data/bronze/docs/prd-devolucao-v2.md',
    confidence='high',
    tags=['devolucao', 'prazo', 'pessoa_fisica', '30_dias'],
    participants=['ana_po'],
    related_features=['garantia']
)
insert_chunk(conn, chunk)

# Testar FTS5
cursor = conn.execute(\"\"\"
    SELECT c.* FROM chunks c
    JOIN chunks_fts fts ON c.id = fts.id
    WHERE chunks_fts MATCH 'devolução prazo'
    AND c.feature = 'devolucao_produtos'
    ORDER BY rank
\"\"\")
results = cursor.fetchall()
print(f'Encontrados: {len(results)} chunks')
for r in results:
    print(f'  - {r[\"title\"]} (confidence: {r[\"confidence\"]})')
"
# Esperado: 1 chunk encontrado
```

---

## ETAPA 3 — Interface de busca (filtro metadados + BM25/FTS5)
**Tempo estimado: 1-2 horas**
**Prioridade: CRÍTICA**
**Dependência: Etapa 2**
**Teste: buscar chunks com diferentes combinações de filtros**

### O que fazer

Implementar a interface de busca abstrata que o agente usará. A busca acontece em dois estágios: primeiro filtra por metadados (SQL), depois rankeia por relevância textual (FTS5). Incluir cache em memória.

### Especificação (`src/knowledge/search.py`)

```python
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import sqlite3
import json
import hashlib
import time

@dataclass
class SearchResult:
    chunk_id: str
    title: str
    content: str
    feature: str
    domain: str
    chunk_type: str
    confidence: str
    tags: List[str]
    relevance_rank: int        # Posição no ranking (1 = mais relevante)
    source_type: str
    source_ref: str
    created_at: str

@dataclass
class SearchQuery:
    """Query estruturada que o agente constrói."""
    text: str                                  # Texto livre para FTS5/BM25
    feature: Optional[str] = None              # Filtro exato
    domain: Optional[str] = None               # Filtro exato
    chunk_types: Optional[List[str]] = None    # Filtro IN
    confidence_min: Optional[str] = None       # Filtro >= (high > medium > low)
    tags: Optional[List[str]] = None           # Filtro — chunk deve ter ALGUMA dessas tags
    status: str = "active"                     # Default: só chunks ativos
    top_k: int = 10                            # Quantidade máxima de resultados


class KnowledgeBaseSearch:
    """Interface de busca abstrata.
    
    Hoje: filtro SQL + FTS5 (SQLite).
    Futuro: trocar implementação para pgvector + pg_textsearch sem mudar a interface.
    """

    CONFIDENCE_ORDER = {"high": 3, "medium": 2, "low": 1}

    def __init__(self, db_path: str, cache_ttl_seconds: int = 300):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.cache: Dict[str, Any] = {}  # hash(query) → (timestamp, results)
        self.cache_ttl = cache_ttl_seconds

    def search(self, query: SearchQuery) -> List[SearchResult]:
        """Busca em dois estágios: filtro SQL → FTS5 ranking."""

        # 1. Verificar cache
        cache_key = self._cache_key(query)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        # 2. Construir filtros SQL
        where_clauses = ["c.status = ?"]
        params = [query.status]

        if query.feature:
            where_clauses.append("c.feature = ?")
            params.append(query.feature)

        if query.domain:
            where_clauses.append("c.domain = ?")
            params.append(query.domain)

        if query.chunk_types:
            placeholders = ",".join(["?"] * len(query.chunk_types))
            where_clauses.append(f"c.chunk_type IN ({placeholders})")
            params.extend(query.chunk_types)

        if query.confidence_min:
            min_order = self.CONFIDENCE_ORDER.get(query.confidence_min, 1)
            valid_levels = [k for k, v in self.CONFIDENCE_ORDER.items() if v >= min_order]
            placeholders = ",".join(["?"] * len(valid_levels))
            where_clauses.append(f"c.confidence IN ({placeholders})")
            params.extend(valid_levels)

        if query.tags:
            # Busca chunks que contenham QUALQUER uma das tags
            tag_conditions = []
            for tag in query.tags:
                tag_conditions.append("c.tags LIKE ?")
                params.append(f"%{tag}%")
            where_clauses.append(f"({' OR '.join(tag_conditions)})")

        where_sql = " AND ".join(where_clauses)

        # 3. Se tem texto, usar FTS5 para ranking
        if query.text.strip():
            sql = f"""
                SELECT c.*, fts.rank as fts_rank
                FROM chunks c
                JOIN chunks_fts fts ON c.id = fts.id
                WHERE chunks_fts MATCH ?
                AND {where_sql}
                ORDER BY fts.rank
                LIMIT ?
            """
            params = [query.text] + params + [query.top_k]
        else:
            # Sem texto, retorna filtrado por metadados ordenado por data
            sql = f"""
                SELECT c.*, 0 as fts_rank
                FROM chunks c
                WHERE {where_sql}
                ORDER BY c.updated_at DESC
                LIMIT ?
            """
            params = params + [query.top_k]

        cursor = self.conn.execute(sql, params)
        rows = cursor.fetchall()

        results = []
        for i, row in enumerate(rows):
            results.append(SearchResult(
                chunk_id=row["id"],
                title=row["title"],
                content=row["content"],
                feature=row["feature"],
                domain=row["domain"],
                chunk_type=row["chunk_type"],
                confidence=row["confidence"],
                tags=json.loads(row["tags"]),
                relevance_rank=i + 1,
                source_type=row["source_type"],
                source_ref=row["source_ref"],
                created_at=row["created_at"],
            ))

        # 4. Cachear resultado
        self._set_cached(cache_key, results)

        return results

    def get_feature_context(self, feature: str) -> List[SearchResult]:
        """Carrega TODOS os chunks de uma feature.
        
        Usado na Fase 2 do agente: contextualização completa.
        Se couber no contexto, injeta tudo direto (sem BM25).
        """
        cache_key = f"feature_context:{feature}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        query = SearchQuery(
            text="",
            feature=feature,
            top_k=100  # Pega todos
        )
        results = self.search(query)
        self._set_cached(cache_key, results)
        return results

    def _cache_key(self, query: SearchQuery) -> str:
        raw = json.dumps(vars(query), sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _get_cached(self, key: str):
        if key in self.cache:
            ts, results = self.cache[key]
            if time.time() - ts < self.cache_ttl:
                return results
            del self.cache[key]
        return None

    def _set_cached(self, key: str, results):
        self.cache[key] = (time.time(), results)

    def invalidate_feature_cache(self, feature: str):
        """Chamado após nova ingestão em uma feature."""
        keys_to_remove = [k for k in self.cache if feature in k]
        for k in keys_to_remove:
            del self.cache[k]
```

### Manifesto de features (`src/knowledge/manifest.py`)

```python
def get_feature_manifest(conn: sqlite3.Connection) -> List[Dict]:
    """View materializado: resume o que existe na base por feature."""
    cursor = conn.execute("""
        SELECT
            feature,
            domain,
            COUNT(*) as total_chunks,
            GROUP_CONCAT(DISTINCT chunk_type) as chunk_types_available,
            MAX(updated_at) as last_updated,
            SUM(CASE WHEN confidence = 'high' THEN 1 ELSE 0 END) as high_confidence_count,
            SUM(CASE WHEN confidence = 'medium' THEN 1 ELSE 0 END) as medium_confidence_count,
            SUM(CASE WHEN confidence = 'low' THEN 1 ELSE 0 END) as low_confidence_count
        FROM chunks
        WHERE status = 'active'
        GROUP BY feature, domain
        ORDER BY feature
    """)
    return [dict(row) for row in cursor.fetchall()]
```

### Como testar

```bash
python -c "
from src.knowledge.search import KnowledgeBaseSearch, SearchQuery

search = KnowledgeBaseSearch('data/silver/knowledge.db')

# Teste 1: Busca por metadados + texto
results = search.search(SearchQuery(
    text='prazo devolução',
    feature='devolucao_produtos',
    chunk_types=['regra_negocio'],
    top_k=5
))
print(f'Teste 1 - Metadados + texto: {len(results)} resultados')

# Teste 2: Feature context completo
all_chunks = search.get_feature_context('devolucao_produtos')
print(f'Teste 2 - Feature context: {len(all_chunks)} chunks total')

# Teste 3: Cache (segunda chamada deve ser instantânea)
import time
start = time.time()
results2 = search.search(SearchQuery(text='prazo devolução', feature='devolucao_produtos'))
elapsed = time.time() - start
print(f'Teste 3 - Cache hit: {elapsed*1000:.1f}ms (esperado < 1ms)')
"
```

---

## ETAPA 4 — Pipeline de ingestão (Bronze → Silver)
**Tempo estimado: 2-3 horas**
**Prioridade: CRÍTICA**
**Dependência: Etapas 1, 2**
**Teste: rodar pipeline nos dados bronze, verificar chunks na Silver**

### O que fazer

Pipeline em 3 passos: extração de texto → chunking lógico via LLM → classificação e inserção na Silver.

### 4.1 — Extrator de texto (`src/ingestion/extractor.py`)

Para o MVP, só precisamos lidar com arquivos .md e .txt (os dados simulados são todos markdown).

```python
def extract_text(file_path: str) -> str:
    """Extrai texto bruto de um arquivo.
    
    MVP: suporta .md e .txt.
    Futuro: adicionar PDF (pdf-parse), imagens (OCR), .docx (pandoc).
    """
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()
```

### 4.2 — Chunker + Classificador via LLM (`src/ingestion/chunker.py`)

Este é o componente mais importante do pipeline. O LLM recebe o texto bruto completo e retorna uma lista de chunks já classificados.

**System prompt do LLM de ingestão:**

```
Você é um archivista especializado em documentação de produto de software.
Sua tarefa é receber um texto bruto (transcrição de reunião, documento,
mensagens de chat) e segmentá-lo em unidades lógicas de conhecimento.

REGRAS CRÍTICAS:
1. NUNCA sumarize. NUNCA remova informação. Reorganize para clareza,
   mas preserve TODO o conteúdo original.
2. Se o texto é ambíguo, preserve a ambiguidade e marque com
   [AMBIGUIDADE: descrição do que não ficou claro].
3. Se uma informação contradiz outra no mesmo documento, preserve ambas
   e marque com [CONTRADIÇÃO: descrição].
4. Cada chunk deve ser compreensível isoladamente — inclua contexto
   suficiente para que alguém entenda o chunk sem ler o documento original.

PARA CADA CHUNK, forneça:
- title: título descritivo (max 100 caracteres)
- content: texto completo da unidade de informação
- chunk_type: um de [regra_negocio, fluxo_usuario, decisao_tecnica,
  requisito_nao_funcional, definicao_escopo, restricao, criterio_aceite,
  integracao, vocabulario, contexto_negocio]
- feature: identificador da funcionalidade (snake_case, ex: devolucao_produtos)
- domain: um de [financeiro, logistica, pos_venda, cadastro, autenticacao,
  integracao, relatorios]
- confidence: high (documento formal), medium (reunião/decisão verbal),
  low (chat/menção informal)
- tags: lista de termos-chave relevantes para busca (inclua sinônimos
  e termos alternativos que alguém poderia usar para buscar esta informação)
- participants: lista de pessoas mencionadas ou envolvidas
- related_features: outras funcionalidades mencionadas ou impactadas

RESPONDA APENAS com um JSON array de chunks. Sem texto adicional.
Sem markdown code fences. Apenas o JSON puro.
```

**User prompt:**

```
Arquivo fonte: {source_ref}
Tipo de fonte: {source_type}

Texto bruto:
---
{raw_text}
---

Segmente este texto em chunks de conhecimento seguindo as regras.
Retorne um JSON array.
```

### 4.3 — Pipeline orquestrador (`src/ingestion/pipeline.py`)

```python
import os
import json
import uuid
from typing import List
from src.ingestion.extractor import extract_text
from src.knowledge.schema import Chunk, insert_chunk, init_db

# Mapeamento de diretório bronze → source_type
SOURCE_TYPE_MAP = {
    "calls": "transcricao_reuniao",
    "docs": "documento_produto",
    "chats": "chat",
}

async def run_ingestion(bronze_dir: str, db_path: str, llm_client) -> dict:
    """Executa o pipeline completo de ingestão."""
    conn = init_db(db_path)
    stats = {"files_processed": 0, "chunks_created": 0, "errors": []}

    for subdir, source_type in SOURCE_TYPE_MAP.items():
        dir_path = os.path.join(bronze_dir, subdir)
        if not os.path.exists(dir_path):
            continue

        for filename in os.listdir(dir_path):
            file_path = os.path.join(dir_path, filename)
            if not filename.endswith((".md", ".txt")):
                continue

            try:
                # Etapa 1: Extração
                raw_text = extract_text(file_path)

                # Etapa 2+3: Chunking + Classificação via LLM
                chunks_data = await chunk_and_classify(
                    raw_text=raw_text,
                    source_ref=file_path,
                    source_type=source_type,
                    llm_client=llm_client,
                )

                # Etapa 4: Inserção na Silver
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
                    insert_chunk(conn, chunk)
                    stats["chunks_created"] += 1

                stats["files_processed"] += 1

            except Exception as e:
                stats["errors"].append({"file": file_path, "error": str(e)})

    conn.close()
    return stats


async def chunk_and_classify(raw_text, source_ref, source_type, llm_client) -> List[dict]:
    """Chama o LLM para segmentar e classificar o texto."""
    # O system prompt e user prompt estão definidos acima
    # A implementação depende do client (Anthropic SDK, Azure OpenAI, etc.)
    # Retorna uma lista de dicts com os campos do chunk

    response = await llm_client.generate(
        system=INGESTION_SYSTEM_PROMPT,
        user=INGESTION_USER_PROMPT.format(
            source_ref=source_ref,
            source_type=source_type,
            raw_text=raw_text,
        ),
        # Modelo sugerido para ingestão: Claude Haiku ou GPT-4o-mini
        # A tarefa é classificação, não precisa de modelo pesado
    )

    # Parse do JSON retornado
    chunks = json.loads(response)
    
    # Validação básica
    for chunk in chunks:
        assert "title" in chunk, "Chunk sem título"
        assert "content" in chunk, "Chunk sem conteúdo"
        assert "chunk_type" in chunk, "Chunk sem tipo"
        assert chunk["chunk_type"] in CHUNK_TYPES, f"Tipo inválido: {chunk['chunk_type']}"

    return chunks
```

### Como testar

```bash
# Rodar pipeline completo
python scripts/run_ingestion.py

# Verificar resultado
python -c "
import sqlite3
conn = sqlite3.connect('data/silver/knowledge.db')
conn.row_factory = sqlite3.Row

# Total de chunks
total = conn.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]
print(f'Total chunks: {total}')

# Chunks por tipo
for row in conn.execute('SELECT chunk_type, COUNT(*) as n FROM chunks GROUP BY chunk_type ORDER BY n DESC'):
    print(f'  {row[\"chunk_type\"]}: {row[\"n\"]}')

# Chunks por feature
for row in conn.execute('SELECT feature, COUNT(*) as n FROM chunks GROUP BY feature'):
    print(f'  {row[\"feature\"]}: {row[\"n\"]}')

# Verificar que o FTS5 funciona
results = conn.execute(\"\"\"
    SELECT c.title FROM chunks c
    JOIN chunks_fts fts ON c.id = fts.id
    WHERE chunks_fts MATCH 'devolução'
\"\"\").fetchall()
print(f'FTS5 match \"devolução\": {len(results)} resultados')
"
# Esperado: 15-25 chunks total, distribuídos entre os tipos
```

---

## ETAPA 5 — Agente conversacional (System prompt + Tools + Fluxo)
**Tempo estimado: 3-4 horas**
**Prioridade: CRÍTICA**
**Dependência: Etapas 2, 3, 4**
**Teste: conversa completa end-to-end gerando um card**

### O que fazer

Implementar o agente com: system prompt completo, tools de busca, working memory, checklist interno, e fluxo de fases.

### 5.1 — System prompt do agente (`src/agent/prompts.py`)

```python
AGENT_SYSTEM_PROMPT = """
Você é um Agente de Especificação (Spec Agent) especializado em criar
User Stories completas e detalhadas para desenvolvimento de software.

## Seu papel

Você trabalha como um quarto participante em sessões de especificação,
ao lado de POs, arquitetos e engenheiros. Sua responsabilidade é:
1. Garantir que a especificação seja COMPLETA para desenvolvimento
2. Identificar contradições com a base de conhecimento existente
3. Cobrar informações faltantes que impactam o downstream
4. Gerar cards estruturados no template padronizado

## Base de conhecimento

Você tem acesso a uma base de conhecimento central que contém informações
documentadas sobre funcionalidades do sistema. Essas informações vêm de
reuniões, documentos de produto, chats e documentação técnica.

A base está organizada com os seguintes metadados:
- **feature**: identificador da funcionalidade (ex: devolucao_produtos)
- **domain**: domínio de negócio (financeiro, logistica, pos_venda, etc.)
- **chunk_type**: tipo da informação:
  - regra_negocio: lógica de negócio, condições, exceções
  - fluxo_usuario: passo-a-passo de interação
  - decisao_tecnica: escolhas de arquitetura, stack, padrões
  - requisito_nao_funcional: performance, segurança, acessibilidade
  - definicao_escopo: o que está dentro e fora
  - restricao: limitações conhecidas
  - criterio_aceite: condições de aceite já definidas
  - integracao: pontos de contato com outros sistemas
  - vocabulario: definições de termos
  - contexto_negocio: background, motivação
- **confidence**: alta (doc formal), média (reunião), baixa (chat informal)
- **tags**: termos-chave para busca

## Glossário de domínio (sinônimos)

Use este glossário para expandir suas buscas quando os termos do usuário
diferirem dos termos na base:

devolução = estorno = reversão = return
cancelamento = rescisão = churn = cancellation
PJ = empresa = corporativo = B2B = pessoa jurídica
PF = consumidor = pessoa física = B2C
checkout = pagamento = payment = finalização de compra
pedido = order = compra
SLA = tempo de resposta = latência = performance
webhook = callback = notificação = evento

## Fases da conversa

### Fase 1 — Coleta inicial
Antes de buscar na base, colete do usuário:
- Qual feature (nome ou descrição)
- Qual domínio de negócio
- Se é nova feature ou evolução de existente
- Quem são os stakeholders
NÃO busque na base antes de ter pelo menos a feature e o domínio.

### Fase 2 — Contextualização
Com os metadados, busque na base usando a tool search_knowledge_base.
Apresente ao usuário um resumo do que a base já sabe.
Pergunte se quer partir do contexto existente ou começar do zero.

### Fase 3 — Especificação interativa
Conduza a conversa cobrindo todos os campos do template.
Use o checklist interno para saber o que falta.
A cada informação nova do usuário:
- Compare com a base de conhecimento
- Se contradiz: levante imediatamente com referência ao chunk
- Se é informação nova (não existe na base): aceite e marque como tal
- Se é vago: peça especificidade

### Fase 4 — Geração
Quando o checklist tiver todos os campos obrigatórios preenchidos,
gere o card completo. Antes de finalizar, faça validação cruzada
com a base e liste todas as observações/contradições.

## Checklist de campos (use internamente)

Obrigatórios (não gere o card sem eles):
- [ ] Persona (quem usa)
- [ ] Ação (o que faz)
- [ ] Benefício (por que faz)
- [ ] Pelo menos 1 regra de negócio
- [ ] Fluxo principal (pelo menos 3 passos)
- [ ] Pelo menos 2 critérios de aceite
- [ ] Definição de escopo (dentro e fora)

Desejáveis (cobre se possível, mas não bloqueie):
- [ ] Fluxos alternativos
- [ ] Fluxos de exceção/erro
- [ ] Integrações
- [ ] Requisitos não funcionais
- [ ] Critérios técnicos

## Comportamento

- Seja direto e objetivo. Não seja excessivamente formal.
- Quando cobrar informação, explique POR QUE ela é necessária
  (impacto no downstream: prototipação, desenvolvimento, QA).
- Nunca invente informação. Se não sabe, diga que não sabe.
- Use o campo de confiança dos chunks para calibrar: informação
  de baixa confiança deve ser destacada ao usuário para validação.
- Quando gerar o card, não simplifique. Mantenha o nível de detalhe
  que o template exige.
"""

GLOSSARY = {
    "devolução": ["estorno", "reversão", "return", "devolucao"],
    "cancelamento": ["rescisão", "churn", "cancellation"],
    "PJ": ["empresa", "corporativo", "B2B", "pessoa jurídica"],
    "PF": ["consumidor", "pessoa física", "B2C"],
    "checkout": ["pagamento", "payment", "finalização de compra"],
    "pedido": ["order", "compra"],
    "SLA": ["tempo de resposta", "latência", "performance"],
    "webhook": ["callback", "notificação", "evento"],
}
```

### 5.2 — Tools do agente (`src/agent/tools.py`)

O agente tem 3 tools:

```python
AGENT_TOOLS = [
    {
        "name": "search_knowledge_base",
        "description": """Busca na base de conhecimento central.
Use SEMPRE os filtros de metadados para reduzir o universo antes da busca textual.
Se o resultado for insuficiente, relaxe os filtros e reformule o texto usando sinônimos do glossário.
Se ainda insuficiente, informe ao usuário.""",
        "parameters": {
            "text": "Texto livre para busca (use termos específicos, não frases longas)",
            "feature": "Filtro por feature (opcional, ex: devolucao_produtos)",
            "domain": "Filtro por domínio (opcional, ex: pos_venda)",
            "chunk_types": "Lista de tipos a buscar (opcional, ex: ['regra_negocio', 'fluxo_usuario'])",
            "confidence_min": "Confiança mínima: high, medium, low (opcional)",
            "tags": "Lista de tags para filtrar (opcional)",
            "top_k": "Quantidade de resultados (default: 10)"
        }
    },
    {
        "name": "get_feature_manifest",
        "description": """Lista todas as features conhecidas na base com estatísticas.
Use no início da conversa para verificar se a feature solicitada existe na base
e quantos chunks de cada tipo estão disponíveis.""",
        "parameters": {}
    },
    {
        "name": "generate_card",
        "description": """Gera o card completo no template padronizado.
Só chame quando o checklist tiver todos os campos obrigatórios preenchidos.
Recebe o working memory como input e gera o arquivo markdown.""",
        "parameters": {
            "working_memory": "JSON com todos os campos coletados durante a conversa"
        }
    }
]
```

### 5.3 — Working Memory (`src/agent/memory.py`)

```python
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import json

@dataclass
class WorkingMemory:
    """Estado da especificação em andamento.
    
    Atualizado a cada turno. Serve como fonte da verdade
    para o que já foi coletado/decidido na conversa.
    """

    # Metadados da feature
    feature: Optional[str] = None
    domain: Optional[str] = None
    is_new_feature: Optional[bool] = None
    stakeholders: List[str] = field(default_factory=list)

    # User Story
    persona: Optional[str] = None
    action: Optional[str] = None
    benefit: Optional[str] = None
    context_description: Optional[str] = None

    # Regras de negócio coletadas
    business_rules: List[Dict] = field(default_factory=list)
    # Formato: {"id": "RN-01", "rule": "...", "conditions": "...", "confidence": "high", "source": "base|usuario"}

    # Fluxos
    main_flow: List[str] = field(default_factory=list)
    alternative_flows: List[Dict] = field(default_factory=list)
    error_flows: List[Dict] = field(default_factory=list)

    # Critérios
    acceptance_criteria_product: List[Dict] = field(default_factory=list)
    acceptance_criteria_technical: List[Dict] = field(default_factory=list)
    non_acceptance_criteria: List[Dict] = field(default_factory=list)

    # Integrações
    integrations: List[Dict] = field(default_factory=list)

    # Requisitos não funcionais
    nfr: List[Dict] = field(default_factory=list)

    # Escopo
    in_scope: List[str] = field(default_factory=list)
    out_of_scope: List[Dict] = field(default_factory=list)  # {"item": "...", "reason": "..."}

    # Observações e contradições
    observations: List[Dict] = field(default_factory=list)
    # Formato: {"type": "contradiction|ambiguity|missing", "description": "...", "impact": "..."}

    # Referências da base
    knowledge_refs: List[Dict] = field(default_factory=list)
    # Formato: {"chunk_id": "...", "title": "...", "confidence": "...", "used_for": "..."}

    # Cards filhos propostos
    child_cards: List[Dict] = field(default_factory=list)

    def get_checklist_status(self) -> Dict[str, bool]:
        """Retorna status do checklist de campos obrigatórios."""
        return {
            "persona": self.persona is not None,
            "action": self.action is not None,
            "benefit": self.benefit is not None,
            "business_rules": len(self.business_rules) >= 1,
            "main_flow": len(self.main_flow) >= 3,
            "acceptance_criteria": (
                len(self.acceptance_criteria_product) +
                len(self.acceptance_criteria_technical) >= 2
            ),
            "scope_defined": (
                len(self.in_scope) >= 1 and
                len(self.out_of_scope) >= 1
            ),
        }

    def get_missing_fields(self) -> List[str]:
        """Retorna campos obrigatórios que ainda faltam."""
        status = self.get_checklist_status()
        return [field for field, done in status.items() if not done]

    def is_ready_to_generate(self) -> bool:
        """Verifica se todos os campos obrigatórios estão preenchidos."""
        return all(self.get_checklist_status().values())

    def to_json(self) -> str:
        """Serializa para JSON (para salvar em disco ou injetar no prompt)."""
        return json.dumps(vars(self), indent=2, ensure_ascii=False)

    def get_compact_summary(self) -> str:
        """Resumo compacto para injeção no contexto quando o histórico
        de conversa fica grande demais."""
        missing = self.get_missing_fields()
        status = self.get_checklist_status()
        filled = sum(1 for v in status.values() if v)
        total = len(status)

        summary = f"## Estado da especificação ({filled}/{total} campos obrigatórios)\n"
        summary += f"Feature: {self.feature or 'NÃO DEFINIDA'}\n"
        summary += f"Domain: {self.domain or 'NÃO DEFINIDO'}\n"
        if self.persona:
            summary += f"Persona: {self.persona}\n"
        summary += f"Regras de negócio: {len(self.business_rules)}\n"
        summary += f"Passos no fluxo principal: {len(self.main_flow)}\n"
        summary += f"Critérios de aceite: {len(self.acceptance_criteria_product) + len(self.acceptance_criteria_technical)}\n"
        summary += f"Contradições detectadas: {len([o for o in self.observations if o.get('type') == 'contradiction'])}\n"
        if missing:
            summary += f"FALTANDO: {', '.join(missing)}\n"
        return summary
```

### 5.4 — Gerador de cards (`src/output/card_generator.py`)

```python
import os
from src.agent.memory import WorkingMemory

def generate_card_markdown(memory: WorkingMemory, output_dir: str) -> str:
    """Gera o arquivo Markdown do card seguindo o template Azure DevOps.
    
    Retorna o caminho do arquivo gerado.
    """
    card_id = f"{memory.feature.upper().replace('_', '-')}-001"
    filename = f"{card_id}.md"
    filepath = os.path.join(output_dir, filename)

    md = []
    md.append(f"# [{card_id}] {memory.action or 'User Story'}\n")

    # --- Metadados ---
    md.append("## Metadados\n")
    md.append(f"| Campo | Valor |")
    md.append(f"|-------|-------|")
    md.append(f"| **Feature** | {memory.feature} |")
    md.append(f"| **Domínio** | {memory.domain} |")
    md.append(f"| **Stakeholders** | {', '.join(memory.stakeholders) if memory.stakeholders else 'N/A'} |")
    md.append(f"| **Prioridade** | A definir pelo PO |")
    md.append(f"| **Estimativa** | A definir pelo time |")
    md.append("")

    # --- Contexto ---
    md.append("## Contexto\n")
    md.append(memory.context_description or "[Contexto não fornecido]")
    md.append("")

    # --- User Story ---
    md.append("## User Story\n")
    md.append(f"**Como** {memory.persona or '[persona]'},")
    md.append(f"**eu quero** {memory.action or '[ação]'},")
    md.append(f"**para que** {memory.benefit or '[benefício]'}.")
    md.append("")

    # --- Regras de negócio ---
    md.append("## Regras de negócio\n")
    md.append("| ID | Regra | Condições / Exceções | Confiança |")
    md.append("|-----|-------|----------------------|-----------|")
    for rule in memory.business_rules:
        conf_icon = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(rule.get("confidence", "medium"), "🟡")
        md.append(f"| {rule['id']} | {rule['rule']} | {rule.get('conditions', 'Sem exceções conhecidas')} | {conf_icon} {rule.get('confidence', 'medium').capitalize()} |")
    md.append("")
    md.append("> 🟢 Alta = documentação formal | 🟡 Média = decisão em reunião | 🔴 Baixa = menção informal\n")

    # --- Fluxo do usuário ---
    md.append("## Fluxo do usuário\n")
    md.append("### Fluxo principal\n")
    for i, step in enumerate(memory.main_flow, 1):
        md.append(f"{i}. {step}")
    md.append("")

    if memory.alternative_flows:
        md.append("### Fluxos alternativos\n")
        for flow in memory.alternative_flows:
            md.append(f"**{flow['id']}:** {flow['condition']} → {flow['behavior']}")
        md.append("")

    if memory.error_flows:
        md.append("### Fluxos de exceção / erro\n")
        for flow in memory.error_flows:
            md.append(f"**{flow['id']}:** {flow['condition']} → {flow['response']} → {flow.get('user_sees', '')}")
        md.append("")

    # --- Integrações ---
    if memory.integrations:
        md.append("## Integrações\n")
        md.append("| Sistema / Módulo | Tipo | Descrição |")
        md.append("|------------------|------|-----------|")
        for intg in memory.integrations:
            md.append(f"| {intg['system']} | {intg['type']} | {intg['description']} |")
        md.append("")

    # --- Requisitos não funcionais ---
    if memory.nfr:
        md.append("## Requisitos não funcionais\n")
        md.append("| Categoria | Requisito | Métrica |")
        md.append("|-----------|-----------|---------|")
        for req in memory.nfr:
            md.append(f"| {req['category']} | {req['requirement']} | {req['metric']} |")
        md.append("")

    # --- Escopo ---
    md.append("## Definição de escopo\n")
    md.append("### Dentro do escopo\n")
    for item in memory.in_scope:
        md.append(f"- {item}")
    md.append("")
    md.append("### Fora do escopo\n")
    for item in memory.out_of_scope:
        md.append(f"- {item['item']} — *Motivo: {item['reason']}*")
    md.append("")

    # --- Critérios de aceite (campo separado no Azure DevOps) ---
    md.append("## Critérios de aceite\n")
    md.append("### Produto\n")
    for ca in memory.acceptance_criteria_product:
        md.append(f"- [ ] **[{ca['id']}]** Dado {ca['given']}, quando {ca['when']}, então {ca['then']}.")
    md.append("")

    if memory.acceptance_criteria_technical:
        md.append("### Técnicos\n")
        for ct in memory.acceptance_criteria_technical:
            md.append(f"- [ ] **[{ct['id']}]** {ct['criteria']}")
        md.append("")

    if memory.non_acceptance_criteria:
        md.append("### Critérios de não-aceite (o que NÃO deve acontecer)\n")
        for cna in memory.non_acceptance_criteria:
            md.append(f"- [ ] **[{cna['id']}]** {cna['criteria']}")
        md.append("")

    # --- Observações e ambiguidades ---
    if memory.observations:
        md.append("## Observações e ambiguidades\n")
        for obs in memory.observations:
            icon = {"contradiction": "⚠️", "ambiguity": "⚠️", "missing": "ℹ️"}.get(obs["type"], "ℹ️")
            md.append(f"> {icon} **{obs['type'].upper()}:** {obs['description']}")
            md.append(f"> **Impacto se não resolvido:** {obs['impact']}\n")
        md.append("")

    # --- Referências ---
    if memory.knowledge_refs:
        md.append("## Referências da base de conhecimento\n")
        md.append("| Chunk | Tipo | Confiança | Data |")
        md.append("|-------|------|-----------|------|")
        for ref in memory.knowledge_refs:
            md.append(f"| {ref['title']} | {ref.get('chunk_type', '-')} | {ref['confidence']} | {ref.get('date', '-')} |")
        md.append("")

    # --- Cards filhos ---
    if memory.child_cards:
        md.append("## Cards filhos\n")
        md.append("| ID | Título | Motivo da separação |")
        md.append("|----|--------|---------------------|")
        for child in memory.child_cards:
            md.append(f"| {child['id']} | {child['title']} | {child['reason']} |")
        md.append("")

    # Escrever arquivo
    content = "\n".join(md)
    os.makedirs(output_dir, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    # Gerar cards filhos se houver
    for child in memory.child_cards:
        child_filepath = os.path.join(output_dir, f"{child['id']}.md")
        with open(child_filepath, "w", encoding="utf-8") as f:
            f.write(f"# [{child['id']}] {child['title']}\n\n")
            f.write(f"**Parent:** [{card_id}]({filename})\n\n")
            f.write(f"**Motivo da separação:** {child['reason']}\n\n")
            f.write("## [A ser especificado]\n\n")
            f.write("Este card filho foi gerado automaticamente. ")
            f.write("Necessita especificação completa.\n")

    return filepath
```

### 5.5 — Loop principal do agente (`src/agent/agent.py`)

```python
"""
Loop principal do agente para o MVP.

Para o MVP, o agente roda como CLI interativo.
Futuro: FastAPI com WebSocket para interface web.

O agente é um loop ReAct:
1. Recebe mensagem do usuário
2. Monta o prompt com: system prompt + working memory + últimos N turnos
3. Chama o LLM
4. Se o LLM pediu uma tool: executa e volta ao passo 3
5. Se o LLM respondeu ao usuário: mostra e volta ao passo 1
"""

import json
from src.agent.memory import WorkingMemory
from src.agent.prompts import AGENT_SYSTEM_PROMPT, GLOSSARY
from src.agent.tools import AGENT_TOOLS
from src.knowledge.search import KnowledgeBaseSearch, SearchQuery
from src.knowledge.manifest import get_feature_manifest
from src.output.card_generator import generate_card_markdown

class SpecAgent:
    def __init__(self, llm_client, db_path: str, output_dir: str):
        self.llm = llm_client
        self.search = KnowledgeBaseSearch(db_path)
        self.memory = WorkingMemory()
        self.output_dir = output_dir
        self.conversation_history = []
        self.max_history_turns = 20  # Compactar após isso

    async def chat(self, user_message: str) -> str:
        """Processa uma mensagem do usuário e retorna a resposta do agente."""

        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        # Compactar histórico se necessário
        if len(self.conversation_history) > self.max_history_turns:
            self._compact_history()

        # Montar contexto
        context = self._build_context()

        # Loop ReAct
        while True:
            response = await self.llm.generate(
                system=AGENT_SYSTEM_PROMPT,
                messages=context,
                tools=AGENT_TOOLS,
            )

            # Se é tool call, executar
            if response.has_tool_call:
                tool_result = await self._execute_tool(
                    response.tool_name,
                    response.tool_params
                )
                context.append({
                    "role": "assistant",
                    "content": response.text,
                    "tool_call": response.tool_call
                })
                context.append({
                    "role": "tool",
                    "content": json.dumps(tool_result, ensure_ascii=False)
                })
                continue

            # Se é resposta ao usuário, retornar
            self.conversation_history.append({
                "role": "assistant",
                "content": response.text
            })
            return response.text

    async def _execute_tool(self, tool_name: str, params: dict) -> dict:
        """Executa uma tool e retorna o resultado."""

        if tool_name == "search_knowledge_base":
            query = SearchQuery(
                text=params.get("text", ""),
                feature=params.get("feature"),
                domain=params.get("domain"),
                chunk_types=params.get("chunk_types"),
                confidence_min=params.get("confidence_min"),
                tags=params.get("tags"),
                top_k=params.get("top_k", 10),
            )
            results = self.search.search(query)
            
            # Salvar referências no working memory
            for r in results:
                self.memory.knowledge_refs.append({
                    "chunk_id": r.chunk_id,
                    "title": r.title,
                    "confidence": r.confidence,
                    "chunk_type": r.chunk_type,
                    "date": r.created_at,
                })

            return {
                "total_results": len(results),
                "chunks": [
                    {
                        "title": r.title,
                        "content": r.content,
                        "chunk_type": r.chunk_type,
                        "confidence": r.confidence,
                        "tags": r.tags,
                    }
                    for r in results
                ]
            }

        elif tool_name == "get_feature_manifest":
            import sqlite3
            conn = sqlite3.connect(self.search.db_path)
            conn.row_factory = sqlite3.Row
            manifest = get_feature_manifest(conn)
            conn.close()
            return {"features": manifest}

        elif tool_name == "generate_card":
            # Atualizar working memory com dados do params se fornecidos
            wm_data = params.get("working_memory", {})
            if isinstance(wm_data, str):
                wm_data = json.loads(wm_data)
            # Merge com working memory existente
            for key, value in wm_data.items():
                if hasattr(self.memory, key) and value:
                    setattr(self.memory, key, value)

            filepath = generate_card_markdown(self.memory, self.output_dir)
            return {
                "status": "success",
                "filepath": filepath,
                "missing_fields": self.memory.get_missing_fields(),
            }

        return {"error": f"Tool desconhecida: {tool_name}"}

    def _build_context(self) -> list:
        """Monta o contexto para o LLM: working memory + histórico."""
        context = []

        # Injetar working memory como primeiro contexto
        wm_summary = self.memory.get_compact_summary()
        if wm_summary:
            context.append({
                "role": "user",
                "content": f"[ESTADO ATUAL DA ESPECIFICAÇÃO]\n{wm_summary}"
            })
            context.append({
                "role": "assistant",
                "content": "Entendido, continuando a especificação."
            })

        # Adicionar histórico de conversa
        context.extend(self.conversation_history)

        return context

    def _compact_history(self):
        """Compacta turnos antigos mantendo apenas as decisões."""
        # Manter os últimos 10 turnos intactos
        keep = self.conversation_history[-10:]
        old = self.conversation_history[:-10]

        # Resumir os turnos antigos (para o MVP, simplesmente descarta)
        # Em produção: chamar LLM para sumarizar as decisões
        self.conversation_history = keep
```

### Como testar

```bash
# Rodar agente em modo CLI
python scripts/run_agent.py

# Conversa de teste:
# > Preciso especificar a funcionalidade de devolução de produtos
# [Agente deve perguntar: domínio, é nova feature, stakeholders]
# > É uma feature do domínio de pós-venda, evolução de existente, stakeholders são Ana e Carlos
# [Agente deve buscar na base e apresentar contexto]
# > Quero focar na devolução para pessoa física com prazo de 30 dias
# [Agente deve trazer regras da base e perguntar detalhes]
# ... continuar até gerar o card ...

# Verificar card gerado
cat data/output/cards/DEVOLUCAO-PRODUTOS-001.md
```

---

## ETAPA 6 — Integração e teste end-to-end
**Tempo estimado: 1-2 horas**
**Prioridade: ALTA**
**Dependência: Etapas 1-5**
**Teste: fluxo completo sem intervenção manual**

### O que fazer

1. Script que roda tudo em sequência:
   - Cria dados bronze (se não existem)
   - Roda pipeline de ingestão
   - Verifica base Silver (count, tipos, manifesto)
   - Inicia agente

2. Teste de conversação automatizado (opcional):
   Script que simula uma conversa pré-definida com o agente para validar que o fluxo funciona sem intervenção.

### Script de setup completo (`scripts/setup_and_run.sh`)

```bash
#!/bin/bash
set -e

echo "=== MVP Knowledge Base + Spec Agent ==="

# 1. Instalar dependências
echo ">>> Instalando dependências..."
pip install -r requirements.txt

# 2. Criar dados bronze (se não existem)
if [ ! -d "data/bronze/calls" ]; then
    echo ">>> Gerando dados simulados..."
    python scripts/seed_bronze.py
fi

# 3. Rodar pipeline de ingestão
echo ">>> Rodando pipeline de ingestão..."
python scripts/run_ingestion.py

# 4. Verificar base Silver
echo ">>> Verificando base Silver..."
python -c "
import sqlite3
conn = sqlite3.connect('data/silver/knowledge.db')
total = conn.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]
features = conn.execute('SELECT DISTINCT feature FROM chunks').fetchall()
print(f'Base Silver: {total} chunks, {len(features)} features')
for f in features:
    count = conn.execute('SELECT COUNT(*) FROM chunks WHERE feature = ?', (f[0],)).fetchone()[0]
    print(f'  {f[0]}: {count} chunks')
"

# 5. Iniciar agente
echo ">>> Iniciando Spec Agent..."
echo ">>> Digite suas mensagens abaixo. Ctrl+C para sair."
python scripts/run_agent.py
```

### Como testar

```bash
# Rodar tudo
chmod +x scripts/setup_and_run.sh
./scripts/setup_and_run.sh

# Verificar output
ls -la data/output/cards/
# Esperado: pelo menos 1 arquivo .md com o card completo

# Verificar conteúdo do card
cat data/output/cards/*.md | head -100
# Esperado: card seguindo o template completo com todas as seções
```

---

## Checklist final do MVP

- [ ] **Etapa 1** — Dados bronze simulados existem (5 arquivos)
- [ ] **Etapa 2** — Schema SQLite + FTS5 criado e funcional
- [ ] **Etapa 3** — Interface de busca retorna resultados corretos
- [ ] **Etapa 4** — Pipeline de ingestão processa bronze → silver
- [ ] **Etapa 5** — Agente conversa, busca na base, gera card
- [ ] **Etapa 6** — Fluxo end-to-end funciona sem erros
- [ ] **Demo** — Card gerado em .md é completo e legível

## Configuração de LLM

Para o MVP, configure no `src/config.py`:

```python
# Escolha UM provider:

# Opção A: Anthropic
LLM_PROVIDER = "anthropic"
LLM_MODEL_INGESTION = "claude-haiku-4-5-20251001"  # Barato para classificação
LLM_MODEL_AGENT = "claude-sonnet-4-6"  # Inteligente para o agente

# Opção B: Azure OpenAI
LLM_PROVIDER = "azure_openai"
LLM_MODEL_INGESTION = "gpt-4o-mini"
LLM_MODEL_AGENT = "gpt-4o"

# Paths
BRONZE_DIR = "data/bronze"
SILVER_DB = "data/silver/knowledge.db"
OUTPUT_DIR = "data/output/cards"
```

## Ordem de execução amanhã (quinta-feira)

1. **08:00-09:00** — Etapa 1 (dados simulados) + Etapa 2 (schema)
2. **09:00-10:30** — Etapa 3 (busca) — testar isoladamente
3. **10:30-13:00** — Etapa 4 (pipeline de ingestão) — mais demorado por causa dos prompts do LLM
4. **13:00-14:00** — Pausa + teste das etapas 1-4 integradas
5. **14:00-17:30** — Etapa 5 (agente completo)
6. **17:30-19:00** — Etapa 6 (integração + testes end-to-end)
7. **19:00-20:00** — Buffer para bugs e ajustes finais
