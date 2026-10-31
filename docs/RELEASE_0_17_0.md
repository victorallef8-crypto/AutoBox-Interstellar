# AutoBoxV 0.17.0

- Interface com mapa central, barra de controles, estatísticas sobrepostas e configurações em janela separada.
- Filtros do minimapa e opções independentes para os nomes dos NPCs e dos aliados.
- Movimento circular ajustável, escolha do sentido com mais espaço e recuperação de rotas junto às bordas.
- Círculo próximo do portal com destinos estáveis.
- Exploração sem NPC marcado, prioridade/vida/distância para escolher o próximo alvo.
- Reconexão e renascimento no NPC Killer com os limites configurados; percentual de vida após reparo configurável.

Validação: 258 testes Python aprovados, incluindo interface, com um teste de certificados preexistente incompatível com o runtime local excluído; cinco simulações Node aprovadas. O workflow Windows executa a suíte integral e testa o executável antes da publicação.

A relação de aliados ainda depende da validação do formato atual do cliente do Interstellar. Quando os dados não estão disponíveis, a interface informa isso. Capturas de revisão usam dados simulados. Não há promessa de compatibilidade com plugins do DarkBot nem de funcionamento perfeito no jogo.
