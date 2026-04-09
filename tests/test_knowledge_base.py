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
