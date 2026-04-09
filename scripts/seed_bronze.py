#!/usr/bin/env python3
"""
Seed Bronze — cria os arquivos de dados simulados da Etapa 1.

Gera 5 documentos de exemplo para a feature de Devolução de Produtos:
- 2 transcrições de reuniões (calls/)
- 2 documentos formais (docs/)
- 1 thread de Slack (chats/)

Se os arquivos já existem, reporta e pula (não sobrescreve).

Uso:
    python scripts/seed_bronze.py
    python scripts/seed_bronze.py --force   # Sobrescreve arquivos existentes
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# === Conteúdo dos arquivos Bronze ===

FILES = {
    "data/bronze/calls/grooming-devolucao-2026-04-01.md": """\
# Transcrição — Grooming: Devolução de Produtos
**Data:** 2026-04-01
**Participantes:** Ana (PO), Carlos (Arquiteto), Diego (Dev), Fernanda (QA)
**Duração:** 52 min

---

## Contexto

Ana: Pessoal, vamos falar sobre a devolução de produtos. Hoje o cliente precisa ligar pro SAC para devolver qualquer coisa. A ideia é a gente fazer isso self-service no app.

Carlos: Faz sentido. Quanto tempo o SAC fica nessa fila?

Ana: Em média 8 minutos por atendimento. São umas 2.000 solicitações por mês. Dá pra imaginar o custo.

Diego: Tem alguma regra específica de prazo?

Ana: Sim. Para pessoa física, 30 dias corridos a partir da entrega. Isso está no PRD. Para pessoa jurídica é mais complicado — depende do contrato.

Fernanda: E os motivos de devolução? O cliente precisa justificar?

Ana: Precisa selecionar um motivo. São: produto com defeito, produto não era o que esperava, produto chegou errado, produto chegou danificado, e arrependimento da compra.

Carlos: Arrependimento só vale dentro do prazo legal né?

Ana: Exato. 7 dias corridos do CDC para arrependimento. 30 dias para defeito.

Diego: E o estorno? Como funciona?

Ana: O reembolso vai no método original de pagamento. Se pagou no cartão, estorna no cartão. Se pagou no PIX, estorna via PIX. Se usou crédito da loja, volta como crédito.

Carlos: Tem algum fluxo de aprovação manual?

Ana: Não para PF. O sistema aprova automaticamente se o pedido está dentro do prazo e o motivo é válido. Para PJ com contratos especiais, vai ter aprovação manual — mas isso é outra feature.

Diego: Foto do produto com defeito a gente vai pedir?

Ana: Para motivo "produto com defeito" e "produto chegou danificado", sim. Opcional para os outros motivos.

Fernanda: Quem gera a etiqueta de envio reverso?

Ana: A gente chama a API da transportadora — mesma que faz a entrega. Prazo para coletar é de 5 dias úteis após aprovação.

---

## Pontos em aberto

[A-01] **Devolução parcial**: o cliente pode devolver apenas parte dos itens de um pedido? Ana: "Ainda não decidimos. Deixa pra versão 2 por enquanto."

Diego: Isso vai impactar o modelo de dados...

Ana: Deixa aberto. Prioridade agora é a devolução total simples.

---

## Definição de escopo desta US

**Dentro:** devolução total de pedido PF, estorno automático, geração de etiqueta.
**Fora:** devolução parcial, devolução PJ (feature separada), troca de produto (feature separada).

---

## Próximos passos

- Carlos vai documentar a decisão técnica sobre o state machine da solicitação
- Diego vai estimar os pontos na próxima sprint
- Fernanda vai escrever os cenários de teste baseada neste grooming
""",

    "data/bronze/calls/refinamento-tecnico-devolucao-2026-04-05.md": """\
# Transcrição — Refinamento Técnico: Devolução de Produtos
**Data:** 2026-04-05
**Participantes:** Carlos (Arquiteto), Diego (Dev), Rafael (Dev), Beatriz (DevOps)
**Duração:** 45 min

---

## State Machine da Solicitação

Carlos: Vou apresentar o state machine que propus. Uma solicitação de devolução passa por estes estados:

```
PENDENTE → APROVADA → AGUARDANDO_COLETA → COLETADA → REEMBOLSO_PROCESSADO → CONCLUIDA
         ↘ REPROVADA
         ↘ CANCELADA_CLIENTE
```

Diego: Por que PENDENTE existe se você disse que aprovação é automática para PF?

Carlos: Bom ponto. Para PF dentro do prazo, vai direto para APROVADA. PENDENTE existe para edge cases: fraude detectada pelo sistema, primeiro pedido do cliente (verificação extra), ou se a API da transportadora estiver fora.

Rafael: E se o webhook de coleta não chegar?

Carlos: Timeout de 48h. Se não veio confirmação, o sistema envia novo evento para a transportadora. Três tentativas, depois entra em fila de operações manuais.

Beatriz: Isso vai SQS?

Carlos: Sim. Fila SQS com dead letter queue para os casos que falharam nas 3 tentativas. Monitoramento via CloudWatch.

Diego: E idempotência? O cliente pode submeter duas vezes?

Carlos: Chave de idempotência: combinação de order_id + customer_id + motivo. Se tentar criar segunda solicitação para o mesmo pedido no estado APROVADA ou posterior, retorna 409 Conflict.

Rafael: E se o reembolso falhar?

Carlos: A gente trata por tipo de pagamento. Cartão de crédito: a operadora confirma em até 72h, a gente acompanha via webhook. PIX: síncrono, sucesso ou falha imediata. Crédito da loja: operação interna, nunca falha. Se o estorno no cartão falhar depois de 3 tentativas, vira crédito na loja automaticamente — e notificamos o cliente.

---

## Decisões técnicas

[DT-01] **Persistência:** tabela `return_requests` no banco principal (PostgreSQL). Campos: id, order_id, customer_id, status, reason, items, created_at, updated_at, resolved_at.

[DT-02] **Fila:** SQS para eventos assíncronos (coleta, reembolso). Dead letter queue com alarme após 3 falhas.

[DT-03] **Idempotência:** chave composta order_id+customer_id. Retorna 409 se já existe solicitação ativa para o pedido.

[DT-04] **Webhook transportadora:** endpoint POST /webhooks/carrier/{provider}. Validação por HMAC-SHA256.

[DT-05] **Timeout coleta:** job rodando a cada hora verificando solicitações em AGUARDANDO_COLETA há mais de 48h.

---

## Performance

Diego: Qual o SLA esperado?

Carlos: p95 em 200ms para criação da solicitação (endpoint síncrono). Para consulta de status, p95 em 50ms (read-only, pode ser cacheado).

Rafael: E disponibilidade?

Carlos: 99.9% uptime para o endpoint de criação. Se a API da transportadora cair, a gente aprova a solicitação e agenda a coleta depois — não pode bloquear o cliente.

---

## Ponto em aberto

[A-02] **Gateway de pagamento fora por mais de 24h:** se o gateway estiver indisponível por mais de 24h após aprovação da devolução, como procedemos? Carlos: "Deixo em aberto. Precisamos alinhar com o time de financeiro antes de decidir."

---

## Próximos passos

- Diego e Rafael vão implementar o state machine e os endpoints
- Beatriz vai criar a fila SQS e dead letter queue
- Carlos vai documentar a API no Swagger
""",

    "data/bronze/docs/prd-devolucao-v2.md": """\
# PRD — Devolução de Produtos (Self-Service)
**Versão:** 2.0
**Autor:** Ana (PO)
**Data:** 2026-03-20
**Status:** Aprovado

---

## Objetivo

Permitir que clientes pessoa física solicitem a devolução de produtos diretamente pelo aplicativo, sem necessidade de contato com o SAC, reduzindo em 60% o volume de atendimentos relacionados a devoluções.

## Problema

Atualmente 100% das solicitações de devolução requerem atendimento humano (SAC). Com 2.000 solicitações/mês e tempo médio de 8 minutos por atendimento, isso representa custo operacional significativo e NPS negativo (clientes relatam demora e dificuldade).

## Solução

Feature self-service no aplicativo móvel (iOS e Android) que permite ao cliente:
1. Selecionar o pedido a ser devolvido
2. Informar o motivo
3. Receber etiqueta de envio reverso
4. Acompanhar o status da devolução
5. Receber o reembolso automaticamente

## Regras de Negócio

**RN-01 — Prazo PF:** Pessoa física tem 30 dias corridos a partir da data de entrega para solicitar devolução.

**RN-02 — Prazo CDC:** Para casos de arrependimento de compra, aplica-se o prazo legal de 7 dias corridos a partir da entrega (CDC Art. 49).

**RN-03 — Método de reembolso:** O reembolso é sempre processado no mesmo método de pagamento utilizado na compra. Exceção: falha no gateway após 3 tentativas converte para crédito na loja.

**RN-04 — Aprovação automática:** Solicitações de PF dentro do prazo com motivo válido são aprovadas automaticamente pelo sistema. Nenhuma intervenção humana é necessária para o fluxo padrão.

**RN-05 — Foto obrigatória:** Para os motivos "produto com defeito" e "produto chegou danificado", o upload de pelo menos 1 foto é obrigatório.

**RN-06 — Prazo de coleta:** Após aprovação, a transportadora tem 5 dias úteis para coletar o produto no endereço do cliente.

**RN-07 — Prazo de reembolso:** Após confirmação de recebimento do produto pela empresa, o reembolso é processado em até 5 dias úteis.

**RN-08 — Devolução parcial:** Não suportado nesta versão. [C-01] Nota: cliente TechCorp solicitou devolução parcial como requisito obrigatório — ver documento de requisitos de cliente enterprise.

## Escopo

**Dentro:** devolução total de pedido PF, aprovação automática, geração de etiqueta, acompanhamento de status, reembolso automático.

**Fora desta versão:** devolução parcial, devolução PJ, troca de produto, aprovação manual, integração com sistemas legados de cliente enterprise.

## Métricas de Sucesso

- Redução de 60% no volume de atendimentos SAC relacionados a devoluções
- NPS do processo de devolução >= 7.0
- Taxa de conclusão do fluxo digital >= 80%
- p95 do endpoint de criação <= 200ms
- Disponibilidade 99.9%

## Requisitos Não Funcionais

- **Performance:** endpoint de criação p95 <= 200ms; consulta de status p95 <= 50ms
- **Disponibilidade:** 99.9% uptime para endpoints críticos
- **Segurança:** autenticação JWT obrigatória; rate limiting 10 req/min por customer_id
- **Retenção de dados:** solicitações retidas por 5 anos (requisito fiscal)
""",

    "data/bronze/docs/requisitos-cliente-enterprise.md": """\
# Requisitos de Cliente Enterprise — Devolução de Produtos
**Cliente:** TechCorp Ltda
**Contrato:** ENT-2026-0042
**Data:** 2026-03-15
**Contato:** João Silva (CTO TechCorp)

---

## Contexto

TechCorp é um cliente B2B com contrato enterprise. Eles revendem nossos produtos para seus próprios clientes (B2B2C). Os requisitos abaixo são cláusulas contratuais para renovação do contrato em julho de 2026.

---

## Requisitos Obrigatórios

**ENT-01 — Devolução Parcial [C-03]:** TechCorp exige suporte a devolução parcial de pedidos. Um pedido pode ter múltiplos itens e o cliente final pode querer devolver apenas alguns. **Isso é requisito contratual — sem isso, TechCorp não renova o contrato.**

*Nota: o PRD v2.0 marca devolução parcial como "fora do escopo". Há contradição entre o PRD e este documento de requisitos de cliente.*

**ENT-02 — Prazo Estendido:** Para clientes TechCorp (identificados por customer_type=enterprise), o prazo de devolução é de 90 dias corridos (vs 30 dias para PF padrão).

**ENT-03 — Aprovação com Gestor:** Solicitações enterprise acima de R$ 5.000 requerem aprovação do gestor de conta TechCorp antes de serem processadas. O gestor recebe notificação via webhook.

**ENT-04 — Webhook de Status:** TechCorp quer receber webhook em cada mudança de status da solicitação. Endpoint configurável por cliente. Payload deve incluir: solicitação_id, status_anterior, status_novo, timestamp, itens devolvidos.

**ENT-05 — Integração SAP:** TechCorp usa SAP para gestão financeira. O reembolso deve ser disparado via SAP BAPI_ACC_DOCUMENT_POST em vez de gateway de pagamento padrão. Credenciais e documentação do SAP fornecidas pelo CTO TechCorp.

---

## Requisitos Desejáveis

**ENT-D01 — Relatório Mensal:** CSV com todas as devoluções do mês, enviado por email no primeiro dia útil.

**ENT-D02 — Portal de Gestão:** Interface web para gestores TechCorp acompanharem todas as solicitações dos seus clientes finais.

---

## Prazo

Os requisitos obrigatórios (ENT-01 a ENT-05) devem estar implementados até 30/06/2026 para renovação do contrato.

---

## Notas Internas

[C-03] A contradição entre este documento (devolução parcial obrigatória) e o PRD v2.0 (devolução parcial fora do escopo) precisa ser resolvida com Ana (PO) e liderança antes do início do desenvolvimento.

O prazo contratual de 30/06/2026 é real e o valor do contrato é significativo (~R$ 2M/ano).
""",

    "data/bronze/chats/slack-devolucao-2026-04-03.md": """\
# Thread Slack — Canal #produto-devolucoes
**Data:** 2026-04-03

---

**Ana [10:14]:** Pessoal, lembrete: o prazo de devolução para campanhas especiais (Black Friday, etc) é diferente do padrão. Preciso confirmar isso com o time jurídico antes de fecharmos o PRD.

**Carlos [10:17]:** Que prazo estamos pensando?

**Ana [10:19]:** Jurídico está sugerindo 45 dias para produtos de campanha [C-02]. O PRD atual diz 30 dias. Preciso de validação deles antes de atualizar.

**Diego [10:23]:** Enquanto isso, posso codificar o prazo como configurável por tipo de produto? Assim a gente não precisa fazer deploy pra mudar o prazo.

**Ana [10:25]:** Boa ideia. Coloca como variável de configuração por categoria de produto.

---

**Rafael [14:02]:** Carlos, uma dúvida sobre o vocabulary de status. A gente está usando "reversal" no código mas o negócio fala "estorno". Vou padronizar?

**Carlos [14:08]:** Padroniza para "estorno" na camada de negócio (API, documentação, mensagens para o usuário). "reversal" pode ficar nos comentários internos de código se necessário [V-01].

**Rafael [14:10]:** Perfeito. Vou criar um glossário no Confluence.

---

**Beatriz [16:45]:** Pessoal, a gente precisa pensar nos eventos Kafka pra essa feature. Quando aprovar uma devolução, precisamos publicar evento para:
- Time de logística (para agendar coleta)
- Time financeiro (para preparar reembolso)
- Time de analytics (para métricas de NPS)

**Carlos [16:52]:** Concordo. Evento `devolucao.aprovada` com payload completo. Eu documento o schema amanhã.

**Diego [16:55]:** E o evento de quando o produto chega no CD? Precisa de `devolucao.produto_recebido` para disparar o reembolso.

**Carlos [16:57]:** Sim. Vou adicionar ao diagrama de eventos. Vou usar CloudEvents spec para o payload.

---

**Ana [17:30]:** Lembrando que amanhã às 14h temos o refinamento técnico (veja o invite). Confirma presença: Carlos, Diego, Rafael, Beatriz.

**Carlos [17:31]:** Confirmado.
**Diego [17:31]:** Ok.
**Rafael [17:32]:** Estarei lá.
**Beatriz [17:35]:** Confirmado.
""",
}


def main():
    parser = argparse.ArgumentParser(description="Seed Bronze — gera dados simulados")
    parser.add_argument("--force", action="store_true", help="Sobrescreve arquivos existentes")
    args = parser.parse_args()

    created = 0
    skipped = 0

    print(">>> Gerando dados Bronze...")
    print()

    for filepath, content in FILES.items():
        # Criar diretório se não existe
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        if os.path.exists(filepath) and not args.force:
            words = len(open(filepath, "r", encoding="utf-8").read().split())
            print(f"  - {os.path.basename(filepath)} (já existe, {words} palavras — pulando)")
            skipped += 1
        else:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            words = len(content.split())
            action = "sobrescrito" if os.path.exists(filepath) else "criado"
            print(f"  + {os.path.basename(filepath)} ({words} palavras)")
            created += 1

    print()
    print(f"  Criados: {created} | Pulados: {skipped} | Total: {len(FILES)}")
    print()

    if created > 0 or skipped == len(FILES):
        print("  Dados Bronze prontos.")
        print("  Próximo passo: python scripts/run_ingestion.py --verbose")
    else:
        print("  Nenhum arquivo criado.")


if __name__ == "__main__":
    main()
