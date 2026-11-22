# Tarefa 2 (Predator): treinar a IA com o que a telemetria REAL mostrou, só em simulação

Só análise offline, simulação e treino em CPU. **Nenhum comando vai ao drone, nenhum script abre rede com o drone, nada aqui autoriza voo.**

## Regras que derrubam sessões

- **Nunca acesse nada fora de `/mnt/dados/Documentos/drone/predator`**, nem com Read, Glob ou ls. Não procure Python nem pacotes no sistema.
- **Não use subagentes** (ferramenta `task`).
- Use só `/home/vascon1/.local/share/aruco-venv/bin/python -P` (tem numpy e OpenCV; **não tem torch**). Não instale nada, não use a rede.
- Todo comando com `timeout` de no máximo 20 min; trabalho longo retomável (checkpoint).
- **Não leia nada em `capturas/`, exceto `capturas/jogo_*.csv`** (jogo de simulação). A telemetria real está **limpa** em `ia/reais/*.csv` (posição em metros a partir do ponto de partida, **sem latitude/longitude**) com `ia/reais/INDICE.json` dizendo o que é cada arquivo. Nunca tente reconstruir coordenadas. Não abra imagens nem vídeos.
- **Não rode** nenhum script que fale com o drone ou abra janela: `scripts/piloto_predator.py`, `voo_1m.py`, `voo_frente.py`, `teste_eixos.py`, `destravar.py`, `calibrar_*.py`, `gravar_voo.py`, `probe.py`, `falar_status.py`, `monitor_bateria.py`, `ensaio_*.py`, `controle.py`, `teste_motores.py`, `prepara_dados_reais.py`; `scripts/jogo_correcao.py` só com `--auto` ou `--sintonia`.
- Sem `git commit`/`push`. **Não edite** `predator/`, `scripts/`, `docs/diario-re.md` nem os arquivos de `ia/` da tarefa 1 (`ambiente.py`, `modelo.py`, `treina`, `prova`, pesos, resultados). Escreva só em `ia/real/` e em `docs/resultado_opencode_2.md`.

## Contexto

A tarefa 1 (`docs/resultado_opencode_1.md`) treinou, em simulação, uma MLP que apenas **copia o PD** (sem ganho) e que **perde todas as rodadas no modelo `medido`**. Faltam dois ingredientes: **dinâmica e ruído medidos no drone real** e **dados humanos**. Aqui o foco é o primeiro. Os dados reais são **poucos** (~12 min no total, em voos curtos de 2 a 25 s; a maior parte com o drone parado, no chão, destravado ou pousando; **nenhum voo em malha fechada, nenhum pairando de verdade**). Seja honesto sobre o que isso permite concluir.

Fatos medidos que **não podem ser contrariados sem evidência nos dados**: telemetria a ~10 Hz; parado, roll/pitch variam ±0,05° (o offset de nivelamento muda por voo); o desvio de 60 no manche fez a inclinação subir ~4° em ~0,2 s e **voltar a ~0 em ~0,5 s com o comando mantido**; atraso comando → inclinação ≤ 0,1–0,2 s; velocidade horizontal ~0,4 m/s com desvio 60; **a altura da telemetria não é confiável** (marca ~0 com o drone subindo); a leitura de bateria cai a 0–20 sob acelerador e volta (queda de tensão), não é um nível de carga; yaw = rumo do nariz.

## O que fazer

1. **Inventário honesto.** Para cada arquivo de `ia/reais/`, leia o `INDICE.json`, classifique: parado no chão / destravado no chão / no ar (use `v_vert`, `v_hor`, inclinação; **não use `altura`**) / pousando. Conte segundos em cada classe. Diga quantos segundos têm **comando conhecido** (`roll_us/pitch_us/yaw_us/acel_us` não vazios, ou fase com nota no índice) **e** o drone no ar.
2. **Ruído e atraso reais.** A partir dos trechos parados: desvio-padrão de roll/pitch/yaw, de `v_hor`, e do **ruído da posição** (`leste_m`, `norte_m`, só onde `satelites >= 8`): amplitude, correlação no tempo (autocorrelação a 0,1–1 s) e **perda de telemetria** (intervalos entre linhas > 0,15 s). Compare com o que o simulador (`scripts/jogo_correcao.py`, classe `Mundo`) usa: ruído correlacionado de 0,25 m e 10 Hz. Diga se o simulador está **otimista ou pessimista** e quanto.
3. **Resposta ao manche real.** Nos trechos com comando conhecido e drone no ar (ex.: `voofrente_20261120_151454`, `eixos_frente_20261120_182234`, `eixos_direita_20261120_210706`, `piloto_*`), estime: ganho de inclinação por unidade de manche, constante de tempo, tempo até a inclinação voltar a zero (lavagem) e atraso. Dê **intervalos de incerteza** (são poucos voos). Diga qual dos modelos do simulador (`velocidade`, `medido`, `antigo`, ver `scripts/simula_controle.py`) combina melhor com os dados e **com que confiança**. Se não der para decidir, diga.
4. **Simulador calibrado.** Crie `ia/real/ambiente_real.py` que **importa** o `Mundo` e acrescenta, por herança/composição (sem editar o original): ruído de posição e de velocidade medidos, perda de quadros de telemetria, offset de nivelamento por rodada e uma faixa de dinâmica coerente com os intervalos do item 3 (sorteada por rodada, não um valor único).
5. **Treinar de novo** a política da tarefa 1 (arquitetura igual: 22 → 32 → 32 → 2, saída contínua ±100%) **nesse ambiente calibrado**, com clonagem do PD + DAgger, sementes novas e disjuntas. Compare **política contra PD** em 100 sementes inéditas por modelo e por condição, no ambiente calibrado. Se a política aprender algo que o PD não faz (ex.: lidar melhor com perda de telemetria), diga; se for só cópia, diga.
6. **O que ela vai ver na prática (repetição aberta com dados reais).** Reconstrua a observação `(x, y, vx, vy)` dos 5 últimos passos e o comando anterior **a partir das telemetrias reais** (`leste_m`, `norte_m`, derivada filtrada, `v_hor`) em trechos de **drone parado/no ar**, sem fechar a malha. Rode a política e o PD e mostre: distribuição dos comandos, fração saturada, comandos sobre trechos **parados** (deveria ser ~0), e se algum trecho real faz a política mandar algo perigoso (saturação sustentada, inversão rápida de sinal). Isso é uma verificação de sanidade, **não** uma prova de que o drone ficaria parado.
7. **Limites e recomendação.** Liste o que os dados reais **não** cobrem (voo pairando, malha fechada, vento real, bateria carregada) e diga com franqueza se a política deve ou não ir ao drone, e o que falta medir antes (por exemplo, **voo com o controle de rádio** gravado só por leitura, e **bateria nova**). Não afirme que o drone vai ficar parado.

## Entrega

`docs/resultado_opencode_2.md`, em português do Brasil, com: inventário, ruído e atraso medidos (tabelas), estimativa da resposta ao manche com incerteza, comparação política × PD no ambiente calibrado, o que a política mandaria nos dados reais, e as limitações e recomendação. Código e resultados em `ia/real/`, com um script que reproduz as tabelas.
