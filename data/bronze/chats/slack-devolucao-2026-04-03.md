# Thread: #proj-devolucao
**Canal:** #proj-devolucao
**Data:** 2026-04-03

---

**[09:02] Pedro:** bom dia galera! comecei a olhar a API do Gateway XPay ontem à noite

**[09:05] Ana:** bom dia! e aí, tudo ok?

**[09:07] Pedro:** mais ou menos 😅 descobri que o endpoint de estorno deles tem rate limit de 100 req/min. isso pode ser um problema em dias de pico

**[09:09] Carlos:** previsto. vamos precisar de throttling no nosso lado mesmo. deixa eu calcular... em Black Friday com pico de 500 devoluções/hora dá uns 8/min, tá bem dentro. o problema seria se tiver um spike de reprocessamento, aí pode estourar

**[09:11] Pedro:** exato, por isso quero garantir idempotência no endpoint de estorno. se a gente fizer retry sem idempotency key, o cara pode ser estornado duas vezes 😬

**[09:13] Carlos:** 100%. usa idempotency key gerada no momento que a devolução é criada. aí qualquer retry com a mesma key o gateway ignora. isso é básico de API de pagamento

**[09:15] Pedro:** boa, vou implementar assim

**[09:18] Pedro:** ah Carlos, uma dúvida sobre as regras de negócio. e se o produto já foi usado mas tem defeito? tipo, o cara usou o produto por 2 semanas, aí defeituou

**[09:21] Ana:** produto usado não aceita devolução por arrependimento, isso é claro. mas se for defeito de fabricação comprovado, aí aceita sim, independente de uso. o CDC ampara

**[09:23] Pedro:** entendi. e se o cara abriu a caixa mas não usou? tipo, eletrônico que tirou o lacre mas nunca ligou

**[09:25] Ana:** aberto sem uso aceita sim, desde que esteja com todos os acessórios e componentes originais. lacre aberto não invalida por si só

**[09:26] Pedro:** 👍

**[09:31] Pedro:** Carlos, outra coisa. eu tava lendo a doc do XPay e eles chamam o processo de "reversal". mas no nosso PRD tá "estorno". são a mesma coisa?

**[09:34] Carlos:** sim, mesmo conceito. "reversal" e "return request" são os termos da API do Gateway XPay, faz parte do vocabulário deles. no **nosso** domínio a gente usa "estorno" e "devolução". isso é importante: quando a gente escrever código e comentários, usa os termos do nosso domínio. o "reversal" fica só na camada de integração com o XPay

**[09:36] Pedro:** ah faz sentido, obrigado pela correção

**[09:37] Carlos:** esse tipo de confusão gera bug quando a gente mistura os domínios

**[09:45] Ana:** pessoal, o time de dados pediu pra gente publicar eventos de devolução no Kafka. eles precisam pra analytics. toda vez que uma devolução mudar de status, a gente publica um evento

**[09:47] Carlos:** faz sentido. Carlos, já estava prevendo isso na arquitetura

**[09:48] Pedro:** haha vc falou de vc mesmo em terceira pessoa 😂

**[09:49] Carlos:** lol. quero dizer: já tava previsto

**[09:51] Ana:** hahaha. mas confirmando então: eventos no Kafka para cada mudança de status da devolução

**[09:52] Pedro:** 👍 vou incluir no design da API

**[10:03] Pedro:** ah Ana, uma coisa que ficou na minha cabeça. e se o cliente faz a devolução numa campanha promocional? tipo, black friday tem prazo estendido?

**[10:07] Ana:** boa pergunta! o prazo padrão pra PF é 30 dias, mas em campanhas promocionais a gente pode estender pra 45 dias. isso vai ser configurável. ex: black friday, aniversário da loja, etc.

**[10:09] Pedro:** isso tá no PRD?

**[10:10] Ana:** não tá explícito ainda, vou adicionar. mas já considera isso na implementação — o prazo precisa ser parametrizável por campanha

**[10:12] Carlos:** faz isso via feature flag ou tabela de configuração, não hardcode o prazo

**[10:13] Pedro:** entendido

**[10:18] Pedro:** seria muito legal ter uma tela de acompanhamento do status da devolução tipo rastreio de entrega, mas invertido. o cliente vê em que etapa tá: "solicitado → aprovado → coletado → em análise → estorno realizado"

**[10:20] Ana:** adorei essa ideia, anota pra não perder

**[10:21] Carlos:** é uma timeline mesmo. a Julia pode fazer um componente reutilizável disso

**[10:22] Pedro:** 👍

**[10:35] Pedro:** ok pessoal, vou fechar aqui. vou montar o design da API e mando pra revisão do Carlos antes de implementar

**[10:36] Carlos:** blz

**[10:36] Ana:** 👍 obrigada!
