# AutoBoxV 0.18.0

- NPC Killer reorganizado numa tabela por mapa: Matar, NPC, Prioridade, Distância, Munição, Míssil e Extras.
- Edição por duplo clique e botão Aplicar ao NPC, incluindo aplicação durante a mesma luta.
- Menu para marcar/desmarcar todos e aplicar o editor aos NPCs marcados.
- Catálogo de tipos observados por mapa, sem limite de 30 tipos na tabela.
- Extras por NPC: circular, lutar no portal e finalizar de perto, além do míssil selecionado.
- Recuperação/compras e diagnóstico separados da tabela principal.
- Corrigidas a sobreposição confusa dos perfis, a configuração que exigia reiniciar e as alterações ocultas do raio pela aproximação/círculo.
- Configurações de outro mapa não alteram o farm ativo. Troca de munição aguarda confirmação; desmarcar o alvo atual encerra seus tiros.

Validação local: 274 testes Python aprovados com interface gráfica, exceto o mesmo teste de certificados específico do runtime; cinco simulações Node aprovadas. O Windows executa todos os testes e verifica o executável antes de publicar.

A lista é construída com os tipos informados pelo cliente e já observados naquele mapa. O comportamento no servidor, as relações de aliados e os recursos específicos de DarkOrbit continuam com as limitações descritas no comparativo.
