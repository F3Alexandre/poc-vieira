# Grooming — Devolução de Produtos
**Data:** 2026-04-01
**Participantes:** Ana (PO), Carlos (Arquiteto), Pedro (Dev Backend)
**Duração:** 45 min

---

**Ana:** Galera, bora começar. A pauta de hoje é a feature de devolução de produtos. Temos pressão do comercial porque 20% das reclamações no SAC são sobre isso. Clientes insatisfeitos, NPS caindo. Quero alinhar escopo e já começar a quebrar as histórias.

**Pedro:** Beleza. Mas antes, qual é o fluxo básico que a gente tá imaginando? Tipo, o cliente vai lá e faz o quê?

**Ana:** Boa pergunta. A ideia é: cliente acessa "Meus Pedidos", seleciona o pedido que quer devolver, clica em "Solicitar Devolução", escolhe o motivo, confirma e recebe um número de protocolo. Simples assim.

**Carlos:** Simples na aparência. Mas tem bastante coisa por baixo. Precisamos definir as regras de elegibilidade logo de cara.

**Ana:** Sim. Prazo pra pessoa física é 30 dias corridos a partir da data de entrega. Isso é CDC, não tem como mudar.

**Pedro:** E pra PJ? A gente tem aqueles clientes enterprise com contrato.

**Ana:** Pra empresa com contrato enterprise, o prazo é conforme o contrato. Pode ser 60 ou 90 dias, depende do que foi negociado. Cada contrato tem o prazo dele.

**Carlos:** Ok. E condições do produto? O cliente não pode usar o produto e querer devolver.

**Ana:** Exato. O produto tem que estar na embalagem original e sem sinais de uso. Mas tem uma exceção importante: se for defeito de fabricação, o prazo segue a garantia legal, que é 90 dias. E aí o estado do produto não importa tanto.

**Pedro:** Faz sentido. E o reembolso, como funciona? Devolvemos o valor pelo mesmo método de pagamento?

**Ana:** Sim. Estorno sempre no mesmo método de pagamento original. Então se pagou no cartão de crédito, volta pro cartão. Se foi PIX, volta por PIX.

**Carlos:** Os prazos de estorno são diferentes. Cartão de crédito pode levar até duas faturas pra aparecer, dependendo da operadora. PIX é mais rápido, até 24 horas úteis.

**Pedro:** E como a gente faz esse estorno tecnicamente? Tem algum gateway específico?

**Carlos:** Vamos integrar com o Gateway XPay. Eles têm uma API de estorno. Minha sugestão é usar mensageria assíncrona pra esse processo — a gente não quer bloquear o usuário esperando a resposta do gateway. O cliente confirma a devolução, a gente dá o protocolo, e o estorno roda em background.

**Pedro:** Faz sentido. Mas aí o cliente precisa saber o status, né? Tipo, como ele sabe que o estorno foi feito?

**Carlos:** Boa. Isso entra no fluxo de notificação. Mas vamos resolver depois. Agora quero garantir que as regras de negócio estão fechadas.

**Ana:** Motivos de devolução: arrependimento, produto diferente do anunciado, defeito e produto danificado no transporte. Cada motivo tem tratamento diferente. Arrependimento, por exemplo, o frete de retorno é por conta do cliente. Se for defeito, o frete é por nossa conta.

**Pedro:** Entendido. E sobre devolução parcial? Tipo, o cliente comprou 3 produtos num pedido só e quer devolver apenas um. Como fica?

**Ana:** Hm... Boa pergunta. Precisamos ver isso com o financeiro, porque o estorno parcial complica.

**Carlos:** Tecnicamente é possível, mas complica bastante o estorno, principalmente se o pedido teve um desconto aplicado sobre o total. Como você calcula o valor do estorno de um item só?

**Pedro:** Pois é. Acho que vamos deixar pra v2 isso. A gente entrega o fluxo principal primeiro.

**Ana:** Peraí, não vamos decidir isso agora. Preciso consultar o financeiro antes. Deixa em aberto por enquanto.

**Carlos:** Concordo. Coloca como pendência.

**Pedro:** Beleza. E produto digital? App, e-book, licença de software?

**Ana:** Por enquanto só produto físico. Produto digital é outra discussão, tem implicações legais diferentes. Fora do escopo.

**Carlos:** E troca de produto?

**Ana:** Também fora. Troca é outra feature. Aqui é só devolução com estorno de dinheiro.

**Pedro:** Ok, ficou claro. Ah, e requisito de performance? Tipo, o endpoint precisa responder em quanto tempo?

**Ana:** Precisa ser rápido. O cliente não pode ficar esperando. Não gosto de tela de loading longa.

**Carlos:** Vou verificar o SLA do Gateway XPay pra gente ter um número concreto. Mas o endpoint de criação da solicitação tem que ser ágil — a integração com o gateway vai ser assíncrona de qualquer forma, então não tem motivo pra ser lento.

**Ana:** Isso. Galera, acho que tá bom por hoje. Pendências: devolução parcial (aguardando financeiro), SLA do gateway. Restante tá alinhado. Vou escrever o PRD com base nisso.

**Pedro:** Show. Posso já começar a pensar na estrutura da API.

**Carlos:** Manda ver. Mas alinha comigo antes de abrir o PR, quero revisar o design.

**Ana:** Ok, encerrando. Obrigada galera.

---

*Pendências registradas:*
- Devolução parcial: aguarda alinhamento com financeiro (sem decisão)
- SLA de performance: Carlos vai verificar com Gateway XPay
