# AutoBoxV e DarkBot — comparação de recursos

Data: 31/10/2026. Trabalho local na branch `fix/npc-portal-circle-map-bounds`.

Esta entrega adapta princípios de funcionamento ao Interstellar Verse. Não é um clone completo do DarkBot, não executa plugins Java do DarkBot e não garante ausência de falhas. Código original do AutoBox em Python/JavaScript; não foram transplantados arquivos Java.

## Referências consultadas

- [DarkBot: configuração geral](https://github.com/darkbot-reloaded/DarkBot/blob/master/src/main/java/com/github/manolo8/darkbot/config/Config.java).
- [DarkBot: interface principal](https://github.com/darkbot-reloaded/DarkBot/blob/master/src/main/java/com/github/manolo8/darkbot/gui/MainGui.java).
- [DarkBotAPI: NPC Killer atual](https://github.com/darkbot-reloaded/DarkBotAPI/blob/master/shared/src/main/java/eu/darkbot/shared/modules/LootModule.java).
- [DarkBotAPI: coletor atual](https://github.com/darkbot-reloaded/DarkBotAPI/blob/master/shared/src/main/java/eu/darkbot/shared/modules/CollectorModule.java).
- [DarkBotAPI: recuperação e fuga](https://github.com/darkbot-reloaded/DarkBotAPI/blob/master/shared/src/main/java/eu/darkbot/shared/utils/SafetyFinder.java).

Os módulos no repositório principal do DarkBot estão marcados como legados; por isso também foram examinados os módulos compartilhados atuais do DarkBotAPI. A comparação cobre os módulos básicos consultados; não representa uma auditoria de todos os plugins de terceiros.

## Alterado nesta sequência de trabalho

| Recurso | Comportamento preparado no AutoBox |
|---|---|
| Movimento circular de combate | Correção gradual do raio conforme a distância, com avanço angular ligado à velocidade da nave. |
| Escolha do sentido | Compara rotas nos dois sentidos e posições futuras; preserva o sentido quando não há vantagem suficiente em trocar. |
| Outros NPCs | Penaliza trajetórias próximas de outros NPCs. Não equivale a uma garantia de não receber dano. |
| Bordas | Margem de 80 unidades e busca de arcos interiores quando as duas direções iniciais são inválidas. |
| Portal | Pontos de um círculo de até 80 unidades, mantidos até a aproximação; reduz o raio quando o portal está perto da borda. É uma adaptação própria do Interstellar. |
| Exploração sem NPC | Percorre pontos interiores do mapa quando não há alvo marcado. Pode ser desativada; interrompe exploração durante combate. |
| Próximo alvo | Prioridade configurada, depois menor proporção de vida, depois distância. Não troca o alvo no meio da luta por essa ordenação. |
| Reconexão no NPC Killer | Usa a preferência já existente da coleta, com tentativas espaçadas, limite de 10 minutos e reavaliação de nave/alvos ao restaurar a leitura. |
| Renascimento no NPC Killer | Usa Base/Portal/Local, custo máximo e contador de mortes configurados. Aguarda confirmação de um pedido enviado; não repete confirmação paga sem observar resultado. |
| Reparo | Percentual de vida para retomar configurável entre 80 e 100%; padrão da interface: 95%. |
| Validação automatizada | Novas simulações de círculo, bordas e exploração; novos testes de recuperação. Workflow de PR deixa de restringir a validação a uma única branch antiga. |

## Recursos já existentes, preservados

A existência de código não significa teste real de todos esses recursos nesta sessão.

| Área | O que já havia no AutoBox |
|---|---|
| Modos | Coleta pela nave, NPC Killer e matar/coletar entre lutas. |
| Coleta | Seleção por ID/coordenadas, confirmação de recompensas, descarte temporário de alvos sem progresso e caixas verdes com chaves existentes. |
| PET | Modo de coleta apenas pelo PET, com checagem de equipamento, nível e combustível; não implementa todos os modos PET do DarkBot. |
| Camuflagem | Uso de cargas equipadas na coleta, com confirmação. |
| Combate | Tipos de NPC selecionáveis, perfis de prioridade/raio/laser/círculo, confirmação de seleção e ataque, perseguição opcional para finalizar. |
| Compras | Reposição de laser/míssil com limites e reservas de saldo, dependendo da integração da loja. |
| Navegação | Viagem por portais e retorno ao mapa configurado pela rota do cliente. |
| Reparo | Retorno ao portal, interrupção de tiros e acionamento do robô de reparo equipado. |
| Painel | Minimap ao vivo, trilha, alvo, recursos, portais, HP/escudo, iniciar/pausar/parar e modo compacto. |
| Janela do jogo | Controles para mostrar/minimizar a janela dedicada; comportamento real depende do Windows/cliente. |
| Estatísticas | Uridium, créditos, rendimento por hora e estatísticas de NPCs. |
| Serviços | Construção de Skylab e giros de energia de Galaxy Gate com limites. Girar energia não significa completar o gate em combate. |
| Atualização | Canal de atualização e empacotamento Windows existentes. Nenhum novo executável foi publicado nesta sessão. |

## Ainda não equivalente ao DarkBot

| Recurso | Limitação concreta |
|---|---|
| Interface | A estrutura visual foi aproximada: barra superior, mapa central, estatísticas sobrepostas e configurações dentro da mesma janela. Não é uma reprodução pixel a pixel da interface Swing. |
| Plugins | Não há compatibilidade com a API Java nem com o catálogo de plugins DarkBot. |
| Obstáculos, minas e áreas | A correção de bordas não é um planejador completo para obstáculos/minas nem um editor de zonas preferidas/proibidas. Precisa de dados confirmados do Interstellar. |
| Fuga de jogadores | Não há identificação validada de jogadores hostis, listas de confiança ou fuga automática equivalente ao SafetyFinder. |
| Grupos | Convites, lista de confiança e gerenciamento automático de grupo não foram implementados. |
| Habilidades e configurações da nave | Trocas de configuração/formação e habilidades específicas não foram integradas. |
| SAB/RSB inteligente | Selecionar um laser é suportado; alternar automaticamente conforme escudo/recarga não foi adicionado. |
| PET completo | Não há combate PET, kamikaze ou todos os demais módulos do DarkBot. |
| Galaxy Gates completos | Não há módulo que complete todas as ondas de cada gate. |
| Recursos de conta | Leilão, hangar, inventário, reparo de drones e serviços específicos de DarkOrbit não foram transplantados. |

## Verificação

- 260 testes Python aprovados, incluindo interface gráfica, após as mudanças visuais.
- Cinco scripts Node aprovados: movimento/portal, perseguição, PET, camuflagem e Skylab.
- Compilação Python e verificação de whitespace aprovadas.
- Interface executada em display virtual: abrir/fechar configurações, persistir filtros, atualizar alvo/HP e verificar botões no tamanho mínimo de janela.
- Um teste preexistente de certificados excluído: exige que um contexto TLS novo inicie com zero certificados; o runtime desta sessão inicia com um certificado. A verificação TLS do produto não foi alterada.
- Capturas do aplicativo real foram inspecionadas visualmente, usando dados simulados explícitos. Não houve validação no jogo nem geração/execução de novo binário Windows.

## Roteiro de validação no jogo

1. Conferir os novos controles de exploração e percentual de reparo na aba NPC.
2. Testar um único tipo de NPC, primeiro no centro e depois perto de cada borda. Verificar se mantém alvo e ataques.
3. Ativar combate junto ao portal e verificar se o círculo permanece realmente na zona segura; o raio de segurança é uma regra do servidor ainda não medida aqui.
4. Sem alvos, verificar exploração com pontos interiores; ao aparecer um alvo marcado, verificar retomada do combate.
5. Com retorno ao portal habilitado, conferir reparo até o percentual escolhido e retomada.
6. Testar uma queda curta de conexão e retomada. Login solicitado deve interromper o processo.
7. Testar renascimento apenas com opção/custo previamente revisados; conferir limite de mortes e ausência de pedidos duplicados.

As alterações estão preparadas localmente. Publicação da versão 0.17.0 autorizada pelo usuário em 31/10/2026. A disponibilidade no atualizador depende do workflow Windows publicar o executável e o manifesto com sucesso.

## Interface adaptada

O aplicativo utiliza uma única janela, com as abas Mapa ao vivo e Configurações e estatísticas. A barra superior reúne configurar, estatísticas, iniciar, pausar, parar e mostrar/ocultar o jogo. Uma segunda linha seleciona o módulo e os filtros de NPCs, boxes, portais, rastro e dados. As estatísticas aparecem sobre o mapa; as barras de HP/escudo, a informação do alvo e as coordenadas ficam no rodapé.

Preferências de módulo, filtros, estatísticas e janela sempre visível são gravadas na configuração. Alternar entre as abas não encerra os trabalhadores nem altera o farm. Ao iniciar, o aplicativo sempre abre o mapa ao vivo, inclusive ao atualizar uma configuração antiga.

Capturas com dados simulados para revisão visual:

- [Janela principal](autobox-interface-preview.png).
- [Configurações](autobox-settings-preview.png).

O utilitário `AutoBox_Sem_Mouse/tests/preview_cockpit.py` reproduz as capturas a partir dos widgets reais, sem conectar ao jogo.

## Nomes no minimapa

- Controles separados: **Mostrar nomes — NPCs** e **Mostrar nomes — Aliados**. O nome do NPC selecionado permanece destacado mesmo com os demais nomes desligados.
- Camada **Aliados** exibe/oculta os marcadores verdes; a opção de nomes é independente. Preferências persistem sem alterar o farm.
- Nomes são limitados a uma linha e 36 caracteres na renderização. Entidades saem da tela quando a leitura fica desatualizada.
- A projeção opcional de `players` aceita apenas nome público, posição e relação explícita (`isAlly` ou `relation`), com precedência para a identificação de hostilidade. Não classifica jogadores por proximidade ou nome; não retém login, tokens ou chat.
- **Limitação:** o formato de relações de jogadores do cliente atual ainda não foi confirmado. A página `/play/` respondeu 401 sem login nesta sessão. Esse esquema de aliados é um contrato opcional implementado e coberto por simulações, não uma integração comprovada com o servidor atual. Se os campos não estiverem disponíveis, o painel informa “Aliados: identificação indisponível”. Para concluir a validação real, usar a exportação de integração do cliente pela janela dedicada já autenticada do usuário.
- As novas capturas mostram nomes e aliados com dados simulados identificados no rodapé.
