#!/usr/bin/env python3
"""
Validação completa — verifica que todas as etapas estão funcionais.

Verifica:
1. Dados bronze existem e têm conteúdo
2. Base Silver está populada e FTS5 funciona
3. Busca retorna resultados relevantes
4. Manifesto de features está correto
5. Working Memory funciona
6. Card generator produz output válido

Rodar: python scripts/validate_all.py
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check(description: str, condition: bool, detail: str = ""):
    """Helper de validação."""
    if condition:
        print(f"  \u2713 {description}")
    else:
        print(f"  \u2717 {description}")
        if detail:
            print(f"    \u2192 {detail}")
    return condition


def validate_bronze():
    """Valida Etapa 1 — dados bronze."""
    print("\n=== ETAPA 1: Dados Bronze ===")
    ok = True

    expected = [
        "data/bronze/calls/grooming-devolucao-2026-04-01.md",
        "data/bronze/calls/refinamento-tecnico-devolucao-2026-04-05.md",
        "data/bronze/docs/prd-devolucao-v2.md",
        "data/bronze/docs/requisitos-cliente-enterprise.md",
        "data/bronze/chats/slack-devolucao-2026-04-03.md",
    ]

    for filepath in expected:
        exists = os.path.exists(filepath)
        if exists:
            with open(filepath, "r", encoding="utf-8") as f:
                words = len(f.read().split())
            ok &= check(f"{os.path.basename(filepath)} ({words} palavras)", words >= 200, f"Muito curto: {words} palavras")
        else:
            ok &= check(f"{os.path.basename(filepath)}", False, "Arquivo não encontrado")

    return ok


def validate_silver():
    """Valida Etapa 2+3 — base Silver populada."""
    print("\n=== ETAPA 2+3: Base Silver ===")
    ok = True

    db_path = "data/silver/knowledge.db"
    ok &= check("Banco existe", os.path.exists(db_path), f"{db_path} não encontrado")

    if not os.path.exists(db_path):
        return False

    from src.knowledge.schema import init_db, get_db_stats
    from src.knowledge.search import KnowledgeBaseSearch, SearchQuery
    from src.knowledge.manifest import get_feature_manifest

    conn = init_db(db_path)
    stats = get_db_stats(conn)

    ok &= check(
        f"Chunks na base: {stats['total_chunks']}",
        stats["total_chunks"] >= 10,
        f"Esperado >= 10 chunks, tem {stats['total_chunks']}"
    )

    ok &= check(
        f"Chunks ativos: {stats['active_chunks']}",
        stats["active_chunks"] >= 10,
        ""
    )

    type_count = len(stats.get("chunks_by_type", {}))
    ok &= check(
        f"Tipos de chunk: {type_count} tipos diferentes",
        type_count >= 3,
        f"Esperado >= 3 tipos, tem {type_count}"
    )

    # Testar FTS5
    try:
        cursor = conn.execute("""
            SELECT COUNT(*) FROM chunks c
            JOIN chunks_fts fts ON c.id = fts.id
            WHERE chunks_fts MATCH 'devolucao OR devolução'
        """)
        fts_count = cursor.fetchone()[0]
        ok &= check(f"FTS5 funciona: {fts_count} resultados para 'devolução'", fts_count > 0)
    except Exception as e:
        ok &= check("FTS5 funciona", False, str(e))

    # Testar busca com filtros
    search = KnowledgeBaseSearch(db_path)
    results = search.search(SearchQuery(
        text="prazo devolução",
        feature="devolucao_produtos",
        top_k=5,
    ))
    ok &= check(
        f"Busca 'prazo devolução': {len(results)} resultados",
        len(results) > 0,
    )

    # Testar manifesto
    manifest = get_feature_manifest(conn)
    ok &= check(
        f"Manifesto: {len(manifest)} features",
        len(manifest) >= 1,
    )

    features = [m["feature"] for m in manifest]
    ok &= check(
        "Feature 'devolucao_produtos' no manifesto",
        "devolucao_produtos" in features,
        f"Features encontradas: {features}"
    )

    search.close()
    conn.close()
    return ok


def validate_agent_components():
    """Valida Etapa 4 — componentes do agente."""
    print("\n=== ETAPA 4: Componentes do Agente ===")
    ok = True

    # Working Memory
    from src.agent.memory import WorkingMemory

    wm = WorkingMemory()
    wm.feature = "devolucao_produtos"
    wm.persona = "cliente PF"
    wm.action = "solicitar devolução"
    wm.benefit = "receber reembolso"
    wm.business_rules = [{"id": "RN-01", "rule": "Prazo 30 dias"}]
    wm.main_flow = ["Passo 1", "Passo 2", "Passo 3"]
    wm.acceptance_criteria_product = [
        {"id": "CA-01", "given": "x", "when": "y", "then": "z"},
        {"id": "CA-02", "given": "a", "when": "b", "then": "c"},
    ]
    wm.in_scope = ["item 1"]
    wm.out_of_scope = [{"item": "item 2", "reason": "fase 2"}]

    ok &= check("WorkingMemory.is_ready_to_generate()", wm.is_ready_to_generate())

    json_str = wm.to_json()
    wm2 = WorkingMemory.from_json(json_str)
    ok &= check("WorkingMemory serializa/deserializa", wm2.feature == "devolucao_produtos")

    summary = wm.get_compact_summary()
    ok &= check("WorkingMemory.get_compact_summary()", len(summary) > 50)

    # Card Generator
    import tempfile
    from src.agent.card_generator import generate_card_markdown

    tmp = tempfile.mkdtemp()
    filepath = generate_card_markdown(wm, tmp)
    ok &= check("Card gerado", os.path.exists(filepath))

    content = open(filepath, "r", encoding="utf-8").read()
    ok &= check("Card tem seção Metadados", "## Metadados" in content)
    ok &= check("Card tem seção User Story", "## User Story" in content)
    ok &= check("Card tem seção Regras", "## Regras de negócio" in content)
    ok &= check("Card tem seção Fluxo", "## Fluxo do usuário" in content)
    ok &= check("Card tem seção Critérios", "## Critérios de aceite" in content)
    ok &= check("Card tem seção Escopo", "## Definição de escopo" in content)

    import shutil
    shutil.rmtree(tmp)

    return ok


def main():
    print("=" * 60)
    print("  VALIDAÇÃO COMPLETA — Knowledge Base MVP")
    print("=" * 60)

    results = {}
    results["bronze"] = validate_bronze()
    results["silver"] = validate_silver()
    results["agent"] = validate_agent_components()

    # Resumo
    print("\n" + "=" * 60)
    print("  RESUMO")
    print("=" * 60)

    all_ok = True
    for etapa, ok in results.items():
        status = "\u2713 OK" if ok else "\u2717 FALHAS"
        print(f"  {etapa}: {status}")
        all_ok &= ok

    print()
    if all_ok:
        print("  \u2705 TODAS AS VALIDAÇÕES PASSARAM")
        print("  O sistema está pronto para a demo.")
        print()
        print("  Execute: make agent")
        print("  Ou:      make demo")
    else:
        print("  \u274c EXISTEM FALHAS")
        print("  Corrija os problemas acima antes de prosseguir.")
        sys.exit(1)


if __name__ == "__main__":
    main()
