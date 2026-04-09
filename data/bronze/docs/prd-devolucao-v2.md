# PRD — Devolução de Produtos
**Versão:** 2.0
**Data:** 2026-04-02
**Autora:** Ana Souza (Product Owner)
**Status:** Em revisão

---

## 1. Visão Geral

### 1.1 Contexto e motivação

O processo atual de devolução de produtos é inteiramente manual: o consumidor abre um ticket no Zendesk, o operador de suporte analisa o caso, envia instruções por e-mail, e o estorno é feito manualmente pela equipe financeira. Esse processo gera gargalos operacionais, experiência insatisfatória e altos custos de suporte.

**Dados que justificam a feature:**
- 20% de todas as reclamações abertas no SAC referem-se ao processo de devolução
- O NPS da empresa caiu 15 pontos nos últimos dois trimestres, diretamente associado à fricção no processo de estorno
- Tempo médio de resolução atual: 12 dias úteis
- Meta com a nova feature: reduzir para até 5 dias úteis

### 1.2 Objetivo

Implementar um módulo de autoatendimento para devolução de produtos físicos, com geração automática de etiqueta de coleta e processamento de estorno integrado ao Gateway XPay.

---

## 2. Personas

| Persona | Perfil | Necessidade principal |
|---|---|---|
| **Cliente PF** | Consumidor individual, compra esporádica | Processo simples, prazo claro, estorno rápido |
| **Cliente PJ Enterprise** | Empresa com contrato, volume alto | Controle de aprovação, integração com ERP, relatório mensal |
| **Operador de Suporte** | Atendente do SAC | Visibilidade de status, capacidade de intervir manualmente |

---

## 3. Regras de Negócio

- **RN-01:** O prazo para solicitação de devolução para cliente pessoa física (consumidor individual) é de **30 dias corridos** a partir da data de entrega confirmada. Prazo improrrogável.
- **RN-02:** Para clientes PJ com contrato enterprise, o prazo de devolução é definido em contrato. Pode variar entre 60 e 90 dias conforme negociação.
- **RN-03:** O produto deve ser devolvido na embalagem original e sem sinais de uso. Exceção: produtos com defeito de fabricação comprovado, onde o estado da embalagem não é critério de elegibilidade.
- **RN-04:** O estorno é sempre realizado no mesmo método de pagamento utilizado na compra original (cartão de crédito, PIX, boleto, etc.).
- **RN-05:** Cliente PF está limitado a **3 solicitações de devolução por mês**. Excedendo esse limite, o sistema bloqueia novas solicitações até o mês seguinte.
- **RN-06:** Pedidos com valor total acima de **R$ 5.000** requerem aprovação do gestor de operações antes de serem processados.
- **RN-07:** Os motivos aceitos para devolução são: (a) arrependimento — frete de retorno por conta do cliente; (b) produto diferente do anunciado — frete por conta da empresa; (c) defeito de fabricação — frete por conta da empresa, prazo estendido para 90 dias; (d) dano no transporte — frete por conta da empresa.
- **RN-08:** O estorno cobre o valor integral do produto. O valor do frete original **não é estornado**, exceto nos casos em que o motivo seja defeito de fabricação ou erro da empresa (produto errado, dano no transporte).

---

## 4. Requisitos Não Funcionais

| Requisito | Métrica | Observação |
|---|---|---|
| Performance | Endpoint `POST /returns` deve responder em até **200ms (p95)** | Processamento de estorno é assíncrono |
| Disponibilidade | **99,9% de uptime** mensal | Inclui janelas de manutenção planejadas |
| Prazo de estorno | Estorno iniciado em até **5 dias úteis** após recebimento do produto no CD | Dependente de inspeção do produto |
| Segurança | Autenticação via **OAuth 2.0**; dados de pagamento não trafegam pelo backend da aplicação | Tokenização via Gateway XPay |

---

## 5. Integrações

| Sistema | Finalidade | Tipo de integração |
|---|---|---|
| **Gateway XPay** | Processamento de estorno após aprovação da devolução | API REST (assíncrona) |
| **LogiTrack** | Logística reversa: agendamento de coleta, geração de etiqueta, rastreio | API REST |
| **Zendesk** | Criação automática de ticket de suporte quando o motivo for defeito de fabricação | Webhook |

---

## 6. Fora do Escopo

Os itens abaixo **não fazem parte desta release** e serão endereçados futuramente:

- **Troca de produto:** feature separada, com fluxo e regras distintas
- **Devolução de produto digital:** requer análise jurídica específica
- **Devolução parcial de pedido:** decidido para v2 — cliente poderá devolver itens individuais de um pedido com múltiplos itens em versão futura

---

## 7. Critérios de Aceite de Alto Nível

- O consumidor consegue iniciar uma solicitação de devolução sem contatar o SAC
- O operador de suporte consegue visualizar e gerenciar todas as solicitações em painel dedicado
- O estorno é processado automaticamente via Gateway XPay sem intervenção manual
- Nenhum estorno é processado em duplicidade
- A coleta do produto é agendada automaticamente via LogiTrack após aprovação

