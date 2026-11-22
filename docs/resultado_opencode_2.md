# Tarefa 2: calibracao e imitacao offline com telemetria real

## Conclusao
**Nao levar esta politica ao drone.** O treino continua sendo imitacao do PD, nao descoberta de um controlador melhor. Os ensaios abaixo sao simulados e o replay real e aberto: nenhuma saida foi enviada ao hardware. Nao se demonstrou que o drone ficaria parado.

Trabalho somente em CPU/numpy, sem torch, instalacao, rede, janelas, subagentes, commit ou push. Foram lidos apenas fontes locais e os CSVs sanitizados de `ia/reais/`; nao foram lidos arquivos de `capturas/`, imagens ou videos. Escritas apenas em `ia/real/` e neste relatorio. Os hashes dos fontes protegidos e dados foram comparados antes/depois em `verificacao.json`. Nenhuma coordenada geografica foi usada ou reconstruida.

## Inventario e criterios
Os 34 arquivos do indice somam **733.663 s** entre primeira e ultima linha. Nao extrapolei o ultimo intervalo nem usei `altura`. Somente **24.613 s** combinam comando conhecido e evidencia compativel com ar/pouso. Isso e uma estimativa operacional, nao uma anotacao visual confirmada.

Cada linha representa o intervalo ate a seguinte. Parado: estado 0, |v_vert| <=0,15 m/s, |v_hor| <=0,1 m/s e desvio angular do nivel de referencia <=1 grau. Destravado: mesmos criterios, estado 1; notas explicitas de nao decolagem permitem classificar repouso mesmo com estado diferente. Ar: estado diferente de 0, |v_vert| >=0,2 m/s OU (|v_hor| >=0,2 e desvio angular >=0,5 grau), com |roll| e |pitch| <35 graus. Pousando: evidencia de ar mais fase pouso/descida ou v_vert <=-0,2. Notas explicitas de nao voo vetam a classe ar. O restante fica indeterminado, inclusive tombamentos, mudancas de atitude no chao e ausencia de telemetria. A fase `voando` sozinha nao prova voo. Limiares nao foram validados com video e podem errar, sobretudo durante contato com o solo.

O nivel de referencia e a mediana por arquivo em estado 0 ou fases checagem/chao/recalibrar. Usar uma mediana nao separa movimentacao manual de mudanca de offset. As gravacoes longas em que a atitude muda ficam majoritariamente indeterminadas; isso nao contradiz a nota de que nao houve voo. O campo v_hor contem valores negativos: usei modulo para detectar movimento e a magnitude na fusao, sem assumir que o sinal represente uma direcao conhecida.

| Arquivo (sem .csv) | Parado s | Destravado s | Ar s | Pousando s | Indeterm. s | Cmd + ar/pouso s |
| --- | --- | --- | --- | --- | --- | --- |
| voo1m_20261101_121924 | 3.12 | 8.44 | 0.00 | 0.00 | 0.00 | 0.00 |
| voo1m_20261101_122050 | 3.12 | 9.36 | 0.00 | 0.00 | 0.00 | 0.00 |
| voo1m_20261101_122115 | 3.12 | 11.27 | 0.00 | 0.00 | 0.00 | 0.00 |
| voo1m_20261101_122237 | 3.12 | 1.35 | 8.54 | 12.07 | 4.24 | 0.00 |
| voo1m_20261101_122422 | 2.91 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| voo1m_20261101_122504 | 3.12 | 0.71 | 0.90 | 12.17 | 6.24 | 0.00 |
| voo1m_20261101_122724 | 3.12 | 1.31 | 0.81 | 3.22 | 1.40 | 0.00 |
| voo1m_20261120_084929 | 3.14 | 11.35 | 0.00 | 0.00 | 0.00 | 0.00 |
| voo1m_20261120_145855 | 3.13 | 1.32 | 0.80 | 3.74 | 0.81 | 0.00 |
| voo1m_20261120_150130 | 3.14 | 1.52 | 0.41 | 4.45 | 0.89 | 0.00 |
| voo1m_20261120_150505 | 3.15 | 3.94 | 0.00 | 0.00 | 0.00 | 0.00 |
| voo1m_20261120_150649 | 3.04 | 1.31 | 2.02 | 0.00 | 1.42 | 0.00 |
| voo1m_20261120_151033 | 3.14 | 2.02 | 0.00 | 0.00 | 2.63 | 0.00 |
| voo1m_20261120_151209 | 3.14 | 1.32 | 2.12 | 0.00 | 1.21 | 0.00 |
| voofrente_20261120_151454 | 2.83 | 1.32 | 1.32 | 17.00 | 7.21 | 1.22 |
| voofrente_20261120_151826 | 5.98 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| eixos_direita_20261120_210706 | 3.13 | 1.32 | 1.42 | 10.41 | 2.60 | 1.42 |
| eixos_frente_20261120_182234 | 3.12 | 1.31 | 1.32 | 1.71 | 1.30 | 1.32 |
| piloto_1120_205814_dados | 0.00 | 0.00 | 0.00 | 0.00 | 4.80 | 0.00 |
| piloto_1120_210847_dados | 18.46 | 0.87 | 2.96 | 0.00 | 17.39 | 2.96 |
| piloto_1120_211349_dados | 3.43 | 1.01 | 0.63 | 0.00 | 1.18 | 0.63 |
| piloto_1120_211650_dados | 6.02 | 0.00 | 0.00 | 0.00 | 0.14 | 0.00 |
| piloto_1120_211749_dados | 8.93 | 3.51 | 4.01 | 0.00 | 3.67 | 4.01 |
| piloto_1120_211934_dados | 36.47 | 0.00 | 0.00 | 0.00 | 29.62 | 0.00 |
| piloto_1120_212516_dados | 101.73 | 2.51 | 4.51 | 0.00 | 8.63 | 4.51 |
| piloto_1120_212751_dados | 92.29 | 0.00 | 0.00 | 0.00 | 6.11 | 0.00 |
| piloto_1120_213309_dados | 12.19 | 3.01 | 6.93 | 1.60 | 3.90 | 8.53 |
| piloto_1120_224053_dados | 0.00 | 0.00 | 0.00 | 0.00 | 4.07 | 0.00 |
| gravacao_1120_015519_telemetria | 9.89 | 0.00 | 0.00 | 0.00 | 0.10 | 0.00 |
| gravacao_1120_084427_telemetria | 9.93 | 0.00 | 0.00 | 0.00 | 0.10 | 0.00 |
| gravacao_1120_181457_telemetria | 4.33 | 0.00 | 0.00 | 0.00 | 5.68 | 0.00 |
| gravacao_1120_181703_telemetria | 2.88 | 0.00 | 0.00 | 0.00 | 0.12 | 0.00 |
| gravacao_1120_181810_telemetria | 0.00 | 0.00 | 0.00 | 0.00 | 2.91 | 0.00 |
| gravacao_1120_182010_telemetria | 0.74 | 0.00 | 0.00 | 0.00 | 74.24 | 0.00 |
| TOTAL | 365.870 | 70.086 | 38.708 | 66.375 | 192.624 | 24.613 |

Conhecido significa os quatro campos de comando preenchidos; alternativamente, a fase `frente`/`direita` explicitamente descrita nas tres notas de ensaio de eixo. Nao inferi a temporizacao completa de pulsos de acelerador apenas de uma nota sem marcacao inequivoca. Por isso a contagem e conservadora e nao equivale a segundos de excitacao isolada identificavel. As duas tentativas de teclado sem telemetria valida ficam indeterminadas apesar de terem comandos.

## Ruido em repouso
Para ruido, usei somente as partes estaveis de checagem/chao/recalibrar/destravar ou gravacao sem voo, dentro das classes de repouso. Exclui os trechos curtos (<1 s) e valores ausentes. Centro cada trecho separadamente, sem remover tendencia linear: a deriva lenta de GPS integra o erro observado, mas o vies absoluto de GPS e desconhecido. Para posicao, exigi satelites >=8. Reamostragem causal por retencao em grade de 0,1 s; linhas repetidas nao viram novas medidas independentes. Yaw e desembrulhado antes de centrar, em graus.

| Campo | Amostras na grade | Desvio-padrao | P95 \|residuo\| | Maior pico a pico |
| --- | --- | --- | --- | --- |
| roll | 3557 | 0.04948 | 0.07143 | 0.900 |
| pitch | 3557 | 0.03591 | 0.07857 | 0.600 |
| yaw | 3557 | 1.02342 | 2.04694 | 8.400 |
| v_hor | 3557 | 0.00868 | 0.00000 | 0.100 |
| leste_m | 3287 | 0.17479 | 0.38547 | 1.380 |
| norte_m | 3287 | 0.25938 | 0.61921 | 1.590 |

Unidades: graus nos angulos, m/s em v_hor e metros em posicao. Os desvios sao agrupados por amostra apos centralizacao por trecho. P95 zero em v_hor reflete quantizacao/muitas leituras zero, nao ausencia de ruido; somente quatro trechos variaveis sustentam sua ACF. Roll/pitch tipicos continuam na ordem de +/-0,05 grau; extremos maiores incluem pequena movimentacao residual. Selecao por repouso trunca extremos de velocidade/inclinacao, portanto nao e uma medida irrestrita do sensor nem de ruido em voo.

| Campo | 0.1s | 0.2s | 0.3s | 0.4s | 0.5s | 0.6s | 0.7s | 0.8s | 0.9s | 1.0s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| roll | 0.723 | 0.550 | 0.382 | 0.209 | 0.233 | 0.156 | 0.136 | 0.095 | 0.106 | 0.108 |
| pitch | 0.715 | 0.491 | 0.387 | 0.163 | 0.092 | 0.050 | 0.036 | 0.015 | 0.028 | 0.058 |
| yaw | 0.786 | 0.536 | 0.290 | 0.079 | -0.056 | -0.104 | -0.113 | -0.095 | -0.023 | 0.040 |
| v_hor | 0.925 | 0.849 | 0.774 | 0.698 | 0.623 | 0.547 | 0.471 | 0.488 | 0.418 | 0.333 |
| leste_m | 0.973 | 0.948 | 0.931 | 0.922 | 0.909 | 0.912 | 0.891 | 0.892 | 0.892 | 0.883 |
| norte_m | 0.980 | 0.969 | 0.957 | 0.943 | 0.948 | 0.923 | 0.914 | 0.906 | 0.923 | 0.930 |

ACF = mediana da correlacao de Pearson entre pares no mesmo trecho, excluindo variancia zero; nao concatenei fronteiras de voos. Numero de trechos por lag esta em `analise.json`. ACFs de trechos curtos/quantizados e vies de selecao limitam a inferencia; nao ha intervalo de confianca independente por linha, pois elas sao correlacionadas.

O Mundo original usa sigma=0,25 m por eixo e AR(1) com rho=0,85 por 0,1 s (rho em 1 s = 0.197). Em amplitude, e **pessimista no leste por fator 1.43** e **otimista no norte por fator 1.04**; nao cabe um unico rotulo para ambos. A correlacao observada em 1 s e 0.883/0.930, cerca de 4.5/4.7 vezes a original: o simulador e otimista sobre a persistencia da deriva. Ruido de GPS parado nao valida GPS em voo.

### Intervalos e medidas retidas
| Arquivo | dt mediano s | Intervalos >0,15s | Maior dt s | Linhas seguintes identicas % |
| --- | --- | --- | --- | --- |
| voo1m_20261101_121924 | 0.100 | 1 | 0.280 | 15.9 |
| voo1m_20261101_122050 | 0.100 | 1 | 0.290 | 16.4 |
| voo1m_20261101_122115 | 0.100 | 0 | 0.110 | 17.5 |
| voo1m_20261101_122237 | 0.100 | 1 | 0.350 | 6.6 |
| voo1m_20261101_122422 | 0.100 | 0 | 0.110 | 0.0 |
| voo1m_20261101_122504 | 0.100 | 0 | 0.110 | 14.3 |
| voo1m_20261101_122724 | 0.100 | 0 | 0.110 | 2.0 |
| voo1m_20261120_084929 | 0.100 | 0 | 0.110 | 17.5 |
| voo1m_20261120_145855 | 0.100 | 1 | 0.290 | 12.6 |
| voo1m_20261120_150130 | 0.100 | 1 | 0.290 | 12.9 |
| voo1m_20261120_150505 | 0.100 | 0 | 0.110 | 11.4 |
| voo1m_20261120_150649 | 0.100 | 0 | 0.110 | 13.0 |
| voo1m_20261120_151033 | 0.100 | 0 | 0.110 | 16.9 |
| voo1m_20261120_151209 | 0.100 | 0 | 0.110 | 5.2 |
| voofrente_20261120_151454 | 0.100 | 1 | 0.340 | 13.1 |
| voofrente_20261120_151826 | 0.100 | 0 | 0.110 | 5.1 |
| eixos_direita_20261120_210706 | 0.100 | 1 | 0.280 | 0.5 |
| eixos_frente_20261120_182234 | 0.100 | 0 | 0.110 | 6.9 |
| piloto_1120_205814_dados | 0.051 | 0 | 0.052 | 100.0 |
| piloto_1120_210847_dados | 0.156 | 172 | 0.235 | 70.2 |
| piloto_1120_211349_dados | 0.051 | 22 | 0.199 | 83.3 |
| piloto_1120_211650_dados | 0.050 | 0 | 0.086 | 89.3 |
| piloto_1120_211749_dados | 0.050 | 0 | 0.101 | 89.8 |
| piloto_1120_211934_dados | 0.050 | 1 | 0.231 | 89.3 |
| piloto_1120_212516_dados | 0.050 | 0 | 0.105 | 89.9 |
| piloto_1120_212751_dados | 0.050 | 0 | 0.090 | 91.0 |
| piloto_1120_213309_dados | 0.050 | 0 | 0.092 | 51.5 |
| piloto_1120_224053_dados | 0.050 | 0 | 0.060 | 100.0 |
| gravacao_1120_015519_telemetria | 0.109 | 1 | 0.353 | 10.2 |
| gravacao_1120_084427_telemetria | 0.111 | 0 | 0.148 | 9.0 |
| gravacao_1120_181457_telemetria | 0.109 | 0 | 0.125 | 5.6 |
| gravacao_1120_181703_telemetria | 0.110 | 0 | 0.122 | 0.0 |
| gravacao_1120_181810_telemetria | 0.110 | 0 | 0.128 | 0.0 |
| gravacao_1120_182010_telemetria | 0.113 | 1 | 0.150 | 10.2 |

Especificamente nos intervalos cujas duas pontas sao de repouso estrito: **90/5867 intervalos >0,15 s (1.53%)**, maximo 0.353 s. Os detalhes por arquivo estao em `analise.json`.
Foram 204/10463 intervalos entre linhas >0,15 s (1.95%). Este e o criterio solicitado, **nao uma taxa comprovada de pacotes UDP perdidos**: inclui agendamento do logger e linhas iniciais sem medida. "Identicas" compara conjuntamente angulos, velocidades e posicao, tratando ausencias iguais; quantizacao tambem produz repeticoes. Alguns logs de teclado repetem dados por ~0,5 s mesmo escrevendo a 20 Hz. Intervalos entre mudancas de angulos/velocidades validos nesses logs: P50/P95/max = 0.501/0.509/6.978 s. Medida identica nao comprova ausencia de pacote e mudanca nao garante atualizacao de todos os campos. O simulador de 10 Hz exatos e otimista quanto a essa irregularidade; nao e honesto chamar todo periodo sem mudanca de perda de rede.

## Resposta ao manche
Degraus anotados: desvio 60 mantido durante ~1,5 s; tempo zero e a primeira linha da fase, nao um timestamp de recepcao do comando no controlador de voo. A tabela usa mediana dos 0,5 s anteriores como baseline; na decolagem essa baseline ja esta em movimento. Retorno = duas amostras consecutivas dentro de max(0,5 grau, 10% do pico), ainda durante a fase. ND indica censura, nao ausencia de lavagem.

| Arquivo/eixo | Fonte | Delta cmd | Pico relativo graus | \|pico/cmd\| | Tempo pico s | Onset aparente s | Retorno s | \|vh\| max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| voofrente_20261120_151454/pitch | nota | 60 | -1.70 | 0.0283 | 0.110 | 0.000 | 0.410 | 0.40 |
| eixos_direita_20261120_210706/roll | nota | 60 | -0.80 | 0.0133 | 0.710 | 0.510 | 1.020 | 0.40 |
| eixos_frente_20261120_182234/pitch | nota | 60 | -4.20 | 0.0700 | 0.200 | 0.000 | 0.510 | 0.10 |
| piloto_1120_210847_dados/roll | csv | 20 | 172.60 | 8.6300 | 1.058 | 1.058 | ND | 0.00 |
| piloto_1120_210847_dados/pitch | csv | -20 | -1.10 | 0.0550 | 0.000 | 0.000 | ND | 0.00 |
| piloto_1120_210847_dados/pitch | csv | 20 | -41.90 | 2.0950 | 0.894 | 0.304 | ND | 0.00 |
| piloto_1120_211749_dados/roll | csv | -40 | 0.40 | 0.0100 | 0.401 | 0.401 | ND | 0.00 |
| piloto_1120_211749_dados/roll | csv | 40 | -3.50 | 0.0875 | 1.604 | 0.100 | ND | 0.50 |
| piloto_1120_211749_dados/pitch | csv | 40 | 1.10 | 0.0275 | 1.554 | 0.050 | ND | 0.50 |
| piloto_1120_212516_dados/roll | csv | 40 | -2.50 | 0.0625 | 1.657 | 1.155 | ND | 0.30 |
| piloto_1120_213309_dados/roll | csv | -60 | 1.60 | 0.0267 | 0.251 | 0.000 | ND | 0.20 |
| piloto_1120_213309_dados/roll | csv | 60 | -2.50 | 0.0417 | 0.250 | 0.050 | 0.351 | 0.10 |
| piloto_1120_213309_dados/roll | csv | -60 | 2.20 | 0.0367 | 0.000 | 0.000 | 0.150 | 0.00 |
| piloto_1120_213309_dados/roll | csv | 60 | 3.00 | 0.0500 | 0.401 | 0.100 | ND | 0.00 |
| piloto_1120_213309_dados/roll | csv | -60 | 1.30 | 0.0217 | 0.000 | 0.000 | 0.301 | 0.00 |
| piloto_1120_213309_dados/roll | csv | 60 | 1.30 | 0.0217 | 0.251 | 0.000 | 0.452 | 0.00 |
| piloto_1120_213309_dados/roll | csv | -60 | 3.60 | 0.0600 | 1.105 | 0.000 | ND | 0.10 |
| piloto_1120_213309_dados/roll | csv | -60 | -8.00 | 0.1333 | 0.451 | 0.151 | ND | 0.20 |
| piloto_1120_213309_dados/roll | csv | 60 | 2.60 | 0.0433 | 1.206 | 0.000 | 1.707 | 0.30 |
| piloto_1120_213309_dados/pitch | csv | -60 | 3.10 | 0.0517 | 0.401 | 0.000 | ND | 0.20 |
| piloto_1120_213309_dados/pitch | csv | -60 | 1.00 | 0.0167 | 1.909 | 0.100 | ND | 0.10 |
| piloto_1120_213309_dados/pitch | csv | 60 | -2.30 | 0.0383 | 0.503 | 0.101 | ND | 0.10 |
| piloto_1120_213309_dados/pitch | csv | 60 | -1.80 | 0.0300 | 0.501 | 0.000 | ND | 0.20 |
| piloto_1120_213309_dados/pitch | csv | 60 | -0.60 | 0.0100 | 0.201 | 0.201 | 0.301 | 0.20 |
| piloto_1120_213309_dados/pitch | csv | -60 | -0.50 | 0.0083 | 0.151 | 0.050 | 0.201 | 0.30 |
| piloto_1120_213309_dados/pitch | csv | -60 | 2.90 | 0.0483 | 0.301 | 0.201 | 0.804 | 0.30 |
| piloto_1120_213309_dados/pitch | csv | 60 | 17.90 | 0.2983 | 1.805 | 0.402 | ND | 1.70 |

Os eventos de teclado nao sao repeticoes independentes de um degrau isolado: ha comandos simultaneos, mudanca de acelerador/yaw, medidas retidas, retorno do comando e contato/tombamento. O evento com pico de roll >170 graus e inadmissivel para identificar dinamica linear. Esses eventos ficam na tabela por transparencia, mas **nao** entram como evidencia de ganho angular linear ou atraso causal. A resposta cruzada e relevante: no ensaio de roll, o pitch muda mais que o roll; o sinal/eixo fisico nao esta confirmado.

No melhor exemplo `eixos_frente`, pitch chega a -6,1 graus, contra baseline de chao ~-1,5: excursao ~4,6 graus (0,077 grau/unidade), pico a 0,20 s; usando a baseline imediatamente anterior, a excursao e 4,2 graus (0,070/unidade). Volta proximo da baseline em 0,51-0,61 s com o comando mantido. Em `voofrente`, o retorno relativo ocorre em 0,41 s e |vh| chega a 0,4 m/s. Isso e coerente com o transitorio ja descrito, mas nao mede um ganho estatico de 60 unidades.

Ajuste descritivo adicional nos primeiros 0,8 s das fases: resposta de primeira ordem seguida de lavagem, ganho com sinal livre e condicao angular inicial como parametro nuisance. Grade: atraso aparente -0,10 a 0,20 s em 0,05 s; subida 0,04/0,06/0,08/0,10/0,14/0,18/0,25 s; lavagem 0,08/0,10/0,14/0,20/0,30/0,45/0,60 s; alternativa sem lavagem. Atraso negativo testa erro de alinhamento/perturbacao preexistente, **nao atraso fisico negativo**. Envelope = ajustes com RMSE ate 0,5 grau acima do minimo e ganho <=0,5. E um intervalo de sensibilidade dependente da grade, **nao IC de 95%**. Nao ha repeticoes limpas suficientes para um IC estatistico causal defensavel.

| Arquivo/eixo | N | RMSE lavado / mantido graus | Melhor subida / lavagem / atraso s | Ganho interno | Envelope subida; lavagem; atraso; ganho |
| --- | --- | --- | --- | --- | --- |
| voofrente_20261120_151454/roll | 8 | 0.606 / 0.633 | 0.040 / 0.080 / 0.100 | 0.121 | [0.040, 0.250]; [0.080, 0.600]; [-0.100, 0.200]; [0.000, 0.397] |
| voofrente_20261120_151454/pitch | 8 | 0.239 / 0.692 | 0.140 / 0.140 / 0.050 | 0.100 | [0.040, 0.250]; [0.080, 0.600]; [-0.100, 0.200]; [0.014, 0.496] |
| eixos_direita_20261120_210706/roll | 9 | 0.120 / 0.239 | 0.250 / 0.450 / -0.100 | 0.038 | [0.040, 0.250]; [0.080, 0.600]; [-0.100, 0.200]; [0.023, 0.355] |
| eixos_direita_20261120_210706/pitch | 9 | 0.334 / 0.931 | 0.100 / 0.080 / 0.150 | 0.138 | [0.040, 0.250]; [0.080, 0.600]; [-0.100, 0.200]; [0.028, 0.479] |
| eixos_frente_20261120_182234/roll | 9 | 0.350 / 0.193 | 0.180 / 0.600 / 0.200 | 0.043 | [0.040, 0.250]; [0.080, 0.600]; [-0.100, 0.200]; [0.033, 0.116] |
| eixos_frente_20261120_182234/pitch | 9 | 0.652 / 1.578 | 0.140 / 0.140 / 0.050 | 0.179 | [0.040, 0.250]; [0.080, 0.450]; [-0.100, 0.150]; [0.076, 0.400] |

No pitch de `eixos_frente`, o melhor ajuste da grade tem subida/lavagem ~0,14/0,14 s e atraso aparente 0,05 s; o envelope e muito largo. O ganho interno ajustado (~0,179 grau/unidade) nao e o ganho de pico: os filtros atenuam o pico. A estimativa de atraso fisico permanece apenas **0-0,2 s**, sem resolucao para separar envio, sensor e logger. Lavagem efetiva de retorno ~0,4-0,6 s nao deve ser confundida com a constante exponencial interna. Nem o valor unico de 0,45 s do simulador original foi identificado com precisao, nem os novos valores sao uma verdade de hardware.

**Comparacao dos modelos:** `medido` e qualitativamente melhor que `antigo` para a inclinacao que desaparece sob comando mantido, com confianca moderada apenas nessa caracteristica e baixa nos parametros. O modelo `velocidade` tambem e compativel: uma malha interna de velocidade pode inclinar transitoriamente e depois nivelar; o seu Mundo nem fornece uma previsao angular comparavel. A velocidade observada de ~0,4 m/s com desvio 60 favorece uma escala de 0,0067 m/s/unidade, mas deriva, decolagem e estimador confundem isso. **Nao e possivel decidir entre `velocidade` e `medido` com confianca.** `antigo` fica como hipotese de contraste, nao modelo real confirmado.

## Ambiente calibrado
`ambiente_real.py` herda `Mundo` e mantem seu integrador, vento e criterio de perda, sem copiar nem editar a fisica original. O dicionario fisico e copiado por rodada e reconectado aos eixos, sem mutar MODELOS global.

| Parametro sorteado uniformemente por rodada | Faixa | Interpretacao |
| --- | --- | --- |
| Atraso | 0-0,20 s | Intervalo conservador, aplicado nos tres modelos |
| Coeficiente angular interno | 0,05-0,20 grau/unidade | Hipotese plausivel, nao IC do ganho de pico |
| Constante de subida | 0,04-0,18 s | Subfaixa plausivel do envelope, nao cobertura completa |
| Constante de lavagem em medido | 0,10-0,50 s | Transitorios incertos; retorno depende tambem da subida |
| Velocidade por unidade | 0,0033-0,010 m/s | 0,2-0,6 m/s para 60 unidades, faixa de sensibilidade |
| Constante de velocidade | 0,20-0,80 s | Nao identificada diretamente; hipotese de sensibilidade |

Em `antigo` nao se acrescenta lavagem; apenas varia-se seu ganho/subida/atraso como hipotese de contraste, portanto nao e a mesma configuracao nominal da tarefa 1. Os intervalos cobrem variabilidade plausivel, nao todas as combinacoes fisicas reais e nao sao uma distribuicao posterior inferida. A mudanca simultanea de condicoes impede atribuir diferencas numericas entre tarefas exclusivamente ao treino.

Ruido: bootstrap de **37 trechos** estaveis com GPS, centrados por trecho, com selecao proporcional a duracao e inicio aleatorio, rotacionados por um rumo fixo por rodada. Posicao leste/norte e residuo de v_hor sao reamostrados juntos; avancam uma amostra por medida entregue, refletindo nas pontas em vez de criar salto de fronteira. Mantem quantizacao e correlacao local, mas a reflexao e uma convencao artificial, nao um modelo generativo comprovado para 60 s. Trechos reais sao poucos e reutilizados entre treino/prova: a independencia e de sementes simuladas, nao de novas sessoes reais.

Velocidade: derivada da posicao com filtro 0,6 anterior +0,4 derivada; a direcao vem dessa derivada, e a magnitude e a media entre sua norma e |v_hor|. A telemetria nao fornece direcao de movimento e yaw e rumo do nariz, nao rumo da velocidade. Na simulacao, v_hor sintetico e norma da velocidade fisica mais residuo observado. Essa fusao 50/50 e uma escolha explicita de engenharia, nao parametro identificado. Em repouso produz comandos por deriva de GPS; nao foi usado estado oculto como entrada da politica ou rotulo.

Offset de nivelamento: sorteado entre medianas reais por arquivo e somado apenas a roll_m/pitch_m. Nao atua como aceleracao gravitacional: um offset do sensor nao prova inclinacao fisica. Como a arquitetura obrigatoria recebe apenas posicao/velocidade, esse offset e um parametro nuisance nao observado pela rede e nao permite alegar robustez aprendida a nivelamento.

Duas condicoes fixadas antes da prova: **nominal**, agenda de medidas extraida dos intervalos entre linhas dos logs nao-teclado; **retencao**, agenda extraida dos intervalos entre mudancas de angulos/velocidades nos logs de teclado, incluindo as caudas longas. Entre entregas mantem-se toda a observacao anterior. O controle tenta a 10 Hz; a agenda e quantizada pelo passo de controle, sem adicionar atraso extra fixo. Na retencao, aplicar a espera do campo mais lento ao vetor inteiro e um estresse conservador, nao identificacao da perda de pacotes por campo. Os dois ambientes usam os mesmos trechos de ruido; a retencao tambem estica sua escala temporal. Nao ha garantia de extrapolacao para outros tipos de falha.

## Treino e prova
MLP da tarefa 1 **importada, nao modificada**: 22 -> 32 -> 32 -> 2, 1.858 parametros, tanh e saida continua 100*tanh. Cinco observacoes medidas (x,y,vx,vy), ordem temporal, mais comando anterior. Inicializacao repete a primeira observacao e comando zero. Professor PD kp=60, kd=15, limite original +/-60%; rede permite +/-100%. Adam, lote 512, taxa 0,001, ate 100 epocas, paciencia 10, melhoria minima 1e-7, melhor checkpoint da validacao em cada etapa. Normalizacao inicial congelada, piso 0,1. Nao houve dados humanos no treino nem rotulos de estado verdadeiro.

Uma clonagem mais tres DAgger puros: a politica anterior visita estados, PD rotula; agrega-se ao conjunto anterior. Ambas as condicoes e os tres modelos entram em todas as etapas. Inicializacao da rede 532019; embaralhamento 532020+etapa. Final escolhido como etapa 3 antes da prova, sem selecionar por resultado do teste. Validacao DAgger usa trajetorias da politica anterior, nunca agregadas ao treino; as perdas entre etapas nao sao do mesmo conjunto de entradas.

| Etapa | Sementes coleta por modelo/condicao | Sementes validacao | Amostras acumuladas | Validacao N | Epocas | MSE validacao pp^2 |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | [310000, 310023] | [410000, 410003] | 60945 | 10206 | 75 | 0.33603 |
| 1 | [311000, 311011] | [411000, 411003] | 91698 | 10262 | 32 | 0.14237 |
| 2 | [312000, 312011] | [412000, 412003] | 122495 | 10296 | 74 | 0.10615 |
| 3 | [313000, 313011] | [413000, 413003] | 153255 | 9758 | 16 | 0.13311 |

Intervalos de sementes sao inclusivos; nao se sobrepoem a tarefa 1, entre treino/validacao/prova nem entre etapas. Numeros comuns entre modelos/condicoes sao intencionais para comparacao, nao replicas independentes. As contagens por modelo/condicao estao nos quatro JSONs de treino. O trecho medido e menor porque a rodada termina ao sair de 4 m.

Prova: **100 sementes ineditas 510000-510099 por modelo, condicao e controlador**, 1.200 rodadas no total. Horizonte 60 s; integracao 50 Hz, comando/historico 10 Hz mesmo quando a medida e retida. Perda: raio verdadeiro >4 m, com interrupcao. Erro medio usa raio verdadeiro a cada passo fisico ate termino e depois media entre rodadas; em perdas ha censura, nao sucesso por ter erro medio <4. Mesmas sementes entre PD/MLP, parametros e sensores separados da acao por RNG independente do sensor. Vento/deriva continuam hipoteses do Mundo original, nao medidos.

| Modelo/condicao | Ctrl | Erro medio m | Perdas/100 | Duracao s | >=95% % | >=57% % | Variacao pp/passo | Medidas retidas % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| velocidade/nominal | PD | 0.2852 | 0 | 60.00 | 0.00 | 0.55 | 0.658 | 5.35 |
| velocidade/nominal | MLP | 0.2854 | 0 | 60.00 | 0.00 | 0.44 | 0.653 | 5.35 |
| velocidade/retencao | PD | 0.3018 | 0 | 60.00 | 0.00 | 0.61 | 0.234 | 75.37 |
| velocidade/retencao | MLP | 0.3019 | 0 | 60.00 | 0.00 | 0.46 | 0.249 | 75.37 |
| antigo/nominal | PD | 0.5313 | 0 | 60.00 | 0.00 | 2.61 | 0.869 | 5.35 |
| antigo/nominal | MLP | 0.5328 | 0 | 60.00 | 0.00 | 2.43 | 0.875 | 5.35 |
| antigo/retencao | PD | 0.6849 | 3 | 59.39 | 0.00 | 13.41 | 1.444 | 75.36 |
| antigo/retencao | MLP | 0.6918 | 3 | 59.40 | 0.00 | 12.28 | 1.634 | 75.37 |
| medido/nominal | PD | 1.8101 | 100 | 8.26 | 0.00 | 70.81 | 1.256 | 5.85 |
| medido/nominal | MLP | 1.8105 | 100 | 8.25 | 0.00 | 69.13 | 1.382 | 5.85 |
| medido/retencao | PD | 1.8194 | 100 | 8.25 | 0.00 | 69.30 | 1.126 | 73.80 |
| medido/retencao | MLP | 1.8196 | 100 | 8.25 | 0.00 | 67.65 | 1.431 | 73.79 |

>=95% e fracao dos passos com algum eixo perto do limite fisico, >=57% usa limiar comum perto do limite do professor. Variacao = media de (|delta_roll|+|delta_pitch|)/2 por passo, incluindo transicao desde zero. Sao medias por rodada, nao pooling de passos de rodadas com duracoes diferentes.

| Modelo/condicao | Delta erro MLP-PD m | IC bootstrap pareado 95% | Delta perdas |
| --- | --- | --- | --- |
| velocidade/nominal | 0.00020 | [0.00011, 0.00030] | 0 |
| velocidade/retencao | 0.00016 | [0.00005, 0.00028] | 0 |
| antigo/nominal | 0.00152 | [0.00098, 0.00221] | 0 |
| antigo/retencao | 0.00689 | [0.00193, 0.01311] | 0 |
| medido/nominal | 0.00034 | [-0.00013, 0.00080] | 0 |
| medido/retencao | 0.00017 | [-0.00034, 0.00067] | 0 |

ICs reamostram as 100 sementes, 2.000 vezes, semente 99117, condicionados ao simulador e aos dados reutilizados; nao quantificam risco no drone nem incerteza do modelo real. Pequenas diferencas numericas nao demonstram nova capacidade de controle. A rede so recebeu rotulos do PD, sem objetivo de melhorar perdas ou lidar com medidas velhas; nao se demonstrou vantagem consistente de robustez a retencao. Em medido, copiar o professor continua sem resolver o vento/deriva persistente. Zero perdas/100, quando ocorre, nao significa risco zero (limite aproximado da regra de tres ~3%, sob hipotese binomial idealizada).

## Replay aberto real
Reconstituicao causal a 10 Hz, exigindo GPS >=8 e posicao/yaw validos em trechos consecutivos classificados como repouso ou ar/pouso. Alvo e a primeira posicao do trecho; nao se afirma que era o alvo do piloto. Deriva leste/norte filtrada antes de girar para o corpo com yaw de cada amostra; isso evita atribuir rotacao do nariz a velocidade translacional. Mesma fusao de magnitude usada no ambiente. Historico reiniciado ao mudar para indeterminado/sem GPS. Nenhum comando influencia a proxima medida real.

**MLP** usa o proprio comando anterior hipotetico, como ocorreria no controle, mas sem fechar a malha fisica. **MLP_csv_anterior** e uma segunda verificacao teacher-forced com o comando de roll/pitch realmente registrado no passo anterior (1500 subtraido), quando disponivel; trechos sem esses campos ficam ausentes nessa variante, e o primeiro comando e zero. O PD nao depende do comando anterior. Os resultados nao devem ser tratados como previsao de trajetoria controlada.

| Trecho/ctrl | Passos | P5/mediana/P95 pp (eixos juntos) | \|cmd\| medio | Ambos <5% | >=95% | >=57% | Maior seq. >=95% / >=57% s | Inversoes rapidas |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| repouso/PD | 4070 | -40.23 / 0.00 / 60.00 | 15.80 | 26.73% | 0.00% | 14.82% | 0.0 / 29.9 | 0 |
| repouso/MLP | 4070 | -40.31 / -0.01 / 58.77 | 15.74 | 26.76% | 0.00% | 14.10% | 0.0 / 29.9 | 0 |
| repouso/MLP_csv_anterior | 2921 | -47.17 / 0.26 / 59.19 | 20.46 | 18.42% | 0.00% | 14.82% | 0.0 / 28.4 | 0 |
| ar_pouso/PD | 1002 | -54.51 / 0.00 / 60.00 | 23.18 | 17.07% | 0.00% | 28.64% | 0.0 / 12.3 | 0 |
| ar_pouso/MLP | 1002 | -53.97 / -0.04 / 59.99 | 23.09 | 17.27% | 0.00% | 27.94% | 0.0 / 12.2 | 0 |
| ar_pouso/MLP_csv_anterior | 223 | -25.00 / -0.01 / 58.63 | 17.64 | 29.60% | 0.00% | 9.87% | 0.0 / 1.9 | 0 |

Inversao rapida: um mesmo eixo muda de sinal entre dois passos adjacentes de 0,1 s, ambos com modulo >=30 pp. Sinalizar risco: >=95% por >=1 s OU >=57% por >=2 s OU qualquer inversao rapida. Estes limiares sao alarmes offline conservadores, nao limites de voo certificados. A contagem de passos tem sobreposicao entre variantes e nao representa segundos independentes de voo.

| Grupo/ctrl | Arquivo | Inicio-fim s | Sequencia >=95% s | Sequencia >=57% s | Inversoes |
| --- | --- | --- | --- | --- | --- |
| repouso/PD | piloto_1120_211934_dados | 30.1-66.0 | 0.0 | 29.9 | 0 |
| repouso/PD | piloto_1120_212516_dados | 31.2-117.4 | 0.0 | 20.5 | 0 |
| repouso/PD | piloto_1120_212751_dados | 33.2-61.7 | 0.0 | 3.6 | 0 |
| repouso/MLP | piloto_1120_211934_dados | 30.1-66.0 | 0.0 | 29.9 | 0 |
| repouso/MLP | piloto_1120_212516_dados | 31.2-117.4 | 0.0 | 20.0 | 0 |
| repouso/MLP | piloto_1120_212751_dados | 33.2-61.7 | 0.0 | 3.6 | 0 |
| repouso/MLP_csv_anterior | piloto_1120_211934_dados | 30.1-66.0 | 0.0 | 28.4 | 0 |
| repouso/MLP_csv_anterior | piloto_1120_212516_dados | 31.2-117.4 | 0.0 | 13.8 | 0 |
| ar_pouso/PD | voo1m_20261101_122237 | 8.2-26.4 | 0.0 | 12.3 | 0 |
| ar_pouso/PD | voo1m_20261120_145855 | 5.1-9.5 | 0.0 | 3.2 | 0 |
| ar_pouso/PD | voo1m_20261120_150130 | 5.5-10.1 | 0.0 | 2.9 | 0 |
| ar_pouso/PD | eixos_direita_20261120_210706 | 9.1-13.0 | 0.0 | 2.5 | 0 |
| ar_pouso/PD | piloto_1120_213309_dados | 20.7-26.5 | 0.0 | 2.6 | 0 |
| ar_pouso/MLP | voo1m_20261101_122237 | 8.2-26.4 | 0.0 | 12.2 | 0 |
| ar_pouso/MLP | voo1m_20261120_145855 | 5.1-9.5 | 0.0 | 3.2 | 0 |
| ar_pouso/MLP | voo1m_20261120_150130 | 5.5-10.1 | 0.0 | 2.9 | 0 |
| ar_pouso/MLP | eixos_direita_20261120_210706 | 9.1-13.0 | 0.0 | 2.5 | 0 |
| ar_pouso/MLP | piloto_1120_213309_dados | 20.7-26.5 | 0.0 | 2.2 | 0 |

No chao, o comportamento desejavel seria ~zero. Deriva aparente de GPS e erros do estimador podem induzir comandos nao nulos e ate saturacao perto do limite de 60% do professor: isso e um **problema de sanidade**, nao movimento real corrigido. A politica nao tem detector de solo nem vigia, nao recebe a qualidade/idade da medida nas 22 entradas e nao deve ser conectada diretamente ao drone. Comandos pequenos neste replay tampouco validariam controle em voo.

## Limites e recomendacao
- Nao ha pairado real sustentado, voo em malha fechada, teste de rejeicao de vento medido nem excitacao controlada e independente por eixo. Os poucos segundos no ar incluem subida, pouso e perda de controle.
- Bateria: a leitura 0-20 sob acelerador e queda de tensao/indicador sem unidade confirmada, nao carga restante. Nao foi usado esse campo como nivel de carga ou parametro dinamico. Faltam dados com bateria nova, carregada e tensao medida sob carga.
- Altura de telemetria nao e confiavel e nao entrou em nenhuma classificacao, ajuste, observacao ou metrica. Tambem nao ha altitude/yaw controlados, obstaculos, pouso seguro ou recuperacao de falhas neste ambiente horizontal.
- Os trechos estaveis de GPS sao amostra limitada e possivelmente selecionada; bootstrap reutiliza dados reais, nao aumenta a evidencia experimental. Ganhos, arrasto, vento e correspondencia dos eixos continuam incertos. A grade de parametros nao cobre todos os envelopes ajustados nem todas as falhas reais.
- Treino por imitacao nao corrige um professor que falha. Sem informacao explicita de idade/qualidade da medida, a arquitetura nao pode distinguir com certeza repouso, medida retida e GPS parado.

**Recomendacao: nao colocar o checkpoint no drone.** Primeiro, obter bateria nova/carregada e diagnostico eletrico; gravar por leitura um voo conduzido por pessoa com controle de radio, com trecho de repouso antes/depois, alvo conhecido, pairado e excitacoes pequenas por eixo, sob supervisao e condicoes seguras. Para identificar resposta ao manche, sincronizar tambem o comando do radio por instrumentacao passiva autorizada; telemetria sem comando nao resolve a identificacao. Confirmar sinais/eixos, atraso, atualizacao por campo, contato com o solo e resposta a vento antes de escolher a dinamica. Depois, validar professor/seguranca em simulacao e bancada, limites conservadores e interrupcao independente. Qualquer futuro voo precisaria de autorizacao especifica; este trabalho nao autoriza nenhum.

## Reproducao e artefatos
Todos os comandos abaixo partem da raiz do projeto e foram executados com timeout externo <=1.200.000 ms. Nao e necessario retreinar para reproduzir as tabelas. Use exclusivamente o interpretador indicado; -P evita shadowing e -B impede caches nos diretorios protegidos.

```bash
/home/vascon1/.local/share/aruco-venv/bin/python -P -B ia/real/executa.py analise
/home/vascon1/.local/share/aruco-venv/bin/python -P -B ia/real/resposta_fit.py
/home/vascon1/.local/share/aruco-venv/bin/python -P -B ia/real/executa.py treino --etapa 0
/home/vascon1/.local/share/aruco-venv/bin/python -P -B ia/real/executa.py treino --etapa 1
/home/vascon1/.local/share/aruco-venv/bin/python -P -B ia/real/executa.py treino --etapa 2
/home/vascon1/.local/share/aruco-venv/bin/python -P -B ia/real/executa.py treino --etapa 3
/home/vascon1/.local/share/aruco-venv/bin/python -P -B ia/real/executa.py prova
/home/vascon1/.local/share/aruco-venv/bin/python -P -B ia/real/executa.py replay
/home/vascon1/.local/share/aruco-venv/bin/python -P -B ia/real/executa.py verifica
/home/vascon1/.local/share/aruco-venv/bin/python -P -B ia/real/executa.py tabelas
```

Para somente regenerar as tabelas e este documento: ultimo comando (`tabelas`). Treino retoma por etapa completa, validando hash do ambiente/calibracao; uma interrupcao perde a coleta/treino da etapa atual, nao as anteriores. Prova salva a cada 10 rodadas e rejeita checkpoint com pesos/ambiente/calibracao diferentes. Nao ha retomada no meio de epoca. O comando `snapshot` e apenas para registrar uma nova auditoria inicial, nao deve ser refeito para mascarar alteracoes entre execucoes.

- `analise.py`, `analise.json`: inventario, ACF, eventos e parametros descritivos; `calibracao.json`: trechos e intervalos usados pelo ambiente.
- `resposta_fit.py`, `ajuste_resposta.json`: grade e envelopes do ajuste angular; os criterios e todas as seis respostas principais estao preservados.
- `ambiente_real.py`, `executa.py`: ambiente herdado e pipeline com guardas de rede, GUI e escrita fora das entregas no processo principal.
- `dados_0.npz` a `dados_3.npz`, `pesos_0.npz` a `pesos_3.npz`, `treino_0.json` a `treino_3.json`: conjuntos agregados, pesos e curvas; validacoes sao regeneraveis pelas sementes.
- `prova.json`: todas as 1.200 rodadas com sementes e metricas. `replay.json`: todos os comandos por trecho/variante, classes e tempos; `tabelas.json`: resumos e alarmes. `relatorio.py`: gerador desta entrega.
- `fontes_antes.json`, `verificacao.json`: hashes, testes de determinismo, observacoes/rotulos, ausencia de mutacao global, arquitetura, guardas e cobertura das sementes; 12 rodadas recalculadas (uma por celula) devem ser identicas.

SHA-256 dos pesos finais: `430b2382826fbca2c077198bbcf429542049665888b52f68759c48e7021e4ef1`. SHA-256 da calibracao: `fe1ca2b92d2556c00281b0ee6a637438f75a3604e9620e99aa6bbababc69677a`. Nenhum peso da tarefa 1 foi sobrescrito.
