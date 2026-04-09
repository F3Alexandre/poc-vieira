# SPEC — Etapa 2: Schema da Base Silver (SQLite + FTS5)

## Objetivo

Criar a base de dados Silver usando SQLite com FTS5 (Full-Text Search 5) como motor de busca textual. Esta base armazena os chunks de conhecimento processados pelo pipeline de ingestão e serve como fonte de dados para o agente de especificação.

A etapa inclui: schema do banco, interface de busca abstrata (filtro metadados + FTS5), manifesto de features, e cache em memória.

## Dependências

- **Python 3.11+**
- **SQLite 3.35+** (FTS5 habilitado — vem por padrão no Python 3.11+)
- **Nenhuma dependência externa** para esta etapa (zero pip install)

Verificar que FTS5 está disponível antes de começar:

```bash
python -c "
import sqlite3
conn = sqlite3.connect(':memory:')
try:
    conn.execute('CREATE VIRTUAL TABLE test USING fts5(content)')
    print('FTS5 disponível')
except:
    print('ERRO: FTS5 não disponível. Atualize o SQLite.')
"
```

## Estrutura de arquivos

```
src/
└── knowledge/
    ├── __init__.py
    ├── schema.py       # Schema, dataclass Chunk, init_db, insert/update/delete
    ├── search.py        # Interface de busca abstrata (SearchQuery → SearchResult)
    ├── manifest.py      # Manifesto de features (view materializado)
    └── cache.py         # Cache em memória com TTL
data/
└── silver/
    └── knowledge.db     # Criado em runtime pelo init_db()
```

---

## Parte 1: Schema e operações CRUD (`src/knowledge/schema.py`)

### Enums controlados

Estes enums são a taxonomia da base de conhecimento. Eles devem ser importáveis por outros módulos (pipeline de ingestão, agente) para validação.

```python
"""
Enums controlados da base de conhecimento.
Qualquer novo valor deve ser adicionado aqui — nunca aceitar texto livre
nos campos tipados.
"""

CHUNK_TYPES = [
    "regra_negocio",             # Lógica de negócio, condições, exceções
    "fluxo_usuario",             # Passo-a-passo de interação do usuário
    "decisao_tecnica",           # Escolhas de arquitetura, stack, padrões
    "requisito_nao_funcional",   # Performance, segurança, acessibilidade
    "definicao_escopo",          # O que está dentro e fora do escopo
    "restricao",                 # Limitações conhecidas, débitos técnicos
    "criterio_aceite",           # Condições de aceite já definidas
    "integracao",                # Pontos de contato com outros sistemas/features
    "vocabulario",               # Definições de termos do domínio
    "contexto_negocio",          # Background, motivação, justificativa
]

SOURCE_TYPES = [
    "transcricao_reuniao",       # Grooming, refinamento, call de alinhamento
    "documento_produto",         # PRD, spec, wiki
    "documento_cliente",         # Requisitos do cliente, contratos
    "chat",                      # Slack, Teams, mensagens
    "card_devops",               # Cards do Azure DevOps existentes
    "documentacao_tecnica",      # READMEs, ADRs, diagramas
    "decisao_registro",          # Ata de reunião, registro formal
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
]

# Ordem de prioridade para confiança (usado em filtros e ranking)
CONFIDENCE_ORDER = {"high": 3, "medium": 2, "low": 1}
```

### Dataclass `Chunk`

O Chunk é a unidade atômica de conhecimento. Cada chunk tem frontmatter (metadados estruturados) e corpo (texto completo).

```python
import uuid
import json
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class Chunk:
    """Unidade atômica de conhecimento na camada Silver.
    
    Cada chunk é uma unidade lógica de informação que pode ser
    compreendida isoladamente. Um documento fonte pode gerar
    múltiplos chunks.
    
    Campos de lista (tags, participants, related_features) são
    armazenados como JSON arrays no SQLite.
    """
    
    # Identificação
    id: str = ""                              # UUID, gerado automaticamente se vazio
    title: str = ""                           # Título descritivo (max 200 chars)
    
    # Conteúdo
    content: str = ""                         # Texto completo, SEM sumarização
    
    # Classificação (todos obrigatórios)
    feature: str = ""                         # Enum — identificador da funcionalidade
    domain: str = ""                          # Enum — domínio de negócio
    chunk_type: str = ""                      # Enum — tipo da informação
    
    # Origem
    source_type: str = ""                     # Enum — de onde veio
    source_ref: str = ""                      # Caminho do arquivo bronze original
    
    # Qualidade
    confidence: str = "medium"                # high | medium | low
    
    # Enriquecimento
    tags: List[str] = field(default_factory=list)               # Termos-chave para busca
    participants: List[str] = field(default_factory=list)        # Pessoas envolvidas
    related_features: List[str] = field(default_factory=list)    # Features conectadas
    
    # Metadados
    language: str = "pt-br"
    status: str = "active"                    # active | deprecated | superseded
    superseded_by: Optional[str] = None       # ID do chunk substituto
    
    # Timestamps
    created_at: str = ""
    updated_at: str = ""
    
    def __post_init__(self):
        """Auto-preenche id e timestamps se vazios."""
        if not self.id:
            self.id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
    
    def validate(self) -> List[str]:
        """Valida o chunk e retorna lista de erros (vazia se válido)."""
        errors = []
        if not self.title:
            errors.append("title é obrigatório")
        if not self.content:
            errors.append("content é obrigatório")
        if self.feature and not self.feature.replace("_", "").isalnum():
            errors.append(f"feature deve ser snake_case alfanumérico, recebido: {self.feature}")
        if self.chunk_type and self.chunk_type not in CHUNK_TYPES:
            errors.append(f"chunk_type inválido: {self.chunk_type}. Válidos: {CHUNK_TYPES}")
        if self.source_type and self.source_type not in SOURCE_TYPES:
            errors.append(f"source_type inválido: {self.source_type}. Válidos: {SOURCE_TYPES}")
        if self.confidence not in CONFIDENCE_LEVELS:
            errors.append(f"confidence inválido: {self.confidence}. Válidos: {CONFIDENCE_LEVELS}")
        if self.domain and self.domain not in DOMAINS:
            errors.append(f"domain inválido: {self.domain}. Válidos: {DOMAINS}")
        if len(self.title) > 200:
            errors.append(f"title excede 200 chars: {len(self.title)}")
        return errors
    
    def to_db_tuple(self) -> tuple:
        """Converte para tupla de inserção no SQLite."""
        return (
            self.id, self.title, self.content, self.feature,
            self.domain, self.chunk_type, self.source_type,
            self.source_ref, self.confidence,
            json.dumps(self.tags, ensure_ascii=False),
            json.dumps(self.participants, ensure_ascii=False),
            json.dumps(self.related_features, ensure_ascii=False),
            self.language, self.status, self.superseded_by,
            self.created_at, self.updated_at,
        )
    
    @classmethod
    def from_db_row(cls, row: dict) -> "Chunk":
        """Cria Chunk a partir de um Row do SQLite."""
        return cls(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            feature=row["feature"],
            domain=row["domain"],
            chunk_type=row["chunk_type"],
            source_type=row["source_type"],
            source_ref=row["source_ref"],
            confidence=row["confidence"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
            participants=json.loads(row["participants"]) if row["participants"] else [],
            related_features=json.loads(row["related_features"]) if row["related_features"] else [],
            language=row["language"],
            status=row["status"],
            superseded_by=row["superseded_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
```

### SQL de criação do banco

```python
"""SQL statements para criação e manutenção do banco."""

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
    tags TEXT NOT NULL DEFAULT '[]',
    participants TEXT NOT NULL DEFAULT '[]',
    related_features TEXT NOT NULL DEFAULT '[]',
    language TEXT NOT NULL DEFAULT 'pt-br',
    status TEXT NOT NULL DEFAULT 'active',
    superseded_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

# FTS5 com tokenizer unicode61 que remove acentos para busca
# remove_diacritics=2 permite buscar "devolucao" e encontrar "devolução"
CREATE_FTS_TABLE = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    id UNINDEXED,
    title,
    content,
    tags,
    tokenize='unicode61 remove_diacritics 2'
);
"""

# Triggers mantêm o FTS sincronizado automaticamente com a tabela chunks.
# IMPORTANTE: sem esses triggers, inserções na tabela chunks NÃO aparecem
# nas buscas FTS5.
CREATE_FTS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS chunks_fts_insert
AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(id, title, content, tags)
    VALUES (new.id, new.title, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS chunks_fts_delete
AFTER DELETE ON chunks BEGIN
    DELETE FROM chunks_fts WHERE id = old.id;
END;

CREATE TRIGGER IF NOT EXISTS chunks_fts_update
AFTER UPDATE ON chunks BEGIN
    DELETE FROM chunks_fts WHERE id = old.id;
    INSERT INTO chunks_fts(id, title, content, tags)
    VALUES (new.id, new.title, new.content, new.tags);
END;
"""

# Índices para filtros de metadados (executados ANTES da busca FTS5)
# Esses índices são o que torna a busca em dois estágios eficiente:
# primeiro filtra por metadados (usa índice), depois rankeia por texto (FTS5)
CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_chunks_feature ON chunks(feature);
CREATE INDEX IF NOT EXISTS idx_chunks_domain ON chunks(domain);
CREATE INDEX IF NOT EXISTS idx_chunks_chunk_type ON chunks(chunk_type);
CREATE INDEX IF NOT EXISTS idx_chunks_status ON chunks(status);
CREATE INDEX IF NOT EXISTS idx_chunks_confidence ON chunks(confidence);
CREATE INDEX IF NOT EXISTS idx_chunks_feature_domain ON chunks(feature, domain);
CREATE INDEX IF NOT EXISTS idx_chunks_feature_type ON chunks(feature, chunk_type);
"""
```

### Funções de banco

```python
import sqlite3
import os
from typing import List, Optional
from datetime import datetime, timezone

def init_db(db_path: str) -> sqlite3.Connection:
    """Inicializa o banco com schema completo.
    
    Cria o diretório pai se não existir.
    Retorna a conexão configurada.
    
    Configurações importantes:
    - WAL mode: permite leitura concorrente durante escrita
    - row_factory: retorna Rows como dicts (acesso por nome)
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # WAL mode para melhor concorrência
    conn.execute("PRAGMA journal_mode=WAL")
    # Foreign keys (caso adicionemos relações futuras)
    conn.execute("PRAGMA foreign_keys=ON")
    
    # Criar schema
    conn.executescript(CREATE_CHUNKS_TABLE)
    conn.executescript(CREATE_FTS_TABLE)
    conn.executescript(CREATE_FTS_TRIGGERS)
    conn.executescript(CREATE_INDEXES)
    conn.commit()
    
    return conn


def insert_chunk(conn: sqlite3.Connection, chunk: Chunk) -> str:
    """Insere um chunk na base. Retorna o id do chunk inserido.
    
    Valida o chunk antes de inserir. Levanta ValueError se inválido.
    """
    errors = chunk.validate()
    if errors:
        raise ValueError(f"Chunk inválido: {'; '.join(errors)}")
    
    conn.execute("""
        INSERT INTO chunks (
            id, title, content, feature, domain, chunk_type,
            source_type, source_ref, confidence, tags, participants,
            related_features, language, status, superseded_by,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, chunk.to_db_tuple())
    conn.commit()
    
    return chunk.id


def insert_chunks_batch(conn: sqlite3.Connection, chunks: List[Chunk]) -> int:
    """Insere múltiplos chunks em uma transação.
    
    Mais eficiente que inserir um por um.
    Retorna quantidade de chunks inseridos.
    Levanta ValueError no primeiro chunk inválido (nenhum é inserido).
    """
    # Validar todos antes de inserir
    for i, chunk in enumerate(chunks):
        errors = chunk.validate()
        if errors:
            raise ValueError(f"Chunk {i} ('{chunk.title}') inválido: {'; '.join(errors)}")
    
    with conn:  # Transação automática
        conn.executemany("""
            INSERT INTO chunks (
                id, title, content, feature, domain, chunk_type,
                source_type, source_ref, confidence, tags, participants,
                related_features, language, status, superseded_by,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [c.to_db_tuple() for c in chunks])
    
    return len(chunks)


def get_chunk_by_id(conn: sqlite3.Connection, chunk_id: str) -> Optional[Chunk]:
    """Busca um chunk por ID. Retorna None se não encontrado."""
    cursor = conn.execute("SELECT * FROM chunks WHERE id = ?", (chunk_id,))
    row = cursor.fetchone()
    if row is None:
        return None
    return Chunk.from_db_row(row)


def update_chunk_status(
    conn: sqlite3.Connection,
    chunk_id: str,
    new_status: str,
    superseded_by: Optional[str] = None
) -> bool:
    """Atualiza o status de um chunk. Retorna True se encontrou e atualizou."""
    if new_status not in ["active", "deprecated", "superseded"]:
        raise ValueError(f"Status inválido: {new_status}")
    
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute("""
        UPDATE chunks
        SET status = ?, superseded_by = ?, updated_at = ?
        WHERE id = ?
    """, (new_status, superseded_by, now, chunk_id))
    conn.commit()
    
    return cursor.rowcount > 0


def get_db_stats(conn: sqlite3.Connection) -> dict:
    """Retorna estatísticas gerais do banco para health check."""
    stats = {}
    
    stats["total_chunks"] = conn.execute(
        "SELECT COUNT(*) FROM chunks"
    ).fetchone()[0]
    
    stats["active_chunks"] = conn.execute(
        "SELECT COUNT(*) FROM chunks WHERE status = 'active'"
    ).fetchone()[0]
    
    stats["chunks_by_type"] = {
        row[0]: row[1] for row in conn.execute(
            "SELECT chunk_type, COUNT(*) FROM chunks WHERE status = 'active' GROUP BY chunk_type"
        ).fetchall()
    }
    
    stats["chunks_by_feature"] = {
        row[0]: row[1] for row in conn.execute(
            "SELECT feature, COUNT(*) FROM chunks WHERE status = 'active' GROUP BY feature"
        ).fetchall()
    }
    
    stats["chunks_by_confidence"] = {
        row[0]: row[1] for row in conn.execute(
            "SELECT confidence, COUNT(*) FROM chunks WHERE status = 'active' GROUP BY confidence"
        ).fetchall()
    }
    
    return stats
```

---

## Parte 2: Interface de busca (`src/knowledge/search.py`)

A busca funciona em dois estágios:
1. **Filtro por metadados** (SQL com índices) — reduz o universo de busca
2. **Ranking por relevância textual** (FTS5) — ordena o subset por relevância

Se os filtros de metadados já reduzirem a poucos chunks (< top_k), o FTS5 é opcional — os chunks podem ser injetados direto no contexto do LLM.

### Dataclasses de entrada e saída

```python
from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class SearchQuery:
    """Query estruturada que o agente constrói.
    
    O agente monta esta query baseado na conversa com o usuário,
    usando o glossário de sinônimos para expandir termos.
    
    Exemplo: usuário diz "regras de estorno para empresa"
    → agente monta: SearchQuery(
        text="estorno devolução reembolso",
        feature="devolucao_produtos",
        domain="pos_venda",
        chunk_types=["regra_negocio"],
        tags=["pj", "empresa", "enterprise"]
    )
    """
    text: str = ""                                  # Texto livre para FTS5
    feature: Optional[str] = None                   # Filtro exato por feature
    domain: Optional[str] = None                    # Filtro exato por domínio
    chunk_types: Optional[List[str]] = None         # Filtro IN por tipo(s)
    confidence_min: Optional[str] = None            # Filtro mínimo de confiança
    tags: Optional[List[str]] = None                # Filtro — chunk deve ter ALGUMA tag
    status: str = "active"                          # Default: só chunks ativos
    top_k: int = 10                                 # Quantidade máxima de resultados


@dataclass
class SearchResult:
    """Resultado de uma busca — um chunk com metadados de ranking."""
    chunk_id: str
    title: str
    content: str
    feature: str
    domain: str
    chunk_type: str
    confidence: str
    tags: List[str]
    source_type: str
    source_ref: str
    created_at: str
    relevance_rank: int              # Posição no ranking (1 = mais relevante)
    participants: List[str] = field(default_factory=list)
    related_features: List[str] = field(default_factory=list)
    
    def token_estimate(self) -> int:
        """Estimativa grosseira de tokens (1 token ≈ 4 chars em português)."""
        return len(self.content) // 4
```

### Classe `KnowledgeBaseSearch`

```python
import sqlite3
import json
import hashlib
import time
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class KnowledgeBaseSearch:
    """Interface de busca abstrata para a base de conhecimento.
    
    ABSTRAÇÃO IMPORTANTE: esta classe é o contrato entre o agente e a base.
    Hoje a implementação é SQLite + FTS5.
    Futuro: pode ser trocada por PostgreSQL (pg_textsearch + pgvector)
    sem mudar a interface pública (search, get_feature_context).
    
    Estratégia de busca em dois estágios:
    1. Filtros de metadados (SQL com índices) reduzem o universo
    2. FTS5 rankeia por relevância textual dentro do subset
    
    Se não houver texto na query, retorna filtrado por metadados
    ordenado por data (mais recente primeiro).
    """

    def __init__(self, db_path: str, cache_ttl_seconds: int = 300):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._cache: Dict[str, tuple] = {}  # hash → (timestamp, results)
        self._cache_ttl = cache_ttl_seconds

    def search(self, query: SearchQuery) -> List[SearchResult]:
        """Busca principal em dois estágios.
        
        Args:
            query: SearchQuery com filtros e texto
            
        Returns:
            Lista de SearchResult ordenada por relevância (melhor primeiro)
        """
        # 1. Verificar cache
        cache_key = self._make_cache_key(query)
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit para query: {query.text[:50]}")
            return cached

        # 2. Construir WHERE clause
        where_parts, params = self._build_where_clause(query)
        where_sql = " AND ".join(where_parts)

        # 3. Executar query
        if query.text.strip():
            # Com texto: JOIN no FTS5 para ranking
            # O FTS5 rank é negativo (mais negativo = mais relevante)
            fts_query = self._prepare_fts_query(query.text)
            sql = f"""
                SELECT c.*, fts.rank AS fts_rank
                FROM chunks c
                JOIN chunks_fts fts ON c.id = fts.id
                WHERE chunks_fts MATCH ?
                AND {where_sql}
                ORDER BY fts.rank
                LIMIT ?
            """
            all_params = [fts_query] + params + [query.top_k]
        else:
            # Sem texto: só filtros de metadados, ordenado por data
            sql = f"""
                SELECT c.*, 0 AS fts_rank
                FROM chunks c
                WHERE {where_sql}
                ORDER BY c.updated_at DESC
                LIMIT ?
            """
            all_params = params + [query.top_k]

        try:
            cursor = self.conn.execute(sql, all_params)
            rows = cursor.fetchall()
        except sqlite3.OperationalError as e:
            # FTS5 pode falhar com queries malformadas
            logger.warning(f"Erro na busca FTS5: {e}. Tentando sem FTS.")
            # Fallback: busca só por metadados
            sql = f"""
                SELECT c.*, 0 AS fts_rank
                FROM chunks c
                WHERE {where_sql}
                ORDER BY c.updated_at DESC
                LIMIT ?
            """
            cursor = self.conn.execute(sql, params + [query.top_k])
            rows = cursor.fetchall()

        # 4. Converter para SearchResult
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
                tags=json.loads(row["tags"]) if row["tags"] else [],
                source_type=row["source_type"],
                source_ref=row["source_ref"],
                created_at=row["created_at"],
                relevance_rank=i + 1,
                participants=json.loads(row["participants"]) if row["participants"] else [],
                related_features=json.loads(row["related_features"]) if row["related_features"] else [],
            ))

        # 5. Cachear
        self._put_in_cache(cache_key, results)
        
        logger.info(
            f"Busca: '{query.text[:50]}' | "
            f"filtros: feature={query.feature}, domain={query.domain}, "
            f"types={query.chunk_types} | "
            f"resultados: {len(results)}"
        )

        return results

    def get_feature_context(self, feature: str) -> List[SearchResult]:
        """Carrega TODOS os chunks ativos de uma feature.
        
        Usado na Fase 2 do agente para contextualização completa.
        Se o total de tokens couber no contexto do LLM, injeta tudo direto
        sem precisar de BM25/FTS5.
        
        Retorna ordenado por: chunk_type (regra_negocio primeiro),
        depois por confidence (high primeiro), depois por data.
        """
        cache_key = f"__feature_context__:{feature}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        cursor = self.conn.execute("""
            SELECT c.*, 0 AS fts_rank
            FROM chunks c
            WHERE c.feature = ? AND c.status = 'active'
            ORDER BY
                CASE c.chunk_type
                    WHEN 'regra_negocio' THEN 1
                    WHEN 'fluxo_usuario' THEN 2
                    WHEN 'decisao_tecnica' THEN 3
                    WHEN 'criterio_aceite' THEN 4
                    WHEN 'integracao' THEN 5
                    WHEN 'requisito_nao_funcional' THEN 6
                    WHEN 'restricao' THEN 7
                    WHEN 'definicao_escopo' THEN 8
                    WHEN 'contexto_negocio' THEN 9
                    WHEN 'vocabulario' THEN 10
                    ELSE 99
                END,
                CASE c.confidence
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 3
                END,
                c.updated_at DESC
        """, (feature,))

        results = []
        for i, row in enumerate(cursor.fetchall()):
            results.append(SearchResult(
                chunk_id=row["id"],
                title=row["title"],
                content=row["content"],
                feature=row["feature"],
                domain=row["domain"],
                chunk_type=row["chunk_type"],
                confidence=row["confidence"],
                tags=json.loads(row["tags"]) if row["tags"] else [],
                source_type=row["source_type"],
                source_ref=row["source_ref"],
                created_at=row["created_at"],
                relevance_rank=i + 1,
                participants=json.loads(row["participants"]) if row["participants"] else [],
                related_features=json.loads(row["related_features"]) if row["related_features"] else [],
            ))

        self._put_in_cache(cache_key, results)
        return results

    def estimate_feature_tokens(self, feature: str) -> int:
        """Estima tokens totais de uma feature para decidir se cabe no contexto."""
        results = self.get_feature_context(feature)
        return sum(r.token_estimate() for r in results)

    # --- Métodos internos ---

    def _build_where_clause(self, query: SearchQuery) -> tuple:
        """Constrói a cláusula WHERE com filtros de metadados.
        
        Retorna (lista_de_condições, lista_de_params).
        """
        where_parts = ["c.status = ?"]
        params = [query.status]

        if query.feature:
            where_parts.append("c.feature = ?")
            params.append(query.feature)

        if query.domain:
            where_parts.append("c.domain = ?")
            params.append(query.domain)

        if query.chunk_types:
            placeholders = ",".join(["?"] * len(query.chunk_types))
            where_parts.append(f"c.chunk_type IN ({placeholders})")
            params.extend(query.chunk_types)

        if query.confidence_min:
            min_val = CONFIDENCE_ORDER.get(query.confidence_min, 1)
            valid = [k for k, v in CONFIDENCE_ORDER.items() if v >= min_val]
            placeholders = ",".join(["?"] * len(valid))
            where_parts.append(f"c.confidence IN ({placeholders})")
            params.extend(valid)

        if query.tags:
            # OR entre tags — chunk deve conter PELO MENOS uma das tags
            tag_parts = []
            for tag in query.tags:
                tag_parts.append("c.tags LIKE ?")
                params.append(f"%{tag}%")
            where_parts.append(f"({' OR '.join(tag_parts)})")

        return where_parts, params

    def _prepare_fts_query(self, text: str) -> str:
        """Prepara o texto para query FTS5.
        
        FTS5 aceita operadores: AND, OR, NOT, NEAR, frases entre aspas.
        Para o MVP, fazemos OR implícito entre todos os termos
        (qualquer termo encontrado já gera match, mais permissivo).
        
        Remove caracteres especiais que podem quebrar a query FTS5.
        """
        # Remover caracteres que FTS5 interpreta como operadores
        cleaned = text.replace('"', '').replace("'", '').replace('(', '').replace(')', '')
        cleaned = cleaned.replace('*', '').replace('-', ' ').replace('+', ' ')
        
        # Separar em tokens e juntar com OR para busca permissiva
        tokens = [t.strip() for t in cleaned.split() if t.strip() and len(t.strip()) > 1]
        
        if not tokens:
            return text  # Fallback para o texto original
        
        # OR entre todos os termos: encontra chunks que contenham QUALQUER termo
        return " OR ".join(tokens)

    def _make_cache_key(self, query: SearchQuery) -> str:
        """Gera chave de cache determinística para uma query."""
        raw = json.dumps({
            "text": query.text,
            "feature": query.feature,
            "domain": query.domain,
            "chunk_types": sorted(query.chunk_types) if query.chunk_types else None,
            "confidence_min": query.confidence_min,
            "tags": sorted(query.tags) if query.tags else None,
            "status": query.status,
            "top_k": query.top_k,
        }, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _get_from_cache(self, key: str) -> Optional[List[SearchResult]]:
        """Retorna resultado do cache se existir e não expirado."""
        if key in self._cache:
            ts, results = self._cache[key]
            if time.time() - ts < self._cache_ttl:
                return results
            del self._cache[key]
        return None

    def _put_in_cache(self, key: str, results: List[SearchResult]):
        """Armazena resultado no cache."""
        self._cache[key] = (time.time(), results)

    def invalidate_cache(self, feature: Optional[str] = None):
        """Invalida cache. Se feature especificada, só invalida essa feature."""
        if feature:
            keys_to_remove = [
                k for k in self._cache
                if feature in str(self._cache[k])  # heurística simples
            ]
            # Sempre invalidar o feature context
            fc_key = f"__feature_context__:{feature}"
            if fc_key in self._cache:
                keys_to_remove.append(fc_key)
            for k in set(keys_to_remove):
                del self._cache[k]
        else:
            self._cache.clear()

    def close(self):
        """Fecha a conexão com o banco."""
        self.conn.close()
```

---

## Parte 3: Manifesto de features (`src/knowledge/manifest.py`)

O manifesto é um view materializado que resume o que existe na base por feature. O agente consulta no início da conversa para saber o universo de features disponíveis.

```python
import sqlite3
from typing import List, Dict

def get_feature_manifest(conn: sqlite3.Connection) -> List[Dict]:
    """Retorna resumo por feature: tipos de chunks disponíveis,
    contagem, última atualização, distribuição de confiança.
    
    Usado pelo agente para:
    1. Verificar se a feature solicitada existe na base
    2. Saber quais tipos de informação estão disponíveis
    3. Avaliar a qualidade da base (proporção de alta vs baixa confiança)
    
    Retorno exemplo:
    [
        {
            "feature": "devolucao_produtos",
            "domain": "pos_venda",
            "total_chunks": 18,
            "chunk_types": "regra_negocio,fluxo_usuario,decisao_tecnica,integracao",
            "last_updated": "2026-04-05T14:30:00Z",
            "high_confidence": 8,
            "medium_confidence": 7,
            "low_confidence": 3,
            "sources": "transcricao_reuniao,documento_produto,chat,documento_cliente"
        }
    ]
    """
    cursor = conn.execute("""
        SELECT
            feature,
            domain,
            COUNT(*) AS total_chunks,
            GROUP_CONCAT(DISTINCT chunk_type) AS chunk_types,
            MAX(updated_at) AS last_updated,
            SUM(CASE WHEN confidence = 'high' THEN 1 ELSE 0 END) AS high_confidence,
            SUM(CASE WHEN confidence = 'medium' THEN 1 ELSE 0 END) AS medium_confidence,
            SUM(CASE WHEN confidence = 'low' THEN 1 ELSE 0 END) AS low_confidence,
            GROUP_CONCAT(DISTINCT source_type) AS sources
        FROM chunks
        WHERE status = 'active'
        GROUP BY feature, domain
        ORDER BY total_chunks DESC
    """)
    return [dict(row) for row in cursor.fetchall()]


def get_feature_summary_text(conn: sqlite3.Connection) -> str:
    """Versão texto do manifesto, para injeção direta no prompt do agente.
    
    Retorna algo como:
    
    Features na base de conhecimento:
    - devolucao_produtos (pos_venda): 18 chunks | tipos: regra_negocio, fluxo_usuario, ...
      Confiança: 8 alta, 7 média, 3 baixa | Atualizado: 2026-04-05
    """
    manifest = get_feature_manifest(conn)
    
    if not manifest:
        return "A base de conhecimento está vazia. Nenhuma feature documentada."
    
    lines = ["Features na base de conhecimento:\n"]
    for f in manifest:
        types_list = f["chunk_types"].replace(",", ", ") if f["chunk_types"] else "nenhum"
        lines.append(
            f"- **{f['feature']}** ({f['domain']}): "
            f"{f['total_chunks']} chunks | "
            f"tipos: {types_list}"
        )
        lines.append(
            f"  Confiança: {f['high_confidence']} alta, "
            f"{f['medium_confidence']} média, "
            f"{f['low_confidence']} baixa | "
            f"Atualizado: {f['last_updated'][:10]}"
        )
    
    return "\n".join(lines)
```

---

## Parte 4: Testes

### Teste completo da Etapa 2

Criar o arquivo `tests/test_knowledge_base.py`:

```python
"""
Testes da Etapa 2: Schema + Busca + Manifesto.

Rodar com: python -m pytest tests/test_knowledge_base.py -v
Ou sem pytest: python tests/test_knowledge_base.py
"""

import os
import sys
import sqlite3
import json
import time
import tempfile

# Adicionar src ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.knowledge.schema import (
    Chunk, init_db, insert_chunk, insert_chunks_batch,
    get_chunk_by_id, update_chunk_status, get_db_stats,
    CHUNK_TYPES, SOURCE_TYPES, DOMAINS,
)
from src.knowledge.search import KnowledgeBaseSearch, SearchQuery
from src.knowledge.manifest import get_feature_manifest, get_feature_summary_text


def create_test_db():
    """Cria banco de teste em diretório temporário."""
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "test.db")
    conn = init_db(db_path)
    return db_path, conn


def create_sample_chunks() -> list:
    """Cria chunks de exemplo para testes."""
    return [
        Chunk(
            title="Regra de prazo de devolução para PF",
            content="O prazo de devolução para pessoa física é de 30 dias corridos a partir da data de entrega do produto. Após esse prazo, a devolução não é aceita exceto em casos de defeito de fabricação cobertos pela garantia.",
            feature="devolucao_produtos",
            domain="pos_venda",
            chunk_type="regra_negocio",
            source_type="documento_produto",
            source_ref="data/bronze/docs/prd-devolucao-v2.md",
            confidence="high",
            tags=["devolucao", "prazo", "pessoa_fisica", "30_dias"],
            participants=["ana_po"],
            related_features=["garantia"],
        ),
        Chunk(
            title="Regra de prazo de devolução para PJ Enterprise",
            content="O prazo de devolução para clientes pessoa jurídica com contrato enterprise segue o definido no contrato vigente. A TechCorp Ltda possui prazo de 90 dias corridos conforme cláusula 8.3 do contrato ENT-2026-0042.",
            feature="devolucao_produtos",
            domain="pos_venda",
            chunk_type="regra_negocio",
            source_type="documento_cliente",
            source_ref="data/bronze/docs/requisitos-cliente-enterprise.md",
            confidence="high",
            tags=["devolucao", "prazo", "pj", "enterprise", "90_dias", "contrato"],
            participants=["roberto_mendes"],
            related_features=[],
        ),
        Chunk(
            title="Decisão técnica: API de devolução",
            content="Endpoint principal: POST /api/v1/returns. Autenticação via Bearer token JWT. Payload JSON com campos: order_id, reason, evidence_urls, refund_type. Resposta 201 Created com return_id. Idempotência via header Idempotency-Key.",
            feature="devolucao_produtos",
            domain="pos_venda",
            chunk_type="decisao_tecnica",
            source_type="decisao_registro",
            source_ref="data/bronze/calls/refinamento-tecnico-devolucao-2026-04-05.md",
            confidence="high",
            tags=["api", "endpoint", "rest", "jwt", "idempotencia"],
            participants=["carlos_arq", "pedro_dev"],
            related_features=[],
        ),
        Chunk(
            title="Fluxo principal de devolução",
            content="1. Cliente acessa Meus Pedidos. 2. Seleciona o pedido. 3. Clica em Solicitar Devolução. 4. Seleciona motivo da devolução. 5. Anexa foto se necessário. 6. Escolhe entre reembolso no cartão ou crédito na loja. 7. Confirma solicitação. 8. Recebe etiqueta de envio reverso por email.",
            feature="devolucao_produtos",
            domain="pos_venda",
            chunk_type="fluxo_usuario",
            source_type="transcricao_reuniao",
            source_ref="data/bronze/calls/grooming-devolucao-2026-04-01.md",
            confidence="medium",
            tags=["fluxo", "usuario", "devolucao", "etiqueta", "reembolso"],
            participants=["ana_po", "pedro_dev"],
            related_features=[],
        ),
        Chunk(
            title="Integração com gateway de pagamento Adyen",
            content="Integração com Adyen para processamento de estornos. Endpoint: POST /v68/payments/{paymentPspReference}/refunds. Rate limit: 100 requests por minuto em produção. Estorno processado em até 5 dias úteis. Usar fila SQS para desacoplar processamento.",
            feature="devolucao_produtos",
            domain="financeiro",
            chunk_type="integracao",
            source_type="decisao_registro",
            source_ref="data/bronze/calls/refinamento-tecnico-devolucao-2026-04-05.md",
            confidence="high",
            tags=["adyen", "estorno", "gateway", "pagamento", "sqs", "rate_limit"],
            participants=["carlos_arq"],
            related_features=["checkout_pagamento"],
        ),
        Chunk(
            title="Condição do produto para devolução PF",
            content="O produto deve estar em condições originais para devolução por arrependimento: sem uso, com etiquetas, na embalagem original. Produtos com sinais de uso não são aceitos para devolução por arrependimento. Para defeito, aceita-se o produto mesmo com uso.",
            feature="devolucao_produtos",
            domain="pos_venda",
            chunk_type="regra_negocio",
            source_type="chat",
            source_ref="data/bronze/chats/slack-devolucao-2026-04-03.md",
            confidence="low",
            tags=["devolucao", "condicao", "produto", "uso", "embalagem"],
            participants=["ana_po", "pedro_dev"],
            related_features=[],
        ),
        Chunk(
            title="Requisito de performance do endpoint de devolução",
            content="O endpoint de criação de devolução deve responder em até 200ms no percentil 95. A página de Solicitar Devolução deve ter LCP de até 1.5 segundos. Disponibilidade do sistema: 99.9% uptime mensal.",
            feature="devolucao_produtos",
            domain="pos_venda",
            chunk_type="requisito_nao_funcional",
            source_type="documento_produto",
            source_ref="data/bronze/docs/prd-devolucao-v2.md",
            confidence="high",
            tags=["performance", "sla", "latencia", "disponibilidade"],
            participants=["ana_po"],
            related_features=[],
        ),
    ]


# === TESTES DO SCHEMA ===

def test_init_db():
    """Banco inicializa sem erros e tabelas existem."""
    db_path, conn = create_test_db()
    
    # Verificar tabelas
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = [t[0] for t in tables]
    
    assert "chunks" in table_names, "Tabela 'chunks' não encontrada"
    assert "chunks_fts" in table_names, "Tabela 'chunks_fts' não encontrada"
    
    # Verificar triggers
    triggers = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger'"
    ).fetchall()
    trigger_names = [t[0] for t in triggers]
    assert len(trigger_names) >= 3, f"Esperado >= 3 triggers, encontrado {len(trigger_names)}"
    
    conn.close()
    print("✓ test_init_db")


def test_insert_and_retrieve_chunk():
    """Inserção e recuperação por ID."""
    db_path, conn = create_test_db()
    chunks = create_sample_chunks()
    
    chunk = chunks[0]
    returned_id = insert_chunk(conn, chunk)
    assert returned_id == chunk.id
    
    retrieved = get_chunk_by_id(conn, chunk.id)
    assert retrieved is not None
    assert retrieved.title == chunk.title
    assert retrieved.content == chunk.content
    assert retrieved.feature == chunk.feature
    assert retrieved.tags == chunk.tags
    
    conn.close()
    print("✓ test_insert_and_retrieve_chunk")


def test_batch_insert():
    """Inserção em lote."""
    db_path, conn = create_test_db()
    chunks = create_sample_chunks()
    
    count = insert_chunks_batch(conn, chunks)
    assert count == len(chunks)
    
    total = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    assert total == len(chunks)
    
    conn.close()
    print("✓ test_batch_insert")


def test_validation_rejects_invalid():
    """Validação rejeita chunks com dados inválidos."""
    chunk = Chunk(title="", content="test", chunk_type="tipo_invalido")
    errors = chunk.validate()
    assert len(errors) > 0, "Deveria ter erros de validação"
    assert any("title" in e for e in errors)
    assert any("chunk_type" in e for e in errors)
    print("✓ test_validation_rejects_invalid")


def test_update_status():
    """Atualização de status funciona."""
    db_path, conn = create_test_db()
    chunk = create_sample_chunks()[0]
    insert_chunk(conn, chunk)
    
    result = update_chunk_status(conn, chunk.id, "deprecated")
    assert result is True
    
    updated = get_chunk_by_id(conn, chunk.id)
    assert updated.status == "deprecated"
    
    conn.close()
    print("✓ test_update_status")


def test_db_stats():
    """Estatísticas do banco."""
    db_path, conn = create_test_db()
    insert_chunks_batch(conn, create_sample_chunks())
    
    stats = get_db_stats(conn)
    assert stats["total_chunks"] == 7
    assert stats["active_chunks"] == 7
    assert "regra_negocio" in stats["chunks_by_type"]
    assert "devolucao_produtos" in stats["chunks_by_feature"]
    
    conn.close()
    print("✓ test_db_stats")


# === TESTES DA BUSCA ===

def test_search_by_text():
    """Busca textual via FTS5 encontra chunks relevantes."""
    db_path, conn = create_test_db()
    insert_chunks_batch(conn, create_sample_chunks())
    conn.close()
    
    search = KnowledgeBaseSearch(db_path)
    results = search.search(SearchQuery(text="prazo devolução"))
    
    assert len(results) > 0, "Deveria encontrar chunks sobre prazo de devolução"
    # O chunk sobre prazo PF ou PJ deve estar nos resultados
    titles = [r.title for r in results]
    assert any("prazo" in t.lower() for t in titles), f"Nenhum resultado sobre prazo: {titles}"
    
    search.close()
    print("✓ test_search_by_text")


def test_search_by_metadata_filters():
    """Filtros de metadados reduzem resultados corretamente."""
    db_path, conn = create_test_db()
    insert_chunks_batch(conn, create_sample_chunks())
    conn.close()
    
    search = KnowledgeBaseSearch(db_path)
    
    # Filtro por tipo
    results = search.search(SearchQuery(
        text="",
        chunk_types=["regra_negocio"],
    ))
    assert all(r.chunk_type == "regra_negocio" for r in results)
    
    # Filtro por domínio
    results = search.search(SearchQuery(
        text="",
        domain="financeiro",
    ))
    assert all(r.domain == "financeiro" for r in results)
    assert len(results) > 0
    
    # Filtro por confiança mínima
    results = search.search(SearchQuery(
        text="",
        confidence_min="high",
    ))
    assert all(r.confidence == "high" for r in results)
    
    search.close()
    print("✓ test_search_by_metadata_filters")


def test_search_combined_filters_and_text():
    """Filtros de metadados + texto funcionam juntos."""
    db_path, conn = create_test_db()
    insert_chunks_batch(conn, create_sample_chunks())
    conn.close()
    
    search = KnowledgeBaseSearch(db_path)
    results = search.search(SearchQuery(
        text="estorno pagamento",
        feature="devolucao_produtos",
        chunk_types=["integracao"],
    ))
    
    assert len(results) > 0
    assert all(r.chunk_type == "integracao" for r in results)
    assert any("adyen" in r.title.lower() for r in results)
    
    search.close()
    print("✓ test_search_combined_filters_and_text")


def test_search_by_tags():
    """Busca por tags funciona."""
    db_path, conn = create_test_db()
    insert_chunks_batch(conn, create_sample_chunks())
    conn.close()
    
    search = KnowledgeBaseSearch(db_path)
    results = search.search(SearchQuery(
        text="",
        tags=["enterprise", "pj"],
    ))
    
    assert len(results) > 0
    # Pelo menos o chunk sobre PJ enterprise deve aparecer
    assert any("enterprise" in str(r.tags) or "pj" in str(r.tags) for r in results)
    
    search.close()
    print("✓ test_search_by_tags")


def test_feature_context():
    """Feature context carrega todos os chunks de uma feature."""
    db_path, conn = create_test_db()
    insert_chunks_batch(conn, create_sample_chunks())
    conn.close()
    
    search = KnowledgeBaseSearch(db_path)
    results = search.get_feature_context("devolucao_produtos")
    
    # Todos os 7 chunks de exemplo são dessa feature (6 pos_venda + 1 financeiro)
    assert len(results) == 7, f"Esperado 7 chunks, obteve {len(results)}"
    
    # Verificar ordenação: regra_negocio deve vir primeiro
    assert results[0].chunk_type == "regra_negocio"
    
    search.close()
    print("✓ test_feature_context")


def test_token_estimation():
    """Estimativa de tokens funciona."""
    db_path, conn = create_test_db()
    insert_chunks_batch(conn, create_sample_chunks())
    conn.close()
    
    search = KnowledgeBaseSearch(db_path)
    tokens = search.estimate_feature_tokens("devolucao_produtos")
    
    assert tokens > 0
    # 7 chunks com ~200 chars cada ≈ ~350 tokens
    assert tokens < 5000, f"Estimativa parece alta demais: {tokens}"
    
    search.close()
    print("✓ test_token_estimation")


def test_cache_works():
    """Cache retorna resultado sem bater no banco."""
    db_path, conn = create_test_db()
    insert_chunks_batch(conn, create_sample_chunks())
    conn.close()
    
    search = KnowledgeBaseSearch(db_path, cache_ttl_seconds=60)
    
    # Primeira busca: popula cache
    query = SearchQuery(text="prazo devolução", feature="devolucao_produtos")
    results1 = search.search(query)
    
    # Segunda busca: deve vir do cache (muito mais rápida)
    start = time.time()
    results2 = search.search(query)
    elapsed = time.time() - start
    
    assert len(results1) == len(results2)
    assert elapsed < 0.01, f"Cache miss? Levou {elapsed:.3f}s"
    
    search.close()
    print("✓ test_cache_works")


def test_cache_invalidation():
    """Invalidação de cache funciona."""
    db_path, conn = create_test_db()
    insert_chunks_batch(conn, create_sample_chunks())
    conn.close()
    
    search = KnowledgeBaseSearch(db_path)
    
    # Popular cache
    search.get_feature_context("devolucao_produtos")
    assert len(search._cache) > 0
    
    # Invalidar
    search.invalidate_cache(feature="devolucao_produtos")
    
    # Cache deve estar vazio para essa feature
    fc_key = "__feature_context__:devolucao_produtos"
    assert fc_key not in search._cache
    
    search.close()
    print("✓ test_cache_invalidation")


def test_fts5_handles_accents():
    """FTS5 com unicode61 remove_diacritics=2 encontra com e sem acento."""
    db_path, conn = create_test_db()
    insert_chunks_batch(conn, create_sample_chunks())
    conn.close()
    
    search = KnowledgeBaseSearch(db_path)
    
    # Buscar sem acento deve encontrar chunks com acento
    results = search.search(SearchQuery(text="devolucao"))
    assert len(results) > 0, "Busca sem acento deveria encontrar chunks com 'devolução'"
    
    search.close()
    print("✓ test_fts5_handles_accents")


def test_fts5_handles_malformed_query():
    """FTS5 não quebra com queries malformadas."""
    db_path, conn = create_test_db()
    insert_chunks_batch(conn, create_sample_chunks())
    conn.close()
    
    search = KnowledgeBaseSearch(db_path)
    
    # Queries com caracteres especiais não devem causar exceção
    results = search.search(SearchQuery(text='prazo "incompleto'))
    # Pode retornar 0 resultados, mas não deve dar erro
    assert isinstance(results, list)
    
    results = search.search(SearchQuery(text="(parenteses) AND OR NOT"))
    assert isinstance(results, list)
    
    search.close()
    print("✓ test_fts5_handles_malformed_query")


# === TESTES DO MANIFESTO ===

def test_feature_manifest():
    """Manifesto retorna resumo correto por feature."""
    db_path, conn = create_test_db()
    insert_chunks_batch(conn, create_sample_chunks())
    
    manifest = get_feature_manifest(conn)
    assert len(manifest) > 0
    
    # Deve ter pelo menos a feature devolucao_produtos
    features = [m["feature"] for m in manifest]
    assert "devolucao_produtos" in features
    
    # Verificar contagens
    devol = [m for m in manifest if m["feature"] == "devolucao_produtos"]
    total = sum(d["total_chunks"] for d in devol)
    assert total == 7, f"Esperado 7 chunks total, obteve {total}"
    
    conn.close()
    print("✓ test_feature_manifest")


def test_feature_summary_text():
    """Summary text é gerável e legível."""
    db_path, conn = create_test_db()
    insert_chunks_batch(conn, create_sample_chunks())
    
    text = get_feature_summary_text(conn)
    assert "devolucao_produtos" in text
    assert "chunks" in text
    assert len(text) > 50
    
    conn.close()
    print("✓ test_feature_summary_text")


def test_empty_manifest():
    """Manifesto com base vazia retorna lista vazia."""
    db_path, conn = create_test_db()
    
    manifest = get_feature_manifest(conn)
    assert manifest == []
    
    text = get_feature_summary_text(conn)
    assert "vazia" in text.lower()
    
    conn.close()
    print("✓ test_empty_manifest")


# === RUNNER ===

if __name__ == "__main__":
    tests = [
        # Schema
        test_init_db,
        test_insert_and_retrieve_chunk,
        test_batch_insert,
        test_validation_rejects_invalid,
        test_update_status,
        test_db_stats,
        # Busca
        test_search_by_text,
        test_search_by_metadata_filters,
        test_search_combined_filters_and_text,
        test_search_by_tags,
        test_feature_context,
        test_token_estimation,
        test_cache_works,
        test_cache_invalidation,
        test_fts5_handles_accents,
        test_fts5_handles_malformed_query,
        # Manifesto
        test_feature_manifest,
        test_feature_summary_text,
        test_empty_manifest,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: {e}")
            failed += 1
    
    print(f"\n{'='*50}")
    print(f"Resultado: {passed} passed, {failed} failed, {passed + failed} total")
    
    if failed > 0:
        sys.exit(1)
```

---

## Validação final da Etapa 2

```bash
# 1. Verificar que os arquivos existem
ls -la src/knowledge/__init__.py
ls -la src/knowledge/schema.py
ls -la src/knowledge/search.py
ls -la src/knowledge/manifest.py

# 2. Rodar testes
python tests/test_knowledge_base.py

# Esperado:
# ✓ test_init_db
# ✓ test_insert_and_retrieve_chunk
# ✓ test_batch_insert
# ✓ test_validation_rejects_invalid
# ✓ test_update_status
# ✓ test_db_stats
# ✓ test_search_by_text
# ✓ test_search_by_metadata_filters
# ✓ test_search_combined_filters_and_text
# ✓ test_search_by_tags
# ✓ test_feature_context
# ✓ test_token_estimation
# ✓ test_cache_works
# ✓ test_cache_invalidation
# ✓ test_fts5_handles_accents
# ✓ test_fts5_handles_malformed_query
# ✓ test_feature_manifest
# ✓ test_feature_summary_text
# ✓ test_empty_manifest
#
# Resultado: 19 passed, 0 failed, 19 total

# 3. Teste rápido de sanidade
python -c "
from src.knowledge.schema import init_db, insert_chunk, Chunk

conn = init_db('data/silver/knowledge.db')
print('Banco criado com sucesso')

chunk = Chunk(
    title='Teste de sanidade',
    content='Este é um chunk de teste para verificar que o schema funciona.',
    feature='teste',
    domain='pos_venda',
    chunk_type='contexto_negocio',
    source_type='documento_produto',
    source_ref='teste.md',
    confidence='high',
    tags=['teste'],
)
insert_chunk(conn, chunk)
print('Chunk inserido com sucesso')

# Verificar FTS5
results = conn.execute(
    \"\"\"SELECT c.title FROM chunks c
    JOIN chunks_fts fts ON c.id = fts.id
    WHERE chunks_fts MATCH 'sanidade'\"\"\"
).fetchall()
print(f'FTS5 encontrou: {len(results)} resultado(s)')
assert len(results) == 1

# Limpar
conn.execute('DELETE FROM chunks WHERE feature = ?', ('teste',))
conn.commit()
conn.close()
print('Limpeza OK. Etapa 2 validada.')
"
```

## Critérios de aceite da Etapa 2

- [ ] `src/knowledge/__init__.py` existe (pode ser vazio)
- [ ] `src/knowledge/schema.py` implementa: enums, Chunk dataclass com validate(), init_db(), insert_chunk(), insert_chunks_batch(), get_chunk_by_id(), update_chunk_status(), get_db_stats()
- [ ] `src/knowledge/search.py` implementa: SearchQuery, SearchResult, KnowledgeBaseSearch com search(), get_feature_context(), estimate_feature_tokens(), cache com TTL, invalidate_cache()
- [ ] `src/knowledge/manifest.py` implementa: get_feature_manifest(), get_feature_summary_text()
- [ ] FTS5 funciona com remoção de acentos (buscar "devolucao" encontra "devolução")
- [ ] FTS5 não quebra com queries malformadas (caracteres especiais)
- [ ] Cache em memória funciona: segunda busca idêntica < 1ms
- [ ] Invalidação de cache funciona por feature
- [ ] Triggers de FTS5 mantêm índice sincronizado após insert/update/delete
- [ ] Todos os 19 testes passam
- [ ] Banco é criado em `data/silver/knowledge.db` sem erro
- [ ] Zero dependências externas (só stdlib do Python)
