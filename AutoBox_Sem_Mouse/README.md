# AutoBox Sem Mouse

AutoBox Interstellar — Beta 0.6.0

ATUALIZAR
No Painel, use Verificar atualizações deste bot. As preferências e a sessão do navegador ficam na pasta de dados do aplicativo.

COMEÇAR
1. No Painel, clique Iniciar jogo. O navegador dedicado abre https://interstellar-verse.com/.
2. Faça login e entre no mapa. Em Dados e coleta, aguarde Leitura ao vivo.
3. Use Dados do jogo como modo. F8 inicia; F9 pausa; F10 para e cancela reconexões. Um percurso já aceito pelo jogo pode terminar.
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
Navegador, diagnóstico, exportação e calibração do modo Imagem (anterior) ficam separados do uso diário. As novas preferências de chaves, renascimento e reconexão são do modo Dados do jogo.

AINDA PENDENTE
Escolher mapa e viajar automaticamente pelos portais; fugir de jogadores; recuperação automática de vida; combate/NPCs; PET e seus modos.
O coletor atual aguarda boxes no mapa em que a nave está. Não compra chaves nem troca de mapa sozinho.

VALIDAÇÃO
140 testes Python de leitura, planejamento, interface, atualização, cancelamento, estatísticas, chaves, renascimento e reconexão.
Teste local da ponte com callbacks do cliente fornecido, incluindo zoom 33%, 100% e 200%, e caixas verdes.
Teste do botão de renascimento com preço atual, morte diferente e painel oculto.
Replay privado de 22 mensagens do jogo, sem publicar dados da sessão.
Esses testes simulados não substituem validação das novas funções em uma partida real.

Instalação nova: Python 3.11+; execute INSTALAR_E_ABRIR.bat. A instalação usa uma .venv própria.
