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
