# AutoBox - Interstellar e Krypton

Aplicativo experimental para Windows 11 que reconhece boxes do jogo por captura
de tela e opera o mouse localmente. **Nao e um produto oficial do jogo.**

## Beta 3.5.3

- Krypton exige marcar a area real da nave, preservada no perfil.
- Usa essa referencia para distancia, aproximacao e chegada.
- Bloqueia a nave tambem durante revalidacao final do clique e ronda.
- Interstellar preserva a calibracao anterior.

## Beta 3.5.2

- Krypton retenta o mesmo alvo quando a aproximacao para, com limite de duas retentativas.
- Evita novos alvos sobre o centro da nave e ordens de minimapa enquanto boxes estao temporariamente filtrados.
- Atualiza o historico apos a coleta para nao reaproveitar coordenadas antigas da camera.
- Preserva o metodo de clique configurado e o comportamento do Interstellar.

## Beta 3.5.1

- Metodo alternativo Windows (SendInput) para o cliente Krypton.
- Botao para testar um clique com o cursor posicionado manualmente.
- Verifica o retorno do Windows e libera o botao ao interromper a espera.
- Interstellar mantem o metodo anterior; aceitacao pelo Krypton ainda precisa de teste.

## Beta 3.5

- Duas abas: Interstellar e Krypton, com calibracoes e ajustes separados.
- Interstellar preserva configuracao e modelo antigos.
- Krypton usa seu proprio modelo de box e clique esquerdo com duracao ajustavel.
- Captura do titulo da janela e rolagem das abas.
- Trocar de aba interrompe a coleta; apenas uma aba opera o mouse por vez.
- Coleta real no Krypton ainda depende de calibracao e teste no jogo.

## Beta 3.4.2

- Escolhe o box disponivel mais perto do centro atual da area espacial.
- Remove a referencia ao clique anterior e usa confianca apenas no desempate.
- Preserva a espera adaptativa e a saida rapida apos desaparecimento.

## Beta 3.4.1

- Reduz a espera quando o alvo desaparece perto da nave em verificacoes consecutivas.
- Mantem tolerancia para notificacao e cancela a saida se o alvo reaparecer.
- Nao considera desaparecimento como recompensa confirmada.

## Beta 3.4

- Mantem o alvo durante a aproximacao, estendendo a espera quando ha progresso.
- Nao envia outro clique de coleta enquanto aguarda esse alvo.
- Limita o tempo total e abandona a espera sem progresso.
- Estima a posicao da nave pelo centro da area espacial calibrada.

## Beta 3.3.2

- Corrige a espera por estabilidade que impedia cliques durante o voo.
- Clica na posicao atualizada sem mover o cursor e aguardar antes.
- Mantem o descarte de alvos desaparecidos ou com deslocamento excessivo.

## Beta 3.3.1

- Revalida a posicao do box em capturas recentes antes do clique.
- Descarta alvos que desapareceram ou continuam se deslocando.
- Procura boxes durante a espera da ronda.
- Validacao em jogo ainda pendente.

## Beta 3.3

- Cada tentativa distingue recompensa confirmada, prazo esgotado e interrupcao.
- Depois de tres tentativas consecutivas sem confirmacao, faz uma ronda na zona segura.
- Sem zona segura calibrada, pausa e explica o motivo.
- Uma recompensa confirmada zera a sequencia; pausas e troca de janela nao somam falhas.
- O historico de alvos recentes e mantido durante a ronda.

## Recursos

- Identificacao visual de boxes na area calibrada pelo jogador.
- Atalhos F8 (iniciar), F9 (pausar) e F10 (parar).
- Deteccao de mensagens **novas** na area `You received` calibrada pelo
  jogador, para adiantar a proxima coleta sem aguardar o tempo maximo.
- Patrulha somente numa area central do minimapa selecionada pelo usuario.
- Reacao ao aviso de radiacao, tentando voltar ao ponto seguro do minimapa.
- Renascimento automatico opcional com tres destinos: Base (gratis), Portal
  (250 U) e Mesmo lugar (500 U). Desativado por padrao, limitado por hora,
  com confirmacao para ativar opcoes pagas.
- **Atualizacoes com um clique**, usando `update_manifest.json`, ZIP e SHA-256.

## Instalar

1. Baixe `AutoBox_Interstellar.zip` neste repositorio.
2. Extraia a pasta `AutoBox_Interstellar`.
3. Instale Python 3.11+ e execute `INSTALAR_E_ABRIR.bat`.
4. Use os botoes de calibracao do proprio programa. Na Beta 3.3, marque
   tambem a area onde aparecem as notificacoes `You received`.

Ao abrir, o AutoBox verifica se existe versao nova. O usuario tambem pode
clicar em **Verificar atualizacoes (GitHub)**. O atualizador so baixa arquivos
do ramo `main` deste repositorio, valida a integridade pelo hash SHA-256 e
substitui apenas arquivos conhecidos, preservando `.venv` e as configuracoes.

O jogo pode proibir automacao e sancionar a conta. A deteccao visual, as
rotas seguras e o renascimento automatico nao sao garantidos; teste com
supervisao antes de deixar o programa funcionando sozinho.
