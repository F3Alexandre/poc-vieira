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
