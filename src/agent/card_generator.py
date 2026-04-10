"""
Gerador de cards — converte Working Memory em arquivos Markdown
seguindo o template do Azure DevOps.

Gera:
- Card pai (User Story principal)
- Cards filhos (se houver)

Os arquivos são salvos em data/output/cards/.
"""

import os


def generate_card_markdown(working_memory, output_dir: str) -> str:
    """Gera o arquivo Markdown do card principal.

    Args:
        working_memory: WorkingMemory com todos os campos.
        output_dir: Diretório onde salvar os cards.

    Returns:
        Caminho do arquivo gerado.
    """
    os.makedirs(output_dir, exist_ok=True)

    feature_slug = (working_memory.feature or "feature").upper().replace("_", "-")
    card_id = f"{feature_slug}-001"
    filename = f"{card_id}.md"
    filepath = os.path.join(output_dir, filename)

    lines = []

    # === Título ===
    title = working_memory.action or "User Story"
    lines.append(f"# [{card_id}] {title}")
    lines.append("")

    # === Metadados ===
    lines.append("## Metadados")
    lines.append("")
    lines.append("| Campo | Valor |")
    lines.append("|-------|-------|")
    lines.append(f"| **Feature** | {working_memory.feature or 'N/A'} |")
    lines.append(f"| **Domínio** | {working_memory.domain or 'N/A'} |")
    stakeholders_text = "N/A"
    if working_memory.stakeholders:
        parts = []
        for s in working_memory.stakeholders:
            if isinstance(s, str):
                parts.append(s)
            elif isinstance(s, dict):
                # Ex: {"po": "Fulano", "devs": ["A", "B"]}
                for role, names in s.items():
                    if isinstance(names, list):
                        parts.append(f"{role}: {', '.join(str(n) for n in names)}")
                    else:
                        parts.append(f"{role}: {names}")
            else:
                parts.append(str(s))
        stakeholders_text = ", ".join(parts)
    lines.append(f"| **Stakeholders** | {stakeholders_text} |")
    lines.append(f"| **Prioridade** | A definir pelo PO |")
    lines.append(f"| **Estimativa** | A definir pelo time |")
    lines.append("")

    # === Contexto ===
    lines.append("## Contexto")
    lines.append("")
    lines.append(working_memory.context_description or "*Contexto não fornecido.*")
    lines.append("")

    # === User Story ===
    lines.append("## User Story")
    lines.append("")
    lines.append(f"**Como** {working_memory.persona or '[persona não definida]'},")
    lines.append(f"**eu quero** {working_memory.action or '[ação não definida]'},")
    lines.append(f"**para que** {working_memory.benefit or '[benefício não definido]'}.")
    lines.append("")

    # === Regras de negócio ===
    if working_memory.business_rules:
        lines.append("## Regras de negócio")
        lines.append("")
        lines.append("| ID | Regra | Condições / Exceções | Confiança |")
        lines.append("|----|-------|----------------------|-----------|")
        for rule in working_memory.business_rules:
            if isinstance(rule, str):
                lines.append(f"| - | {rule} | - | - |")
            else:
                conf = rule.get("confidence", "medium")
                icon = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(conf, "🟡")
                conditions = rule.get("conditions", "Sem exceções conhecidas")
                lines.append(f"| {rule.get('id', '-')} | {rule.get('rule', '-')} | {conditions} | {icon} {conf.capitalize()} |")
        lines.append("")
        lines.append("> 🟢 Alta = documentação formal | 🟡 Média = decisão em reunião | 🔴 Baixa = menção informal")
        lines.append("")

    # === Fluxo do usuário ===
    if working_memory.main_flow:
        lines.append("## Fluxo do usuário")
        lines.append("")
        lines.append("### Fluxo principal")
        lines.append("")
        for i, step in enumerate(working_memory.main_flow, 1):
            lines.append(f"{i}. {step}")
        lines.append("")

    if working_memory.alternative_flows:
        lines.append("### Fluxos alternativos")
        lines.append("")
        for flow in working_memory.alternative_flows:
            if isinstance(flow, str):
                lines.append(f"- {flow}")
            else:
                lines.append(f"**{flow.get('id', 'FA')}:** {flow.get('condition', '')} → {flow.get('behavior', '')}")
        lines.append("")

    if working_memory.error_flows:
        lines.append("### Fluxos de exceção / erro")
        lines.append("")
        for flow in working_memory.error_flows:
            if isinstance(flow, str):
                lines.append(f"- {flow}")
            else:
                lines.append(f"**{flow.get('id', 'FE')}:** {flow.get('condition', '')} → {flow.get('response', '')} → {flow.get('user_sees', '')}")
        lines.append("")

    # === Integrações ===
    if working_memory.integrations:
        lines.append("## Integrações")
        lines.append("")
        lines.append("| Sistema / Módulo | Tipo | Descrição |")
        lines.append("|------------------|------|-----------|")
        for intg in working_memory.integrations:
            if isinstance(intg, str):
                lines.append(f"| - | - | {intg} |")
            else:
                lines.append(f"| {intg.get('system', '-')} | {intg.get('direction', '-')} | {intg.get('description', '-')} |")
        lines.append("")

    # === Requisitos não funcionais ===
    if working_memory.nfr:
        lines.append("## Requisitos não funcionais")
        lines.append("")
        lines.append("| Categoria | Requisito | Métrica |")
        lines.append("|-----------|-----------|---------|")
        for req in working_memory.nfr:
            if isinstance(req, str):
                lines.append(f"| - | {req} | - |")
            else:
                lines.append(f"| {req.get('category', '-')} | {req.get('requirement', '-')} | {req.get('metric', '-')} |")
        lines.append("")

    # === Escopo ===
    if working_memory.in_scope or working_memory.out_of_scope:
        lines.append("## Definição de escopo")
        lines.append("")
        if working_memory.in_scope:
            lines.append("### Dentro do escopo")
            lines.append("")
            for item in working_memory.in_scope:
                lines.append(f"- {item}")
            lines.append("")
        if working_memory.out_of_scope:
            lines.append("### Fora do escopo")
            lines.append("")
            for item in working_memory.out_of_scope:
                reason = item.get("reason", "") if isinstance(item, dict) else ""
                text = item.get("item", item) if isinstance(item, dict) else item
                if reason:
                    lines.append(f"- {text} — *Motivo: {reason}*")
                else:
                    lines.append(f"- {text}")
            lines.append("")

    # === Critérios de aceite ===
    has_criteria = (
        working_memory.acceptance_criteria_product
        or working_memory.acceptance_criteria_technical
        or working_memory.non_acceptance_criteria
    )
    if has_criteria:
        lines.append("## Critérios de aceite")
        lines.append("")

    if working_memory.acceptance_criteria_product:
        lines.append("### Produto")
        lines.append("")
        for ca in working_memory.acceptance_criteria_product:
            if isinstance(ca, str):
                lines.append(f"- [ ] {ca}")
            else:
                # Suporta tanto given/when/then quanto dado/quando/entao
                given = ca.get("given", ca.get("dado", ""))
                when = ca.get("when", ca.get("quando", ""))
                then = ca.get("then", ca.get("entao", ""))
                if given and when and then:
                    lines.append(f"- [ ] **[{ca.get('id', 'CA')}]** Dado {given}, quando {when}, então {then}.")
                else:
                    lines.append(f"- [ ] **[{ca.get('id', 'CA')}]** {ca.get('criteria', ca.get('description', '-'))}")
        lines.append("")

    if working_memory.acceptance_criteria_technical:
        lines.append("### Técnicos")
        lines.append("")
        for ct in working_memory.acceptance_criteria_technical:
            if isinstance(ct, str):
                lines.append(f"- [ ] {ct}")
            else:
                lines.append(f"- [ ] **[{ct.get('id', 'CT')}]** {ct.get('criteria', ct.get('description', '-'))}")
        lines.append("")

    if working_memory.non_acceptance_criteria:
        lines.append("### Critérios de não-aceite")
        lines.append("")
        for cna in working_memory.non_acceptance_criteria:
            if isinstance(cna, str):
                lines.append(f"- [ ] {cna}")
            else:
                lines.append(f"- [ ] **[{cna.get('id', 'CNA')}]** {cna.get('criteria', cna.get('description', '-'))}")
        lines.append("")

    # === Observações e ambiguidades ===
    if working_memory.observations:
        lines.append("## Observações e ambiguidades")
        lines.append("")
        for obs in working_memory.observations:
            if isinstance(obs, str):
                lines.append(f"> ℹ️ {obs}")
                lines.append(">")
            else:
                obs_type = obs.get("type", "info")
                icon = {"contradiction": "⚠️", "ambiguity": "⚠️", "missing": "ℹ️", "info": "ℹ️"}.get(obs_type, "ℹ️")
                lines.append(f"> {icon} **{obs_type.upper()}:** {obs.get('description', '-')}")
                if obs.get("impact"):
                    lines.append(f"> **Impacto se não resolvido:** {obs['impact']}")
                lines.append(">")
        lines.append("")

    # === Referências da base ===
    if working_memory.knowledge_refs:
        lines.append("## Referências da base de conhecimento")
        lines.append("")
        lines.append("| Chunk | Tipo | Confiança | Data |")
        lines.append("|-------|------|-----------|------|")
        for ref in working_memory.knowledge_refs:
            if isinstance(ref, str):
                lines.append(f"| {ref} | - | - | - |")
            else:
                lines.append(f"| {ref.get('title', '-')} | {ref.get('chunk_type', '-')} | {ref.get('confidence', '-')} | {ref.get('date', '-')} |")
        lines.append("")

    # === Cards filhos ===
    if working_memory.child_cards:
        lines.append("## Cards filhos")
        lines.append("")
        lines.append("| ID | Título | Motivo da separação |")
        lines.append("|----|--------|---------------------|")
        for child in working_memory.child_cards:
            if isinstance(child, str):
                lines.append(f"| - | {child} | - |")
            else:
                lines.append(f"| {child.get('id', '-')} | {child.get('title', '-')} | {child.get('reason', '-')} |")
        lines.append("")

    # === Escrever arquivo ===
    content = "\n".join(lines)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    # === Gerar cards filhos (stubs) ===
    for child in working_memory.child_cards:
        if isinstance(child, str):
            continue  # Pular strings — precisa ser dict com id/title
        child_id = child.get("id", "CHILD")
        child_filepath = os.path.join(output_dir, f"{child_id}.md")
        with open(child_filepath, "w", encoding="utf-8") as f:
            f.write(f"# [{child_id}] {child.get('title', 'Card filho')}\n\n")
            f.write(f"**Parent:** [{card_id}]({filename})\n\n")
            f.write(f"**Motivo da separação:** {child.get('reason', '-')}\n\n")
            f.write("---\n\n")
            f.write("*Este card filho foi gerado automaticamente e necessita especificação completa.*\n")

    return filepath
