# AutoBox Interstellar

AUTOBOX INTERSTELLAR — BETA 0.10.0

ATUALIZAÇÃO
No Painel, use Verificar atualizações deste bot. Configurações e sessão do Opera são preservadas.
A coleta usa somente dados do jogo. OpenCV, NumPy e Pillow não são necessários.

KILL NPC: PRIMEIRO TESTE AUTOMÁTICO
1. Abra o jogo pelo bot e recupere a nave para pelo menos 80% de vida.
2. Escolha laser e míssil na aba Kill NPC. Pause a coleta com F9.
3. Na aba Kill NPC, marque um ou mais tipos de NPC.
4. Deixe o mapa vazio para testar onde está, ou informe um destino normal.
5. Clique Testar 1 NPC.
6. Acompanhe a primeira luta. Depois copie o diagnóstico da luta e envie no chat.

Este modo executa UMA luta e encerra. Ainda não existe repetição de NPCs.
Seleciona o NPC mais próximo do conjunto de tipos marcados, conserva ID e revisão, aproxima até o alcance e verifica ataque/dano.
Usa laser e míssil escolhidos no bot; none desativa o envio de mísseis pelo bot. Não compra munição nem escolhe jogadores como alvo.
Não repete Ctrl enquanto espera confirmação do ataque.
A parada usa a seleção explícita do mesmo NPC com ataque desligado pelo cliente, evitando alternar Ctrl novamente.
F9/F10 encerram o teste e tentam desligar os tiros; confira a mensagem de confirmação.
Vida mínima padrão: 40%. Sem a opção de reparo, o limite interrompe tiros. Com ela, começa a ir ao portal normal mais próximo enquanto confirma a parada; liga o reparador equipado apenas sem tiros ativos. Aguarda as condições do jogo (15 segundos sem combate). Encerra ao chegar ao portal com pelo menos 90% de vida; não pula nem reinicia o ataque. F9/F10 cancelam a recuperação.
Sem dados, sem dano/progresso ou alvo alterado, o teste encerra.
Confirma derrota quando observa dano, desaparecimento/vida zero do alvo e ganho de XP.
Não há garantia de confirmação quando outra nave mata o NPC ou a leitura se perde.
O diagnóstico inclui as ações do teste e se a parada foi confirmada.

REGISTRO MANUAL
Registrar luta manual pausa a coleta e observa por até 90 segundos.
Selecione um NPC, ataque, pare uma vez e ataque novamente; depois use Encerrar registro e Copiar diagnóstico.
O registro agora preserva seleção/ataque/parada mesmo com muitos movimentos.
Os campos do diagnóstico excluem tokens, chat e identidade de outros jogadores.

COLETA
F8 inicia a coleta, mesmo quando você está na aba Kill NPC. Não inicia combate.
F9 pausa; F10 para. Um percurso já aceito pelo jogo pode terminar.
O modo Dados seleciona a box mais próxima e mantém ID/revisão até terminar.
Caixas verdes são opcionais, usam chaves existentes e não compram chaves.
O coletor espera novas boxes quando o mapa não tem alvos, sem movimentação aleatória.
A janela dedicada pode ficar atrás de outros programas; funcionamento minimizado ainda não validado.

MAPAS
Coleta e Kill NPC têm destinos independentes. Vazio mantém o mapa atual.
Selecione um mapa da lista ou digite seu código, como 4-3.
Ir ao mapa só viaja. F8 viaja primeiro ao destino da coleta e então coleta.
Testar 1 NPC viaja ao destino de NPC antes de selecionar o alvo.
Usa a rota calculada pelo próprio cliente e portais normais; não usa CPU paga nem portal de galáxia.
Recusa acesso bloqueado, ataque ativo, vida baixa e dados ausentes. Encerra viagens sem progresso.
Confira a primeira viagem na sua partida.

PAINEL E CONTADORES
Mostra Uridium, créditos, XP, honra, nível e chaves verdes.
Uridium da sessão e por hora contam somente eventos de boxes durante coleta ativa, excluindo PET.
Estimativa começa após 60 segundos. Pausas, viagem e espera de reconexão/renascimento não entram no tempo ativo.
Os ganhos de combate não são contados como ganhos de boxes.
Saldos indisponíveis aparecem como traço. Contadores da sessão são zerados ao fechar o aplicativo.

RECONEXÃO E RENASCIMENTO DA COLETA
Reconexão opcional: aguarda dados, usa botões normais do cliente e recarrega quando necessário.
F9/F10 cancelam tentativas. Autenticação exige login manual; não reabre navegador fechado pelo usuário.
Renascimento opcional: Base, Portal ou Local, com teto de gasto inicialmente zero Uridium.
Ao atingir o limite de mortes (padrão 3), encerra antes de renascer novamente.
Vida em 25% ou menos pausa coleta. Renascimento local pode exigir recuperação manual.
Essas retomadas automáticas são da coleta; o teste de NPC encerra se morrer ou perder leitura.

VALIDAÇÃO
125 testes Python, testes simulados da navegação e da integração de combate.
A integração de combate foi exercitada com os handlers de seleção, Ctrl e ataque do cliente fornecido.
Isso não substitui o primeiro teste acompanhado na sua partida.

Instalação nova: Python 3.11+; execute INSTALAR_E_ABRIR.bat.

Beta 0.10.0: se o NPC ainda não puder ser selecionado na tela, aproxima mais do mesmo alvo e tenta novamente, com limite de tempo.

MOVIMENTO CIRCULAR E REPARO (EXPERIMENTAL)
Circular ao redor do NPC: distância desejada de 150 a 800 unidades, padrão 450. Compara os sentidos para preferir maior distância dos outros NPCs. Não garante evitar dano; o alcance inimigo ainda não foi medido.
Vida no limite: ir ao portal e ativar reparador é opcional e começa desmarcado. Requer CPU/robô equipado. Movimento e proximidade do portal não garantem proteção nem início do reparo. Sem confirmação de ativação, encerra sem alternar novamente o botão. A recuperação tem limite de 3 minutos.
Validado com testes simulados; acompanhe a primeira luta na partida.

Beta 0.10.0: ativa ataque pelo cliente após confirmação da seleção, mesmo se o NPC se afastar; continua aproximando sem alternar Ctrl. O jogo controla o alcance efetivo. Aproximação busca um ponto mais próximo para perseguir alvos móveis. Diagnóstico inclui distância.

Beta 0.10.0: seleção de múltiplos tipos por caixas de marcação; escolhe o NPC mais próximo entre os tipos marcados. Continua uma luta por teste. Corrige contraste de listas, campos numéricos e tabelas.

Beta 0.10.0: aproximação direta e atualizada antes de selecionar; confirma ataque antes de afastar. Persegue o mesmo NPC ao sair da distância configurada, inclusive com pouca vida. Movimento circular opcional, distância de combate preservada também sem circular. Não garante ausência de dano; teste de uma luta.

Beta 0.10.0: distância configurável até 800. Padrão continua 450; valores acima do alcance da arma podem interromper o dano e encerrar por falta de progresso.

Beta 0.10.0: retorno por vida baixa não depende da confirmação inicial de parada; o reparo continua condicionado ao fim dos tiros. Opção experimental Levar NPC ao portal: após atacar, segue ao portal normal mais próximo e circula a 100 unidades do portal, mantendo o mesmo alvo. Este modo substitui o círculo em torno do NPC e pode sair do alcance se ele não acompanhar. Não pula portal. Não garante proteção contra NPCs provocados. Teste acompanhado.

Beta 0.10.0: antecipa o próximo ponto da curva pela velocidade e atualiza o trajeto com mais frequência para reduzir paradas. Aplicado ao círculo do NPC e do portal. Diagnóstico de recuperação mostra distância ao portal e estado atual dos tiros.

Beta 0.10.0: vida baixa detectada pelo cliente entre a leitura e o comando também aciona a recuperação, quando habilitada, em vez de encerrar como erro de movimento.

Beta 0.10.0: alvo removido durante comando passa pela confirmação de recompensa por até 2 segundos; não é tratado como erro de aproximação e não conta derrota sem evidência.

Beta 0.10.0: lasers LCB-10, MCB-25, MCB-50, UCB-100, SAB-50 e RSB-75. Mísseis R-310, PLT-2026, PLT-2021 e PLT-3030, ou none (desativado). Seleciona pelos controles nativos, aguarda confirmação e respeita alcance e recarga do míssil. Sem estoque, não compra; laser encerra, míssil é omitido. Para usar somente o escolhido, desative a troca automática de munição e CPUs automáticas de disparo no próprio jogo. Se o jogo não aceitar a seleção do laser pela barra, selecione o mesmo laser manualmente antes do teste. SAB-50 absorve escudo e pode não finalizar o NPC sozinho.
