# Tarefa 1 (Predator): IA que mantém o drone parado, por imitação, só em simulação

Só simulação e treino offline, só CPU. **Nenhum comando vai ao drone, nenhum script abre rede com o drone, nada aqui autoriza voo.**

## Regras que derrubam sessões

- **Nunca acesse nada fora de `/mnt/dados/Documentos/drone/predator`**, nem com Read, Glob ou ls. Não procure Python nem pacotes no sistema.
- **Não use subagentes** (ferramenta `task`).
- Use só este Python: `/home/vascon1/.local/share/aruco-venv/bin/python -P` (tem numpy e OpenCV; **não tem torch**). Não instale nada, não use a rede.
- Todo comando com `timeout` de no máximo 20 min. Trabalho longo deve ser retomável (checkpoint) e rodado em pedaços.
- **Não rode** nenhum destes (enviam comando ao drone ou abrem janela): `scripts/piloto_predator.py`, `voo_1m.py`, `voo_frente.py`, `teste_eixos.py`, `destravar.py`, `calibrar_*.py`, `gravar_voo.py`, `probe.py`, `falar_status.py`, `monitor_bateria.py`, `ensaio_*.py`, `controle.py`, `teste_motores.py`, `scripts/jogo_correcao.py` sem `--auto` ou `--sintonia`.
- **Não abra nem envie imagens** de `capturas/` (os `.jpg`/`.h264`). Pode ler os `.csv` de `capturas/jogo_*.csv`.
- Sem `git commit`/`push`, sem apagar `capturas/`, e **não edite** `predator/`, `scripts/` nem `docs/diario-re.md`. Trabalhe só em `ia/` e escreva o resultado em `docs/resultado_opencode_1.md`.

## Objetivo

Treinar uma política que **fica parada em cima do alvo** a partir da observação que o drone real tem: posição medida (ruidosa, 10 Hz), velocidade estimada e um histórico curto. A saída é **contínua, de −100% a +100% de força por eixo** (roll e pitch; 100 unidades de manche = 100%), como um manche analógico, e não liga/desliga. Compare com o professor (controlador PD) e com o humano.

## Ambiente e dados (já existem)

- `scripts/jogo_correcao.py`: classe `Mundo` (física, vento que gira devagar, ruído da medida correlacionado), modelos `velocidade`, `medido` e `antigo` em `scripts/simula_controle.py` (`MODELOS`). Leia, **importe** (`sys.path.insert`) e não edite.
- `predator/controle.py`: `PD`, `Ganhos`, `Vigia`, `para_percentual` e `de_percentual`. O PD com kp 60, kd 15 é o professor.
- Humano: `capturas/jogo_*.csv` (sem `_pd`): colunas `t, rodada, modelo, amp, med_x, med_y, vel_x, vel_y, real_x, real_y, cmd_roll, cmd_pitch` (cmd = % de força, −100 a 100). Poucos dados (poucas rodadas, a maioria no modelo `velocidade`). Antes de treinar, **conte** quantas rodadas e amostras há por modelo.
- Professor: gere com `Mundo` e `PD` (veja `auto` e `avalia` em `scripts/jogo_correcao.py`) quanto precisar.
- Resultados anteriores do PD (referência): erro médio 0,22 m no `velocidade`, 0,70 m no `antigo`, e **falha total (15/15 perdidas) no `medido`**.

## O que fazer

1. **Entrada da rede:** posição e velocidade medidas dos últimos 5 passos (x, y, vx, vy) e o comando anterior. **Nada de estado verdadeiro do simulador** (`real_x`, `real_y`, vento) na entrada; use-os só para avaliar.
2. **Imitação em duas etapas:** (a) clonagem de comportamento do professor PD; (b) **DAgger** no simulador: rode a política aprendida, peça a ação do professor nos estados visitados e retreine, por algumas iterações. Adicione o humano como segundo professor, se houver dados suficientes (diga se não houver).
3. **Modelo:** MLP pequeno em numpy (sem torch), saída com `tanh` escalada para ±100%, perda L2 (ou Huber). Faça normalização, validação por sementes disjuntas e `early stopping`.
4. **Prova** com sementes que nunca foram usadas: 100 rodadas de 60 s por modelo (`velocidade`, `antigo`, `medido`), comparando política, PD e (onde existir) humano em: erro médio, % de rodadas perdidas (> 4 m), fração do tempo saturado e **suavidade** (variação do comando por passo).
5. **Robustez:** repita a prova com atraso de 0,05 s a 0,5 s e ruído de 0,1 a 0,6 m. Diga em que ponto a política quebra e o PD também.
6. **Modelo `medido`:** o PD não consegue. Tente fazer a política conseguir (ela vê um histórico). Se não conseguir, **diga**; não force. Não invente resultado.
7. Salve pesos e código em `ia/` (`ia/modelo.py`, `ia/treina.py`, `ia/prova.py`, pesos em `.npz`) e um script `ia/prova.py` que reproduz a tabela.

## Entrega

`docs/resultado_opencode_1.md` com: dados usados (contagem real), tabela de prova por modelo, robustez, limitações honestas (a dinâmica do simulador veio de **dois voos curtos** do drone real; **nada disso foi voado**), e uma recomendação clara sobre se vale levar a política ao drone real (sim ou não, e com quais salvaguardas). Mantenha o texto direto e em português do Brasil.
