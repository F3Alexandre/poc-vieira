"""
Schema da base de conhecimento Silver.

Enums controlados, dataclass Chunk, SQL de criação e funções CRUD.
Qualquer novo valor de enum deve ser adicionado aqui — nunca aceitar
texto livre nos campos tipados.
"""

import uuid
import json
import sqlite3
import os
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, List

# ---------------------------------------------------------------------------
# Enums controlados
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Dataclass Chunk
# ---------------------------------------------------------------------------

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
    confidence: str = "medium"               # high | medium | low

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


# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Funções de banco
# ---------------------------------------------------------------------------

def init_db(db_path: str) -> sqlite3.Connection:
    """Inicializa o banco com schema completo.

    Cria o diretório pai se não existir.
    Retorna a conexão configurada.

    Configurações importantes:
    - WAL mode: permite leitura concorrente durante escrita
    - row_factory: retorna Rows como dicts (acesso por nome)
    """
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

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
    superseded_by: Optional[str] = None,
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
