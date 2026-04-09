# Refinamento Técnico — Devolução de Produtos
**Data:** 2026-04-05
**Participantes:** Carlos (Arquiteto), Pedro (Dev Backend), Julia (Dev Frontend), Marina (QA)
**Duração:** 1h30

---

## Decisões

### 1. API Design

Definidos os endpoints principais do módulo:

| Método | Rota | Descrição |
|---|---|---|
| POST | `/api/v1/returns` | Cria solicitação de devolução |
| GET | `/api/v1/returns/{id}` | Consulta status de uma devolução |
| GET | `/api/v1/returns?order_id={id}` | Lista devoluções de um pedido |
| PATCH | `/api/v1/returns/{id}/cancel` | Cancela solicitação (somente antes da coleta) |

**Carlos:** O endpoint de criação precisa responder rápido — o processamento de estorno vai ser assíncrono, então o POST retorna imediatamente com o status `requested` e o protocolo da devolução. O cliente não espera o estorno terminar.

**Pedro:** Faz sentido. Aí a gente tem o polling via `GET /returns/{id}` ou notificação por e-mail quando o status mudar.

**Julia:** Preciso saber quais status existem pra montar o componente de timeline no frontend.

### 2. State Machine

Fluxo de estados definido para a devolução:

```
requested → approved → shipping_label_sent → in_transit → received → inspecting → refunded
                                                                                  ↘ rejected
```

Para clientes PJ com pedidos acima de R$ 5.000, há estado adicional de aprovação:

```
requested → pending_approval → approved → shipping_label_sent → ...
```

**Carlos:** O `rejected` ocorre na inspeção (produto com uso sem defeito) ou se o prazo expirou. Precisamos logar o motivo.

**Pedro:** Vou documentar as transições válidas junto com o design da API.

### 3. Integrações

#### 3.1 LogiTrack (Logística Reversa)

Comunicação via **fila SQS**: quando aprovada, publicamos o evento `return.approved`. O consumidor SQS agenda a coleta no LogiTrack e retorna o código de rastreio.

**Carlos:** SQS porque o LogiTrack tem latência variável. Não queremos que a instabilidade deles afete nosso fluxo principal.

#### 3.2 Gateway XPay (Estorno)

Chamada HTTP **síncrona** com retry exponencial: máximo 3 tentativas (1s, 2s, 4s). Falhas vão para **fila de reprocessamento**.

Idempotência via `idempotency_key` (UUID v4 gerado na criação da devolução) — o XPay ignora duplicatas com a mesma key.

**Carlos:** Rate limit de 100 req/min do XPay. Em operação normal tudo bem, mas reprocessamento batch pode estourar — throttling obrigatório no consumidor.

#### 3.3 Kafka (Analytics)

Evento publicado no Kafka a cada transição de status. Payload: `return_id`, `order_id`, `status_from`, `status_to`, `timestamp`. Time de dados consome para analytics.

### 4. Observabilidade

- Logs estruturados (JSON) com `correlation_id` em todas as chamadas — do endpoint de criação até as integrações externas
- Métricas de latência do estorno no **Datadog**: histograma do tempo entre `approved` e `refunded`
- Alerta configurado no Datadog: **taxa de falha de estorno > 5%** em janela de 15 minutos dispara alerta para o canal #ops-alertas

**Carlos:** O `correlation_id` é fundamental pra rastrear uma devolução por todos os sistemas. Sem isso, debug em produção vira pesadelo.

### 5. Frontend

**Julia:** Componente de **timeline de status** reutilizável — cada etapa com ícone, descrição e timestamp. Similar ao rastreio de entrega, mas no sentido inverso.

**Pedro:** Vou garantir que `GET /returns/{id}` retorne o histórico de transições, não só o status atual.

---

## Critérios de Aceite (QA)

**Marina:** Meu principal critério de aceite crítico: **o estorno nunca pode ser processado em duplicidade.** Se o sistema falhar no meio — timeout, crash, reinicialização — o retry não pode gerar um segundo estorno no cartão ou PIX do cliente. Isso é inaceitável do ponto de vista do cliente e cria problema financeiro.

**Carlos:** A idempotência via `idempotency_key` resolve isso. Confirmado.

**Marina:** Preciso de teste de caos: simular falha após envio ao XPay mas antes de confirmar status no banco.

**Pedro:** Consigo. Vou criar um endpoint de teste que injeta falha nesse ponto.

---

## Restrições Técnicas

- **Rate limit Gateway XPay:** 100 requisições por minuto. Em Black Friday, estimativa de pico de ~500 devoluções/hora (≈ 8/min em distribuição uniforme), mas spikes de reprocessamento podem ultrapassar. Throttling obrigatório no consumidor de reprocessamento.
- **Webhook LogiTrack:** SLA de entrega de etiqueta de até 2 horas após recebimento do evento. Devolução permanece em `approved` até a etiqueta ser gerada.

---

## Pendências

| Item | Responsável | Prazo |
|---|---|---|
| Como lidar com Gateway XPay fora do ar por mais de 24h? | Carlos + Pedro | Próxima reunião |
| Documentação das transições de estado | Pedro | 2026-04-07 |
| Design do componente de timeline | Julia | 2026-04-08 |

**Ambiguidade em aberto — A-02:** Se o Gateway XPay ficar indisponível por mais de 24 horas, qual a estratégia?

- **Carlos:** dead letter queue com alerta para operações manuais — não podemos retentar indefinidamente
- **Pedro:** retry com backoff infinito e alerta, mas deixa o sistema tentar resolver sozinho

**Decisão adiada para a próxima reunião.** Precisamos de mais informações sobre o histórico de downtime do XPay e qual é o SLA deles.
