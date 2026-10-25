# AutoBox Interstellar Verse

Aplicativo experimental para Windows 11 que reconhece boxes do jogo por captura
de tela e opera o mouse localmente. **Nao e um produto oficial do jogo.**

## Recursos

- Identificacao visual de boxes na area calibrada pelo jogador.
- Atalhos F8 (iniciar), F9 (pausar) e F10 (parar).
- Deteccao visual de recompensas para adiantar a proxima coleta.
- Patrulha somente numa area central do minimapa selecionada pelo usuario.
- Reacao ao aviso de radiacao, tentando voltar ao ponto seguro do minimapa.
- Renascimento pago opcional com limite por hora. Desativado por padrao;
  confira o custo e o botao no jogo antes de ativar.
- **Atualizacoes com um clique**, usando `update_manifest.json`, ZIP e SHA-256.

## Instalar

1. Baixe `AutoBox_Interstellar.zip` neste repositorio.
2. Extraia a pasta `AutoBox_Interstellar`.
3. Instale Python 3.11+ e execute `INSTALAR_E_ABRIR.bat`.
4. Use os botoes de calibracao do proprio programa.

Ao abrir, o AutoBox verifica se existe versao nova. O usuario tambem pode
clicar em **Verificar atualizacoes (GitHub)**. O atualizador so baixa arquivos
do ramo `main` deste repositorio, valida a integridade pelo hash SHA-256 e
substitui apenas arquivos conhecidos, preservando `.venv` e as configuracoes.

O jogo pode proibir automacao e sancionar a conta. A deteccao visual, as
rotas seguras e o renascimento automatico nao sao garantidos; teste com
supervisao antes de deixar o programa funcionando sozinho.
