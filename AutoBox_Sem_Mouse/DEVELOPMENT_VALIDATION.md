# AutoBoxV — desenvolvimento sem publicação

Base: design/autoboxv-dashboard, commit 795146ec76c711fe07e088322a08053ec5044927, PR #1.

## Diagnóstico inicial
A base já tinha seis abas, cartões e botões rápidos ligados aos métodos. Faltavam barras de HP/escudo e janela móvel; a coleta podia agendar reinícios repetidos enquanto encerrava. O NPC já mantinha o alvo, com limites de 15 segundos sem progresso e duração máxima da luta, sem um simples limite absoluto normal de abandono. Skylab/camuflagem eram recursos pendentes de integração; seu estado foi preservado.

## Resultado
- Painel compacto AutoBoxV: saldos grandes, rendimento compacto, conta/estatísticas secundárias, duas barras independentes, controles separados e 20 eventos de histórico (3 linhas visíveis).
- Leitura ausente/antiga e escudo com máximo inválido aparecem como indisponíveis.
- Última hora: janela móvel de 3600 segundos cronológicos; envelhece durante pausas. Considera idade do evento no servidor quando disponível, usando relógio monotônico local.
- Média: ganhos de boxes e NPCs divididos por tempo efetivo de farm, após 30 segundos; sem descontar compras ou contar eventos duplicados.
- F8/F9/F10 controlam somente coleta. Botão Parar tudo continua disponível. Reinício durante encerramento não fica agendado.
- Finalização opcional, desativada por padrão: HP 20%, distância desejada 450, limite absoluto 3000, duração 60 segundos.
- Configuração validada: HP 5–50%; distância desejada 150–600; limite absoluto 1000–8000; duração 10–180 segundos.
- Detecta NPC ferido movendo-se para longe, filtra velocidade e usa previsão curta limitada a 150 unidades por eixo. Reutiliza approach/onFollow a cada 0,2 s, sem sobrepor órbita.
- Vida, morte, mapa, revisão do alvo, bordas, falta de progresso e confirmação de comandos permanecem obrigatórios. A rota bloqueia aproximação perigosa através de outro NPC. Combate ancorado no portal tem prioridade. Sem maxHp válido, a exceção não é ativada.

## Validação
Testes locais executados em Windows, Python 3.13 e Tkinter. Cobertura:
- Inicialização, seis abas, widgets reais de HP/escudo, valores zero/ausentes e heartbeat Tk durante worker em segundo plano.
- Controles, desconexão, retomada/contador de NPCs, exclusão mútua, cliques repetidos, atalhos de coleta e histórico limitado.
- Janela móvel durante pausa, média por tempo ativo, eventos breves e duplicação.
- NPC parado, ferido em fuga, mudança de direção, derrota, desaparecimento, falta de progresso, vida baixa, morte da nave, mudança de mapa, opção desativada, cancelamento e limites absolutos.
- Ponte JavaScript simulada: destinos atualizados, mesmo alvo, vida/mapa/alvo/bordas e outros NPCs.
- Regressão dos testes anteriores de coleta, combate, loja, Galaxy Gate e atualizadores.

Comandos:
    python -m unittest discover -s AutoBox_Sem_Mouse/tests -q
    node AutoBox_Sem_Mouse/tests/test_pursuit_bridge.mjs
    python AutoBox_Sem_Mouse/distribution/build_user.py

O workflow autoboxv-validation roda em windows-latest, com permissão somente de leitura; executa testes, gera o EXE e realiza seu autoteste. Não publica release ou manifesto. Consulte o resultado final no PR.

## Limitações
Não houve batalha real no Shadow Galaxy neste trabalho. Alcance efetivo, parâmetros de perseguição, latência, reação do servidor e NPCs agrupados exigem validação na conta. O layout foi verificado por testes de widgets; aparência em outras escalas de tela ainda requer conferência visual.

A numeração, o ZIP de produção, os manifestos e o mecanismo de atualização foram preservados. Nenhuma tag, release ou merge é publicado por este trabalho. Supabase não foi implementado.


## Skylab — integração em desenvolvimento

Baseado nos arquivos skylab.js, skylab-catalog.js e tech-factory.js fornecidos pelo usuário. Usa somente o botão nativo de construção normal, com verificação dos custos, reserva de créditos, minérios, nível básico, energia e construção ativa. Não chama ações de conclusão instantânea, robôs ou transporte. Módulo básico pode subir mesmo com déficit de energia para desbloquear a próxima melhoria solar.

Worker independente: um upgrade por confirmação, comparação de módulo/nível/revisão, interrupção em resultado desconhecido após 30 segundos. Parar tudo, diagnóstico, atualização e fechamento interrompem novas ações. Janela Tkinter atualizada por fila. Sem publicação; validação real requer abrir Skylab no jogo.

Testes adicionados: 11 Python/Tkinter e ponte JavaScript simulada para limites, falta de créditos/minérios, energia, pré-requisito básico, construção ativa, leitura perdida, conta alterada, resultado não confirmado, cliques repetidos, parada e contagem regressiva.


## Camuflagem na coleta

Integração pelos dados me.cloaked, loadout.extras e specials do cliente exportado. Aciona DarkOrbitQuickbar.onAction somente para CL04K equipada com cargas e sem impedimento informado pelo próprio cliente. Nenhuma compra, mudança de equipamento ou uso no NPC Killer.

7 testes Python adicionais e ponte JavaScript simulada: confirmação, perda e reativação, resultado desconhecido, recarga, CPU ausente, estoque vazio, morte, salto, combate, troca de sessão, parada e modo desativado. Total local: 183 testes Python/Tkinter. Validação em partida real pendente; sem publicação.
