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

## NPC Killer — prioridade 1 e mortes rápidas (2026-10-27)

Seleciona primeiro todo NPC clicável, sem exigir aproximação a 180 unidades.
Somente se a seleção retornar not_visible aproxima pela distância normal de combate,
sem close_approach até o centro do NPC. Tentativas de aproximação de aquisição são
espaçadas em 0,5 s; aproximação em combate normal em 0,35 s. Finalização e portal
mantêm suas regras anteriores. A confirmação do alvo ainda antecede o ataque.

Mortes entre duas leituras não precisam apresentar uma amostra intermediária de HP:
após um ataque enviado, desaparecimento mais aumento de XP ou novo evento próprio
de kill confirma o fim. Eventos anteriores ao ataque, caixas e eventos marcados como
PET não servem como novo evento de kill. A janela de recompensa passa de cerca de
2 para 5 segundos; durante a espera não envia novo ataque. Desaparecimento isolado
continua sem confirmação. Essa correlação usa os dados disponíveis; a associação
entre recompensa e alvo em partidas com PET/grupo exige validação real.

Validação neste ambiente Linux: 159 testes Python de lógica/integração passaram,
incluindo 38 do NPC Killer (7 novos métodos de regressão). As três pontes JavaScript
simuladas passaram. A tentativa da suíte completa encontrou três erros de setup
Tkinter por ausência de display e uma falha no teste do atualizador que espera um
SSLContext sem certificados iniciais, mas este ambiente já adiciona um certificado.
Esses quatro pontos não foram ignorados como aprovação da suíte completa. O workflow
Windows existente continua responsável por interface e empacotamento, sem release.

Pendente no Windows/jogo: Lordakia e Saimon com x4 em sequência, mortes em um/dois
tiros, recompensa atrasada, seleção de NPC distante visível, fora da tela e encoberto,
movimento residual após seleção, PET/grupo, parada manual e prioridade de portal.
Confirmar que a nave não precisa encostar para mirar e que o farm encadeia as kills.
Não mesclar nem publicar; versão, manifestos e ZIPs de produção preservados.

## Cockpit compacto e decisões de farm (2026-10-27)

Implementado com código próprio, mantendo AutoBoxV. A abertura usa uma janela
compacta de 760x560, com controles Iniciar/Pausar/Parar, seletor de modo, pin de
janela e acesso à interface completa. A escolha do modo de janela é persistida.
Minimapa usa coordenadas recebidas: nave, NPCs, alvo, recursos, portais, destino e
rastro limitado a 80 posições. Limpa o mapa quando a leitura fica indisponível e
reinicia o rastro após mudança de mapa/renascimento. Mantém proporção do mapa e
limita quantidade de marcadores para não bloquear Tkinter. Não é vídeo do jogo.
A prévia em docs/cockpit-preview.png usa exclusivamente dados simulados e traz
esse aviso na própria imagem; não é evidência de farm real.

Perfis por NPC: prioridade (-100 a 100, menor primeiro), laser, distância e órbita.
Sem perfil, usa valores gerais. Os perfis são validados e copiados ao iniciar o
farm; alterações valem no próximo início. Reposição é avaliada após escolher o
perfil para não comprar automaticamente a munição geral para um alvo com perfil.

Combate: seleção sem confirmação pode ser tentada novamente até duas vezes,
somente com ataque explicitamente inativo. Ctrl/ataque sem confirmação não ganha
repetição cega. Movimentos quase iguais (<25 unidades em menos de 600 ms) para a
mesma sessão são deduplicados no cliente; mudanças maiores continuam atualizando
a rota. Proteções e regras de finalização/portal permanecem.

Coleta: um recurso sem progresso é adiado por 30 s e o coletor procura outro. O
adiamento é por ID/revisão; desaparecimento continua sem contar como coleta sem
prova. O modo Matar + coletar usa o mesmo worker e intercala uma coleta de até
10 s entre lutas, ou na ausência de NPC. Só inicia coleta entre lutas após parar
os tiros com confirmação; limite de HP do combate também interrompe essa coleta.
Não coleta durante a órbita: essa otimização ainda está no roteiro.

Janela do jogo: operação Browser.setWindowBounds via CDP, executada no mesmo
thread do navegador, com restauração normal. Flags do Chromium tentam reduzir
throttling de segundo plano. Isso NÃO comprova funcionamento minimizado no Opera
GX/Windows real. Dados antigos continuam bloqueando ações e limpam o minimapa.
Não houve sessão do Interstellar disponível no navegador conectado nesta etapa.

Validação local: suíte completa de 208 testes executada com display Xvfb temporário;
207 passaram. Única falha é a premissa de SSLContext inicialmente sem certificados
no teste do atualizador (ambiente injeta um CA). Não removida nem tratada como
aprovação total. As três pontes JavaScript simuladas passaram. O workflow Windows
sem release deve validar a suíte e o empacotamento deste commit antes de liberação.
A validação Windows do commit anterior 0cf85b6 terminou com sucesso (run 12).

### Continuação obrigatória antes de publicação

1. Conferir CI Windows deste novo commit e resolver falhas, se existirem.
2. Testar em partida Lordakia/Saimon com x4, NPC visível distante/encoberto,
   perfis, seleção perdida, movimento residual, órbita, finalização e portal.
3. Comparar janela normal e minimizada: sequência/idade da leitura, movimento,
   mira, ataque, coleta, reconexão e recuperação; testar também VPS/RDP. Minimizar
   não é aprovado apenas porque a leitura continua recebendo eventos.
4. Obter exportação atual do cliente com minérios visíveis e dados de porão:
   nomes/tipos, entidades, ação nativa e confirmação de recompensa. Nenhuma coleta
   de minério foi habilitada com identificação inventada. Buscas pelos arquivos
   anteriores não localizaram a exportação nesta sessão.
5. Ainda não implementados: coleta durante combate, navegação completa com
   obstáculos/áreas proibidas, fuga baseada em jogadores, gestão de PET, histórico
   persistente por NPC e ajustes adaptativos. Exigem integrações/dados e validação.
6. Manter PR em rascunho, sem merge/release, sem alterar versão/ZIP/manifestos de
   produção. Acumular próximos ajustes para publicação conjunta autorizada.


### Revisão de coordenação e recuperação

A confirmação de camuflagem é compartilhada entre os intervalos de coleta; o modo
combinado aguarda a confirmação pendente antes de iniciar ataque. Assim, trocar de
intervalo não reinicia a proteção contra repetição de cargas. Resultado desconhecido
continua encerrando o farm. Regressões cobrem o intervalo e a espera antes do ataque.

Após falha de seleção ou ausência de progresso, o farm pode adiar aquele ID/revisão
por 30 s, somente depois de confirmar a parada dos tiros. Há limite de três desvios
consecutivos; falhas de ataque ambíguo ou recompensa não confirmada não recebem
reinício cego. O painel completo mostra contagem, média e último tempo por ciclo e
laser utilizado por tipo de NPC. Esses dados são da sessão, não aprendizado automático.

CI Windows do cockpit inicial be85030 passou (run 14), incluindo empacotamento.
A revisão final que inclui os guardas acima precisa do próprio resultado de CI.
