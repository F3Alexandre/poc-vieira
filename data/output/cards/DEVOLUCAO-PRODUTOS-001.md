# [DEVOLUCAO-PRODUTOS-001] Solicitar devolução total de produto via Site, App ou SAC

## Metadados

| Campo | Valor |
|-------|-------|
| **Feature** | devolucao_produtos |
| **Domínio** | ['pos_venda', 'financeiro'] |
| **Stakeholders** | PO: Vinicius Bazan Cirello, DEVs: Alexandre Damas Murata, Raphael Klein de Almeida |
| **Prioridade** | A definir pelo PO |
| **Estimativa** | A definir pelo time |

## Contexto

*Contexto não fornecido.*

## User Story

**Como** Cliente Pessoa Física (PF) que realizou uma compra na plataforma,
**eu quero** Solicitar devolução total de produto via Site, App ou SAC,
**para que** Reduzir atrito no pós-venda oferecendo um processo de devolução claro, ágil e multicanal.

## Regras de negócio

| ID | Regra | Condições / Exceções | Confiança |
|----|-------|----------------------|-----------|
| RN-01 | Prazo para solicitação de devolução: 45 dias corridos a partir da entrega (override do PRD por orientação jurídica) | Sem exceções conhecidas | 🟡 Medium |
| RN-02 | Solicitações dentro do prazo são aprovadas automaticamente | Sem exceções conhecidas | 🟡 Medium |
| RN-03 | Solicitações fora do prazo entram em fila de revisão manual | Sem exceções conhecidas | 🟡 Medium |
| RN-04 | Outros motivos para revisão manual: A definir | Sem exceções conhecidas | 🟡 Medium |
| RN-05 | Motivos de devolução obrigatórios: Entrega com defeito / Má qualidade / Simplesmente não quero / Me arrependo | Sem exceções conhecidas | 🟡 Medium |
| RN-06 | Foto do produto é obrigatória para abertura da devolução | Sem exceções conhecidas | 🟡 Medium |
| RN-07 | Estorno sempre ao meio de pagamento original. Crédito em site não é permitido | Sem exceções conhecidas | 🟡 Medium |
| RN-08 | Prazo de estorno: padrão bancário, fatura seguinte | Sem exceções conhecidas | 🟡 Medium |
| RN-09 | SAC pode abrir devolução em nome do cliente usando o mesmo sistema | Sem exceções conhecidas | 🟡 Medium |
| RN-10 | Idempotência por chave order_id+customer_id. Retorna 409 se já existe solicitação ativa | Sem exceções conhecidas | 🟡 Medium |
| RN-11 | Devolução parcial fora do escopo deste card — tratada em card separado (US-DEV-05) | Sem exceções conhecidas | 🟡 Medium |

> 🟢 Alta = documentação formal | 🟡 Média = decisão em reunião | 🔴 Baixa = menção informal

## Definição de escopo

### Dentro do escopo

- Devolução total para PF
- Aprovação automática dentro do prazo
- Geração de etiqueta de devolução
- Acompanhamento de status
- Estorno ao meio de pagamento original
- Canal Site
- Canal App
- Canal SAC (atendente abre em nome do cliente, mesmo sistema)

### Fora do escopo

- Devolução parcial (tratada em US-DEV-05)
- Crédito em site
- Marketplace de terceiros
- Clientes PJ (não mencionado — a confirmar)

## Observações e ambiguidades

> ℹ️ Contradição de prazo resolvida: PRD dizia 30 dias, jurídico (Slack) diz 45 dias. Decisão: 45 dias corridos.
>
> ℹ️ Devolução parcial: requisito contratual TechCorp ENT-01 (R$2M/ano) — tratado em card separado US-DEV-05.
>
> ℹ️ Outros motivos para revisão manual além de 'fora do prazo': A definir.
>
> ℹ️ Vocabulário padronizado: usar 'estorno' na camada de negócio; 'reversal' apenas em comentários internos.
>

## Referências da base de conhecimento

| Chunk | Tipo | Confiança | Data |
|-------|------|-----------|------|
| Criterio aceite aprovacao prazo | criterio_aceite | high | 2026-04-09 |
| Vocabulario estorno vs reversal | vocabulario | medium | 2026-04-09 |
| Requisito enterprise devolucao parcial | restricao | high | 2026-04-09 |
| Idempotencia e fila SQS | decisao_tecnica | medium | 2026-04-09 |
| Contradicao prazo campanhas | restricao | low | 2026-04-09 |
| Definicao de escopo | definicao_escopo | high | 2026-04-09 |
| Requisitos performance e disponibilidade | requisito_nao_funcional | medium | 2026-04-09 |
| State machine solicitacao devolucao | decisao_tecnica | medium | 2026-04-09 |
| Fluxo principal devolucao app | fluxo_usuario | medium | 2026-04-09 |
| Aprovacao automatica PF | regra_negocio | high | 2026-04-09 |

## Cards filhos

| ID | Título | Motivo da separação |
|----|--------|---------------------|
| - | US-DEV-01 | - |
| - | US-DEV-02 | - |
| - | US-DEV-03 | - |
| - | US-DEV-04 | - |
| - | US-DEV-05 | - |
