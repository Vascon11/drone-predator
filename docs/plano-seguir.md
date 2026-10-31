# Plano do modo seguir por gestos

Desenho combinado em 2026-10-31. Nada disso foi testado em voo. A implementação começa em simulação.

## Sequência

| Etapa | O que acontece | Quem decide |
|---|---|---|
| 1. Decolar | Botão, com a pessoa afastada | Humano |
| 2. Subir e esperar | Sobe para a altura de voo e paira | Drone |
| 3. Procurar | Gira devagar até achar alguém, com tempo limite | IA |
| 4. Aguardar | Fica parado esperando o gesto | IA |
| 5. Seguir | Mantém a pessoa no centro da imagem | IA |
| 6. Mover ou parar | Gesto de braço | Pessoa |
| 7. Pousar | Gesto ou botão, com o controle na mão | Pessoa |

## Gestos

| Gesto | Ação |
|---|---|
| Triângulo | Pairar; vale como parar tudo |
| Um braço | Seguir ou mover devagar para aquele lado |
| Dois braços abertos | Pousar |

Evitar "dois braços levantados" em comandos importantes: parece com o triângulo e com se espreguiçar.

## Regras

- Sem decolagem por gesto nem automática ao ligar.
- Altura de 1,7 m é um alvo aproximado: o barômetro do Predator varia cerca de 1 m parado.
- Manter a pessoa no centro só gira o drone. Não impede deriva nem aproximação, então a distância também precisa de correção.
- Sem pessoa, gesto incerto ou vídeo velho: manche no centro e pairar, sem busca longa nem pouso automático.
- Controle físico na mão como reserva em todo voo.

## Antes de voar com a IA

1. Passar no reteste de falsos disparos com vídeos novos.
2. Voar pelo controle ao ar livre e medir a deriva.
3. Confirmar sentido dos eixos e a troca entre controle e notebook.
4. Só então liberar comandos, um por vez, com autorização explícita.
