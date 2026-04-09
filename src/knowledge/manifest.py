"""
Manifesto de features da base de conhecimento Silver.

O manifesto é um view materializado que resume o que existe na base
por feature. O agente consulta no início da conversa para saber o
universo de features disponíveis.
"""

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
