ABAS E MAPA — BETA 0.7.0
- Coleta: mapa de destino independente, coleta por dados e preferências existentes.
- Kill NPC: lista ao vivo dos NPCs, viagem ao mapa e registro manual do combate.
- O ataque automático a NPCs AINDA NÃO ESTÁ DISPONÍVEL. Primeiro precisamos validar o registro da luta.
- F8 continua sendo iniciar COLETA. Abrir a aba Kill NPC não inicia combate.

VIAGEM ENTRE MAPAS
Em Coleta ou Kill NPC, selecione/digite um código de mapa normal (ex.: 4-3) e salve. Vazio mantém o mapa atual.
A lista mostra mapas conhecidos no estado atual; para um destino mais distante, digite seu código.
Ir ao mapa pausa a coleta e só faz a viagem. Na aba Kill NPC, ao chegar faça o registro manual.
Ao iniciar coleta com F8, o bot viaja primeiro ao destino da aba Coleta e então começa a coletar.
Usa a rota calculada pelo cliente e somente portais normais; não usa CPU paga ou portais de galáxia.
Recusa viagem com ataque ativo, vida baixa, acesso negado ou dados ausentes. Para se não houver progresso.
F9/F10 cancelam próximos comandos, mas um percurso ou salto já aceito pelo jogo pode terminar.
A viagem isolada para em perda de leitura; a coleta com destino mantém a opção de reconexão existente.
Confira a primeira viagem na partida: os testes locais não substituem essa validação.

REGISTRAR UMA LUTA
1. Abra o jogo pelo bot, entre no mapa e abra Kill NPC.
2. Clique Registrar luta manual (90 segundos). O bot pausa a coleta.
3. Selecione um NPC fraco e ataque usando munição básica.
4. Pare o ataque uma vez e depois ataque novamente. Se puder, conclua a morte do NPC.
5. Clique Encerrar registro e Copiar diagnóstico da luta; cole no chat.
O painel informa se observou seleção, início, parada e dano. Não precisa abrir F12.
O registro não envia ataques. Captura somente campos necessários, sem token, chat ou identidade de outros jogadores.
Depois do registro, F8 volta à coleta. Combate automático, fuga e recuperação de combate ficam para a etapa seguinte.

# AutoBox Sem Mouse

AutoBox Interstellar — Beta 0.7.0

ATUALIZAR
Esta versão remove os modos antigos de imagem e clique e as dependências OpenCV, NumPy e Pillow.
No Painel, use Verificar atualizações deste bot. As preferências e a sessão do navegador ficam na pasta de dados do aplicativo.

COMEÇAR
1. No Painel, clique Iniciar jogo. O navegador dedicado abre https://interstellar-verse.com/.
2. Faça login e entre no mapa. Em Coleta, aguarde Leitura ao vivo.
3. F8 inicia; F9 pausa; F10 para e cancela reconexões. Um percurso já aceito pelo jogo pode terminar.
4. A coleta por dados dispensa marcação de áreas. Mantém a box mais próxima como alvo até terminar.
5. Mantenha o navegador aberto. O funcionamento minimizado ainda precisa de validação.

PAINEL
Saldos: Uridium, créditos, XP, honra, nível e chaves verdes.
Uridium da sessão: somente novos eventos de recompensa de boxes durante a coleta, excluindo PET.
Uridium/h: recompensas contadas divididas pelo tempo ativo; começa após 60 segundos. Pausas e espera de reconexão/renascimento não entram no tempo ativo.
Saldos indisponíveis aparecem como traço. O contador de mortes e os ganhos são zerados ao fechar o aplicativo.

PREFERÊNCIAS
- Caixas verdes: desativadas inicialmente. Usa somente chaves existentes, sem comprar. A confirmação combina desaparecimento do alvo, proximidade e redução de chaves.
- Reconectar: ativado inicialmente. Aguarda o fluxo voltar, usa os botões normais de entrada/tentativa do cliente e recarrega a página do mapa se necessário. Tentativas espaçadas, até 60 segundos entre elas. Só retoma após leitura atual; F9/F10 cancelam. Se exigir autenticação, faça login manualmente. Não reabre um navegador que você fechou.
- Renascimento: desativado inicialmente. Escolha Base, Portal ou Local; custo máximo começa em zero Uridium. Confere opção disponível, saldo e preço do botão antes de confirmar.
- Limite de mortes: padrão 3. Ao atingir o limite, encerra antes de outro renascimento. Contagem durante a coleta automática, por identificação da morte.
- Renascimento local pode dar apenas 1% de vida. Com vida em 25% ou menos a coleta para e pede recuperação manual.
- Ajustes de coleta, reconexão e renascimento são aplicados ao iniciar com F8.

AVANÇADO
Navegador, diagnóstico por dados e exportação ficam separados do uso diário. A coleta por dados é o único modo. Foram removidos calibração, aprendizado de imagem, teste visual e clique por coordenadas de captura. As preferências antigas de imagem são descartadas ao salvar; as demais configurações são preservadas.

AINDA PENDENTE
Fugir de jogadores; recuperação automática de vida; combate automático/NPCs; PET e seus modos.
O coletor aguarda boxes no mapa de destino. Com destino vazio, permanece no mapa atual. Não compra chaves.

VALIDAÇÃO
101 testes Python de leitura, planejamento, interface, atualização, cancelamento, estatísticas, chaves, renascimento e reconexão.
Teste local da ponte com callbacks do cliente fornecido, incluindo zoom 33%, 100% e 200%, e caixas verdes.
Teste do botão de renascimento com preço atual, morte diferente e painel oculto.
Replay privado de 22 mensagens do jogo, sem publicar dados da sessão.
Esses testes simulados não substituem validação das novas funções em uma partida real.

Instalação nova: Python 3.11+; execute INSTALAR_E_ABRIR.bat. A instalação usa uma .venv própria.
