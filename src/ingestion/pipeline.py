"""
Pipeline de ingestão — orquestra extração, chunking e inserção na Silver.

Uso:
    stats = await run_ingestion("data/bronze", "data/silver/knowledge.db", llm_client)
    print(f"Processados: {stats['files_processed']} arquivos, {stats['chunks_created']} chunks")
"""

import os
import uuid
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
