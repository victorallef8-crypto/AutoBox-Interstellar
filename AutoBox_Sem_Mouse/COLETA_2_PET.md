# Coleta 2 — somente PET (0.16.4)

Na aba Coleta, escolha Coleta 2 e inicie no mapa desejado. Requer PET nível 2 ou superior, Auto-looter nível 1 equipado na configuração ativa, vida e combustível. Ativa o PET e seleciona o módulo com confirmação antes de mover a nave. Não compra combustível, equipamentos ou reparos.

A nave recebe apenas destinos, sem clicar em boxes ou enviar coleta. Segue o percurso pelo mapa, atravessa a posição das boxes próximas e mantém o destino adiante, com até 1200 unidades de continuação. Só libera a box após cruzar sua posição, sem parada, espera ou volta para coletar. A antecipação dos próximos destinos considera velocidade, idade da leitura e duração dos comandos; o ciclo verifica movimento a cada 0,1 segundo. Boxes muito perto da borda, sem espaço para continuar depois delas, são ignoradas em favor do percurso. Somente o PET recebe o modo de coleta. Sem boxes próximas, mantém o percurso pelo mapa. Não atribui desaparecimentos de boxes ao PET sem prova. Validado em simulação de voo com atraso; conferir em partida real.

F9/F10 e troca do modo interrompem a nave. PET permanece ativo no jogo; recolha-o manualmente para interromper seu consumo de combustível. Perda de conexão, morte, vida baixa, falta de combustível, mudança de conta/configuração ou mapa interrompem a Coleta 2. Não retoma automaticamente nem viaja para outro mapa neste modo. Camuflagem opcional aproveita o controle existente.

Validação real com o PET nível 2 e módulo nível 1 ainda necessária. Publicado no canal de usuários por solicitação em 29/10/2026.


Correção 0.16.4: o cliente calcula o destino pela posição atual da nave, evitando rejeitar um comando após curva por diferença com a leitura anterior. Seleciona boxes próximas independentemente da direção do percurso e só marca como passadas as efetivamente cruzadas. Boxes desaparecidas ou bloqueadas provocam continuação imediata da rota, com adiamento limitado. Copiar diagnóstico inclui pet_collection com contadores, última ação, resultado e falha preservada após encerrar.
