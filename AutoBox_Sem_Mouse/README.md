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
