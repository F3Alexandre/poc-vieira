# Requisitos de Devolução — TechCorp Ltda
**Contrato:** ENT-2026-0042
**Data:** 2026-03-28
**Versão:** 1.0
**Responsável:** Maria Silva (Gerente de Compras, TechCorp)

---

## 1. Introdução

A TechCorp Ltda, doravante denominada **Contratante**, possui contrato corporativo ativo (ENT-2026-0042) para aquisição recorrente de equipamentos de TI e periféricos. Dado o volume de compras mensais e as especificidades operacionais da Contratante, este documento formaliza os requisitos mínimos que o módulo de devolução de produtos deve atender para que a TechCorp Ltda possa adotar a solução em substituição ao processo atual de solicitação via e-mail.

O não atendimento integral dos requisitos aqui descritos impossibilita a adoção da feature pela Contratante e constitui descumprimento de SLA contratual conforme cláusula 8.3 do contrato ENT-2026-0042.

---

## 2. Requisitos Funcionais

### 2.1 Prazo de Devolução

Conforme cláusula 5.1 do contrato ENT-2026-0042, o prazo para solicitação de devolução aplicável à TechCorp Ltda é de **90 dias corridos** a partir da data de entrega confirmada no sistema de rastreio. Este prazo sobrepõe o prazo padrão da plataforma e deve ser respeitado independentemente de configuração global.

### 2.2 Fluxo de Aprovação Interna

Toda solicitação de devolução deve passar pelo seguinte fluxo de aprovação:

- **Itens com valor unitário até R$ 5.000:** qualquer funcionário autorizado da TechCorp cadastrado na plataforma pode solicitar a devolução. A solicitação segue diretamente para processamento.
- **Itens com valor unitário acima de R$ 5.000:** a solicitação deve aguardar aprovação do Gestor de Compras designado antes de ser encaminhada para processamento. O sistema deve enviar notificação por e-mail ao gestor responsável no momento em que a solicitação é criada.

### 2.3 Devolução Parcial de Pedido

A **devolução parcial é requisito obrigatório** para o atendimento à TechCorp Ltda. A Contratante realiza compras em lote (ex.: 50 notebooks por pedido) e frequentemente necessita devolver itens específicos sem afetar os demais itens do pedido. O sistema deve permitir:

- Seleção de itens individuais dentro de um pedido para devolução
- Cálculo proporcional do estorno por item, incluindo rateio de descontos aplicados no pedido original
- Geração de etiqueta de coleta apenas para os itens selecionados

A ausência desta funcionalidade inviabiliza operacionalmente o uso da plataforma pela TechCorp Ltda.

### 2.4 Campo Customizado: Centro de Custo

Toda solicitação de devolução deve incluir o campo **"Centro de Custo"** (obrigatório para a TechCorp). Este campo deve ser preenchido pelo solicitante no momento da criação da solicitação e deve ser incluído em todos os registros e relatórios relacionados.

---

## 3. Requisitos de Integração

### 3.1 Integração com ERP (SAP — TechCorp)

O sistema de devolução deve notificar o ERP interno da TechCorp (SAP — ERP TechCorp) a cada mudança de status de devolução. A integração será realizada via **webhook**, com chamada HTTP POST para o endpoint fornecido pela TechCorp.

**Payload esperado:**
```json
{
  "order_id": "string",
  "return_id": "string",
  "items": [{ "sku": "string", "quantity": "integer", "unit_value": "number" }],
  "status": "string",
  "timestamp": "ISO 8601"
}
```

Falhas na entrega do webhook devem ser retentadas por no mínimo 3 vezes com intervalo exponencial antes de gerar alerta para a equipe de operações da Contratante.

### 3.2 Relatório Mensal

A plataforma deve gerar e enviar automaticamente um relatório mensal de devoluções em formato **CSV** para o e-mail cadastrado da TechCorp, até o **5º dia útil do mês seguinte**.

**Campos obrigatórios no relatório:**
- Data de solicitação
- Número do pedido
- SKU e descrição do produto
- Motivo da devolução
- Valor estornado
- Status final
- Tempo total de processamento (em dias úteis)
- Centro de Custo

---

## 4. SLAs Específicos

| Indicador | SLA contratado |
|---|---|
| Tempo para iniciar processamento do estorno (após aprovação interna) | **48 horas corridas** |
| Disponibilidade do módulo de devolução | **99,9% mensal** |
| Entrega do webhook para SAP (ERP TechCorp) | **30 segundos** após mudança de status |
| Envio do relatório mensal | Até o **5º dia útil** do mês seguinte |

O descumprimento reiterado dos SLAs acima sujeita a Contratada a penalidades conforme cláusula 9.2 do contrato ENT-2026-0042.

---

## 5. Observações Finais

A TechCorp Ltda está disponível para sessão de validação técnica com a equipe de desenvolvimento para esclarecimento dos requisitos de integração. Contato: integrações@techcorp.com.br.

Este documento deve ser tratado como adendo técnico ao contrato ENT-2026-0042 e tem validade jurídica equivalente.
