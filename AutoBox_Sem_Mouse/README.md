# AutoBox Sem Mouse

Bot independente, exclusivo de coleta visual no Interstellar em uma sessao dedicada do Opera GX.

Baixe [AutoBox_Sem_Mouse.zip](AutoBox_Sem_Mouse.zip), extraia e execute INSTALAR_E_ABRIR.bat. Feche o bot antigo para evitar conflitos de atalhos.

Configure mapa, modelo de box e area da nave. Minimap e notificacoes sao opcionais. F8 inicia, F9 pausa e F10 para.

Esta beta possui configuracoes e atualizador proprios. A logica e a interface foram verificadas com navegador simulado; a coleta real ainda precisa de validacao. Nao ha garantia de ausencia de banimento.

Consulte LEIA-ME.txt para detalhes.

Beta 0.1.1: detector com mais escalas e recorte do objeto luminoso; teste visual de deteccao sem cliques; busca limitada a 24 s sem candidatos, alternancia de patrulha e retorno ao centro da zona marcada ao reconhecer radiacao. Retorno depende de calibracao correta e precisa de validacao no jogo.

Beta 0.1.2: converte coordenadas da captura para pixels CSS medidos no navegador antes de clicar, com validacao de pagina/zoom entre captura e clique. A previa informa os dois pontos. 56 testes passaram; a abertura de um Opera local para teste foi impedida pelo ambiente, e a coleta real ainda depende de validacao.

Referencia das unidades de coordenadas: [Playwright Mouse](https://playwright.dev/python/docs/api/class-mouse) e [CDP Input](https://chromedevtools.github.io/devtools-protocol/tot/Input/#method-dispatchMouseEvent).

Beta 0.1.3: prioridade ao box mais proximo sem desvio para outro durante reverificacao, rastreamento local com previsao curta de movimento, protecao restrita ao centro da nave e busca estendida para a faixa inferior (opcao ligada por padrao, minimapa excluido). Aproximacao exige desaparecimento a ate 22 pixels da nave, com recuperacao de perdas breves.

Validacao: 64 testes passaram. Na analise local do print fornecido, a area antiga excluia a box inferior; a area estendida a reconheceu com 0.975 de confianca. Isso valida esse caso de imagem; a coleta em movimento ainda precisa de validacao na partida.

Beta 0.1.4: rejeita um candidato quando seu brilho faz parte de um objeto conectado muito maior que o modelo, como a borda do portal. O filtro vale na busca, no rastreamento e no teste de deteccao.

Validacao: o falso positivo da borda no print fornecido foi removido; boxes reais dos prints anteriores foram preservadas. 67 testes passaram, incluindo estrutura grande com brilho que a versao anterior aceitava com 0.998 de correlacao e uma box isolada ao lado da estrutura. A coleta em movimento ainda depende de validacao no jogo.

Beta 0.2.0: primeira etapa da interface inspirada em organizacao por modos. Tema escuro, abas Painel/Coleta/Navegador/Diagnostico, controles de coleta permanentes, contadores e tempo ativo. Combate e Recuperacao estao desativados e ainda nao executam acoes. Preserva o motor de coleta da 0.1.4, incluindo a rejeicao do falso positivo do portal; configuracao, modelo e perfil existentes usam os mesmos caminhos.

Validacao desta etapa: 70 testes passaram, incluindo interface Tk, estados das abas, tempo ativo sem contar pausas, contadores, deteccao e servico de navegador simulado. A nova interface nao acrescenta leitura de memoria nem validacao real de combate.

Beta 0.3.0: primeira etapa de leitura de dados ao vivo. Observa EventSource pelo CDP da janela dedicada, reconstrói full + patches de objeto/valor observados e mostra a aba Dados. Sequencias interrompidas, conexoes antigas e estados desatualizados nao produzem alvo atual. Operacoes de patch relevantes ainda desconhecidas interrompem a leitura ate novo full. O leitor filtra os campos mantidos em memoria e nao registra tokens ou chat. A coleta automatica permanece visual nesta etapa.

Validacao: 91 testes, incluindo callbacks CDP simulados, reconexao, sequencia, atomicidade, limpeza de campos privados e painel. Replay das 22 mensagens fornecidas reconstruiu 40 boxes, 4 portais e a box mais proxima. Nenhum dado original da sessao foi incluido no pacote ou repositorio. A recepcao no Opera conectado ao jogo ainda depende de validacao pelo usuario.

Referencias da observacao: [CDP Network eventSourceMessageReceived](https://chromedevtools.github.io/devtools-protocol/tot/Network/#event-eventSourceMessageReceived), [Playwright CDPSession](https://playwright.dev/python/docs/api/class-cdpsession).

Beta 0.3.1: a janela dedicada inicia em https://interstellar-verse.com/ para permitir login e entrada no mapa pelo site. O reconhecimento da pagina de jogo continua separado do endereco inicial.

Beta 0.4.0: motor de decisao por ID/revisao e coordenadas em validacao. Seleciona a box mais proxima, preserva o alvo, estima viagem, detecta falta de progresso e exige proximidade + desaparecimento + aumento do contador para indicar coleta observada. O plano ainda nao envia comandos ao jogo. A chegada usa raio inicial estimado de 100 unidades, ainda nao validado no jogo.

A aba Dados inclui registro passivo de uma coleta manual (30 s) e copia de diagnostico com nomes de campos, destino, referencias a boxes conhecidas e aumento observado do contador. Ignora comandos cumulativos antigos e nao grava tokens, chat ou valores de campos desconhecidos. O registro e necessario para validar o adaptador de execucao antes de automatizar farm por dados. A coleta visual continua sendo o unico modo automatico.

Validacao: 108 testes passaram, alem do replay das 22 mensagens. A observacao do EventSource nao exige mais que a pagina ja esteja em /play no instante da requisicao. A recepcao ao vivo, o comando manual e a execucao futura por dados ainda precisam de validacao no jogo.

Beta 0.4.1: corrige a aba Dados vazia: seus campos e botoes agora sao montados ao iniciar, mesmo sem conexao. Teste de regressao reproduziu a falha antes da correcao; 109 testes passaram. Leitura e coleta reais ainda precisam de validacao no jogo.

Beta 0.4.2: acrescenta diagnostico da primeira interrupcao do leitor (sequencia, campo, operacao e estrutura limitada sem textos privados). O registro manual preserva comandos observados quando a leitura falha. Nao acrescenta suporte a operacoes desconhecidas: copie o diagnostico antes de recarregar. 111 testes passaram; inclui registro sem alterar o estado recebido e preservacao da falha original.

Beta 0.4.3: suporta atualizacoes indexadas de listas no formato [a, tamanho final, pares de indice/patch], identificado pelo diagnostico enviado. Aplica patches de objeto nos itens, preserva a ordem, permite substituicao, crescimento completo e truncamento e rejeita indices invalidos ou listas incompletas. A projecao de campos tambem vale para cada item atualizado. 115 testes passaram, incluindo reproducao sintetica da atualizacao do indice 35 em 40 boxes; validacao ao vivo ainda necessaria. Registro manual e coleta automatica por dados continuam em validacao.
