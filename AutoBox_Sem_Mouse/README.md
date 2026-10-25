# AutoBox Sem Mouse

Bot independente, exclusivo de coleta visual no Interstellar em uma sessao dedicada do Opera GX.

Baixe [AutoBox_Sem_Mouse.zip](AutoBox_Sem_Mouse.zip), extraia e execute INSTALAR_E_ABRIR.bat. Feche o bot antigo para evitar conflitos de atalhos.

Configure mapa, modelo de box e area da nave. Minimap e notificacoes sao opcionais. F8 inicia, F9 pausa e F10 para.

Esta beta possui configuracoes e atualizador proprios. A logica e a interface foram verificadas com navegador simulado; a coleta real ainda precisa de validacao. Nao ha garantia de ausencia de banimento.

Consulte LEIA-ME.txt para detalhes.

Beta 0.1.1: detector com mais escalas e recorte do objeto luminoso; teste visual de deteccao sem cliques; busca limitada a 24 s sem candidatos, alternancia de patrulha e retorno ao centro da zona marcada ao reconhecer radiacao. Retorno depende de calibracao correta e precisa de validacao no jogo.

Beta 0.1.2: converte coordenadas da captura para pixels CSS medidos no navegador antes de clicar, com validacao de pagina/zoom entre captura e clique. A previa informa os dois pontos. 56 testes passaram; a abertura de um Opera local para teste foi impedida pelo ambiente, e a coleta real ainda depende de validacao.

Referencia das unidades de coordenadas: [Playwright Mouse](https://playwright.dev/python/docs/api/class-mouse) e [CDP Input](https://chromedevtools.github.io/devtools-protocol/tot/Input/#method-dispatchMouseEvent).
