# Resultado: imitacao offline para manter o Predator no alvo

## Conclusao

**Nao recomendo levar esta politica ao drone real.** A MLP aprendeu a reproduzir
o PD, sem vantagem pratica de erro ou suavidade. Ambos funcionaram nos modelos
`velocidade` e `antigo`, mas perderam 100/100 rodadas no `medido`, inclusive apos
tres iteracoes de DAgger. O historico nao resolveu essa falha.

Tudo foi feito em simulacao, offline, somente CPU/numpy. Nenhum comando foi
enviado ao drone, nenhuma janela foi aberta e nada disso foi voado. Nao houve
instalacao, acesso a rede, subagentes, commit ou push. As alteracoes manuais
ficaram em `ia/` e neste arquivo; os fontes do simulador e do PD nao foram editados.

## Dados humanos

Contagem feita antes do treino, excluindo o arquivo com `_pd`:

| Modelo | Rodadas | Amostras | Rodadas completas | Duracao media observada por rodada |
|---|---:|---:|---:|---:|
| velocidade | 15 | 2.725 | 2 | 19,904 s |
| antigo | 14 | 97 | 0 | 0,629 s |
| medido | 4 | 172 | 0 | 4,635 s |
| Total | 33 | 2.994 | 2 | - |

Arquivos: `jogo_1120_214150.csv`, `jogo_1120_214205.csv`,
`jogo_1120_214435.csv`, `jogo_1120_214619.csv`, `jogo_1120_223803.csv` e
`jogo_1120_224103.csv`, todos em `capturas/`. Uma rodada e identificada por
arquivo, numero de rodada e modelo. Completa significa ultimo timestamp >=59,8 s
ou erro verdadeiro observado >4 m. Duracao observada e ultimo menos primeiro
timestamp; nao inclui um trecho inicial nao registrado.

**Nao houve dados humanos suficientes para um segundo professor confiavel.**
Foi adotado, antes do treino, o criterio de pelo menos 10 rodadas completas por
modelo. Nenhum modelo o atingiu. Os dados humanos nao entraram no treinamento
nem na validacao; foram usados somente como referencia descritiva. Esse limiar
e uma escolha conservadora deste experimento, nao uma garantia estatistica.

## Metodo

- Simulador: importacao de `Mundo` de `scripts/jogo_correcao.py`, que usa `Eixo`
  e `MODELOS` de `scripts/simula_controle.py`. Nao houve copia da fisica.
- Professor: `PD(Ganhos(kp=60, kd=15))`, mantendo o limite original de **60%**.
  Nao foi aumentado para 100% para alterar a linha de base.
- Entrada: 22 valores, os ultimos 5 vetores medidos `(x, y, vx, vy)` em ordem
  temporal e o comando anterior `(roll, pitch)`. Na inicializacao, repete-se a
  primeira observacao 5 vezes e usa-se comando anterior zero.
- Nenhuma entrada usa posicao/velocidade verdadeira, vento, identificador do
  modelo, semente ou parametros fisicos. Estado verdadeiro serve apenas para
  metricas e termino da rodada. Rotulos usam exclusivamente as medidas do PD.
- Uma unica MLP compartilhada: `22 -> 32 -> 32 -> 2`, 1.858 parametros,
  ativacoes `tanh`, saida continua `100*tanh`, sem discretizacao ou pos-processamento.
  A saida pode atingir +/-100%, embora os exemplos do professor parem em +/-60%.
- Normalizacao por media e desvio do conjunto inicial de treino, piso de 0,1
  no desvio, congelada nas demais etapas. Alvos divididos por 100.
- Perda L2, Adam com taxa 0,001, lotes de 512, ate 100 epocas. Early stopping
  com paciencia de 10 epocas e melhoria minima de 1e-7 na MSE normalizada;
  restaura os melhores pesos da validacao dentro de cada etapa.
- DAgger puro: a politica da etapa anterior dirige a simulacao; em cada estado
  visitado, consulta-se a acao do PD, que vira rotulo, mas nao dirige a coleta.
  Os exemplos sao agregados aos anteriores e a rede e retreinada. Nao houve RL,
  professor alternativo otimizado nem acesso ao estado oculto para decidir acoes.

### Sementes e treino

| Etapa | Sementes de coleta, por modelo | velocidade | antigo | medido | Total acumulado | Epocas | MSE validacao, pontos percentuais ao quadrado |
|---|---|---:|---:|---:|---:|---:|---:|
| Clonagem | 10000-10049 | 30.000 | 30.000 | 4.229 | 64.229 | 100 | 0,66564 |
| DAgger 1 | 11000-11024 | 15.000 | 15.000 | 1.888 | 96.117 | 92 | 0,29448 |
| DAgger 2 | 12000-12024 | 15.000 | 15.000 | 1.864 | 127.981 | 51 | 0,21671 |
| DAgger 3 | 13000-13024 | 15.000 | 15.000 | 2.065 | 160.046 | 11 | 0,22123 |

Validacao: sementes **20000-20011**, disjuntas do treino, com 7.200 exemplos de
`velocidade`, 7.200 de `antigo` e 953 de `medido` em cada etapa. Na clonagem, a
validacao vem do PD; no DAgger, vem de trajetorias da politica anterior, sempre
rotuladas pelo PD e nunca agregadas ao treino. Por isso as perdas entre etapas
nao representam exatamente o mesmo conjunto de entradas. A clonagem atingiu o
teto de epocas; o early stopping encerrou as tres etapas DAgger.

A inicializacao usa semente numpy 42; embaralhamento usa 42+etapa. O checkpoint
final escolhido foi o da etapa 3, antes de abrir a prova. Nao se ajustaram pesos,
ganhos ou hiperparametros depois dos resultados de teste.

## Prova nominal

**100 rodadas por modelo e por controlador**, sementes **90000-90099**, nunca
usadas em treino/validacao. Horizonte de 60 s, fisica a 50 Hz, medidas e comando
a 10 Hz, ruido correlacionado de 0,25 m. Atrasos originais: 0,15 s em
`velocidade`/`medido` e 0,40 s em `antigo`. Mesmas sementes entre controladores
para comparacao pareada. Repete-se a medicao inicial como no `auto` original.

Rodada perdida quando erro verdadeiro **>4 m**, com interrupcao imediata; nao
se conta como sucesso o restante do horizonte. Erro e media do raio verdadeiro
a 50 Hz ate o termino, seguida da media entre rodadas. Nos casos perdidos, essa
interrupcao censura o erro: 1,84 m nao significa manter posicao por 60 s.

Saturacao comum: fracao dos passos de controle em que pelo menos um eixo esta
em modulo >=95 pontos percentuais, perto do limite fisico de 100%. A coluna
`>=57%` mostra adicionalmente o uso perto do limite de 60% do professor, com
o mesmo limiar absoluto para ambos. Suavidade e a media de
`(|roll_t-roll_anterior|+|pitch_t-pitch_anterior|)/2`, incluindo a transicao
inicial desde zero; unidade: pontos percentuais por passo de 0,1 s. Menor e mais suave.

| Modelo | Controlador | Erro medio (m) | Perdidas | Saturado >=95% | Tempo >=57% | Variacao por passo |
|---|---|---:|---:|---:|---:|---:|
| velocidade | PD | 0,2069 | 0/100 | 0,00% | 3,11% | 13,746 |
| velocidade | Politica | 0,2069 | 0/100 | 0,00% | 2,49% | 13,790 |
| antigo | PD | 0,7068 | 0/100 | 0,00% | 29,53% | 12,089 |
| antigo | Politica | 0,7069 | 0/100 | 0,00% | 27,46% | 12,177 |
| medido | PD | 1,8432 | 100/100 | 0,00% | 74,66% | 7,322 |
| medido | Politica | 1,8430 | 100/100 | 0,00% | 73,34% | 7,568 |

A politica foi ligeiramente **menos suave**, nao mais. A menor frequencia perto
de 60% nao se traduziu em melhora de posicao. Saturacao em 100% igual a zero nao
e evidencia de folga util de controle: o professor so demonstra ate 60%.

### Referencia humana observada

| Modelo | Erro medio (m) | Perdas observadas / rodadas | Saturado >=95% | Tempo >=57% | Variacao por amostra |
|---|---:|---:|---:|---:|---:|
| velocidade | 0,7025 | 0/15 | 0,00% | 6,81% | 3,589 |
| antigo | 0,9577 | 0/14 | 0,00% | 0,00% | 0,222 |
| medido | 1,3150 | 0/4 | 0,00% | 38,01% | 4,557 |

Essas metricas sao medias entre rodadas dos trechos registrados. **Nao sao uma
prova humana de 100 rodadas/60 s**, nem usam as mesmas sementes. Tempos de amostra
do jogo humano podem variar. Ausencia de perda registrada nao significa sucesso
nas rodadas interrompidas. Especialmente em `antigo`, os trechos duram menos de
1 s em media; seria incorreto concluir que o humano supera o PD ou a politica.
Nao foi inventado um controlador humano para repetir sementes no simulador.

## Robustez

Grade cartesiana completa: atrasos **0,05; 0,10; 0,15; 0,20; 0,25; 0,30; 0,35;
0,40; 0,45; 0,50 s** e ruido **0,1; 0,2; 0,3; 0,4; 0,5; 0,6 m**. Cada uma
das 60 combinacoes foi rodada 100 vezes por modelo e controlador: **36.000
rodadas adicionais**. Atraso substitui, nao soma, o atraso original; nao e atraso
extra da telemetria. A fisica tem passo de 20 ms, portanto a aplicacao e
quantizada nesse passo. O parametro de ruido mantem o processo correlacionado
original, nao vira ruido branco.

Usam-se as mesmas sementes 90000-90099 como numeros aleatorios comuns entre
condicoes. As celulas nao sao 60 conjuntos de sementes independentes. Nao houve
retreino na grade; sao condicoes fora da distribuicao nominal de treino.

| Modelo | Controlador | Faixa do erro medio entre celulas (m) | Faixa de perdas | Duracao media das rodadas |
|---|---|---:|---:|---:|
| velocidade | PD | 0,1465-0,3844 | 0%-0% | 60 s |
| velocidade | Politica | 0,1464-0,3850 | 0%-0% | 60 s |
| antigo | PD | 0,4731-1,1227 | 0%-0% | 60 s |
| antigo | Politica | 0,4721-1,1231 | 0%-0% | 60 s |
| medido | PD | 1,8291-1,8934 | 100%-100% | 7,997-8,071 s |
| medido | Politica | 1,8283-1,8929 | 100%-100% | 8,003-8,072 s |

Pior celula de erro medio em cada modelo: **atraso 0,50 s e ruido 0,60 m**.

| Modelo | Controlador | Erro medio (m) | Perdidas | Saturado >=95% | Tempo >=57% | Variacao por passo |
|---|---|---:|---:|---:|---:|---:|
| velocidade | PD | 0,3844 | 0/100 | 0,00% | 49,05% | 24,865 |
| velocidade | Politica | 0,3850 | 0/100 | 0,00% | 46,64% | 25,663 |
| antigo | PD | 1,1227 | 0/100 | 0,00% | 69,50% | 19,436 |
| antigo | Politica | 1,1231 | 0/100 | 0,00% | 67,73% | 20,387 |
| medido | PD | 1,8934 | 100/100 | 0,00% | 82,35% | 14,449 |
| medido | Politica | 1,8929 | 100/100 | 0,00% | 80,88% | 15,455 |

Definindo quebra como qualquer rodada perdida na celula, **nao se encontrou
o ponto de quebra de `velocidade` ou `antigo` dentro da grade**, para nenhum dos
controladores. Isso nao garante estabilidade fora dela ou por mais de 60 s.
Em `medido`, os dois ja quebram no menor atraso/ruido testado, **0,05 s/0,10 m**,
com 100% de perdas, e tambem na condicao nominal.

Os JSONs `ia/robustez_01.json` a `ia/robustez_05.json` preservam as metricas
das **360 celulas controlador/modelo/condicao** e de cada rodada individual,
incluindo saturacao e suavidade, nao apenas estes extremos.

## Por que o medido continua falhando

Foi tentada a MLP com historico de 0,4 s entre primeira e ultima observacao,
comando anterior e tres agregacoes DAgger, incluindo os estados visitados antes
de sair do alvo. O resultado final continua sendo falha total. Imitar um
professor que falha nao oferece, por si so, uma demonstracao de como resolver
o problema; o PD rotula usando apenas a observacao atual, sem explorar memoria.

Nesse modelo, o passa-alta faz a inclinacao decair quando o comando permanece
constante, enquanto vento/deriva continuam empurrando o drone. Isso ajuda a
explicar a dificuldade de rejeitar a perturbacao persistente com comando
limitado. **Nao foi provado que toda politica possivel falha**, nem se demonstrou
que uma outra forma de explorar o historico resolveria. O experimento nao deve
ser apresentado como sucesso no modelo mais proximo da resposta transitoria
observada, nem como prova de impossibilidade matematica.

## Artefatos e reproducao

- `ia/modelo.py`: MLP, normalizacao, Adam, early stopping e persistencia `.npz`.
- `ia/ambiente.py`: adaptacao offline, features, coleta DAgger e leitura humana.
- `ia/treina.py`: quatro etapas retomaveis por checkpoint de etapa.
- `ia/pesos_0.npz` a `ia/pesos_3.npz`: pesos; `pesos_3.npz` e a politica final.
- `ia/dados_0.npz` a `ia/dados_3.npz`: conjuntos agregados; `validacao.npz`
  guarda a validacao inicial. A validacao DAgger e regenerada por semente.
- `ia/treino_0.json` a `ia/treino_3.json`: contagens e curvas de validacao.
- `ia/humanos.json`: contagem e metricas por rodada humana.
- `ia/prova.json`, `ia/prova_repetida.json`: prova nominal e repeticao do zero.
- `ia/robustez_01.json` a `ia/robustez_05.json`: grade completa em cinco partes.
- `ia/audita.py`, `ia/resumo.json`: verificacao de cobertura, medias e hashes.
- `ia/test_offline.py`: quatro testes de features/rotulos DAgger, determinismo,
  atraso local sem mutacao global, aprendizagem/persistencia e ausencia de rede.

Python 3.12.16, numpy 2.5.5, sem torch. SHA-256 do checkpoint final:
`dd7b74b33f9d6d54949550580a11f50b7b70bfae763c2ce947f91e6fddd7000b`.
Hashes dos fontes e CSVs estao em `ia/resumo.json`. O codigo desativa escrita
de bytecode antes dos imports locais, evitando caches novos nos fontes importados.

Comandos a partir da raiz deste projeto, sempre com timeout externo de no maximo
20 minutos por comando. Use somente este interpretador; `-B` desativa bytecode:

```bash
/home/vascon1/.local/share/aruco-venv/bin/python -P -B ia/test_offline.py
/home/vascon1/.local/share/aruco-venv/bin/python -P -B ia/treina.py --etapa 0
/home/vascon1/.local/share/aruco-venv/bin/python -P -B ia/treina.py --etapa 1
/home/vascon1/.local/share/aruco-venv/bin/python -P -B ia/treina.py --etapa 2
/home/vascon1/.local/share/aruco-venv/bin/python -P -B ia/treina.py --etapa 3
/home/vascon1/.local/share/aruco-venv/bin/python -P -B ia/prova.py
/home/vascon1/.local/share/aruco-venv/bin/python -P -B ia/prova.py --atraso .05 .10 --saida ia/robustez_01.json
/home/vascon1/.local/share/aruco-venv/bin/python -P -B ia/prova.py --atraso .15 .20 --saida ia/robustez_02.json
/home/vascon1/.local/share/aruco-venv/bin/python -P -B ia/prova.py --atraso .25 .30 --saida ia/robustez_03.json
/home/vascon1/.local/share/aruco-venv/bin/python -P -B ia/prova.py --atraso .35 .40 --saida ia/robustez_04.json
/home/vascon1/.local/share/aruco-venv/bin/python -P -B ia/prova.py --atraso .45 .50 --saida ia/robustez_05.json
/home/vascon1/.local/share/aruco-venv/bin/python -P -B ia/audita.py
```

Nao e necessario retreinar para reproduzir as tabelas: os pesos estao incluidos.
`prova.py` reaproveita celulas prontas e valida hash dos pesos, numero e inicio
das sementes. Para repetir calculo do zero, use outro arquivo de saida em `ia/`,
por exemplo `--saida ia/prova_nova.json`; para robustez, mantenha os argumentos
de atraso/ruido e escolha outro nome. Uma interrupcao perde no maximo a celula
em andamento. O treino retoma da ultima etapa concluida, nao do meio de uma epoca.
Se houver retreino, mantenha resultados antigos separados: o checkpoint de prova
rejeita pesos com hash diferente.

Foram auditadas 366 celulas/36.600 rodadas principais, e outras 600 rodadas
nominais foram recalculadas do zero: **todos os resultados nominais e por rodada
foram identicos**. Os quatro testes offline passaram. Validacao e teste sao
disjuntos, mas 0 perdas em 100 nao equivale a risco real zero; mesmo sob uma
hipotese binomial idealizada, a regra de tres daria limite superior aproximado
de 3% para uma condicao com 0/100 perdas.

## Limitacoes e recomendacao

A dinamica do simulador veio de **dois voos curtos do drone real**. Os tres
modelos sao hipoteses simplificadas; parametros de atraso, vento, ruido,
arrasto, eixos e resposta ao comando nao foram validados amplamente. Nao se
simulam altitude, yaw, visao falhando, perda de pacotes, bateria, obstaculos ou
o conjunto completo de seguranca do voo. O teste usa limite simulado de 4 m,
nao integra `Vigia`, e nao demonstra uma integracao segura com hardware.

**Recomendacao: nao levar esta politica ao drone agora.** Ela so acrescenta
complexidade ao comportamento do PD, nao melhora a suavidade e falha totalmente
em `medido`. Qualquer avaliacao futura exigiria primeiro identificacao mais
confiavel da dinamica e dos eixos, dados humanos completos, professor capaz de
resolver `medido` e testes de falhas em simulacao. Antes de qualquer eventual
ensaio real, seriam indispensaveis validacao em bancada sem helices, limites de
comando conservadores, vigia independente, interrupcao manual, area isolada,
supervisao humana e autorizacao explicita para aquele voo. Essas salvaguardas
nao tornam o checkpoint atual aprovado e nao autorizam voo.
