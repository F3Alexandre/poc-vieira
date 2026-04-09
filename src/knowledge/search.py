"""
Interface de busca abstrata para a base de conhecimento Silver.

Estratégia em dois estágios:
1. Filtros de metadados (SQL com índices) reduzem o universo
2. FTS5 rankeia por relevância textual dentro do subset

ABSTRAÇÃO IMPORTANTE: esta classe é o contrato entre o agente e a base.
Hoje a implementação é SQLite + FTS5. Futuro: pode ser trocada por
PostgreSQL (pg_textsearch + pgvector) sem mudar a interface pública.
"""

import sqlite3
import json
import hashlib
import time
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict

from src.knowledge.schema import CONFIDENCE_ORDER

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses de entrada e saída
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Classe KnowledgeBaseSearch
# ---------------------------------------------------------------------------

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
