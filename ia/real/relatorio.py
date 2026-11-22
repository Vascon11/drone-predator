"""Reproduz as tabelas e o relatorio a partir dos resultados persistidos."""
import json
from pathlib import Path
from analise import np

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]


def load(nome):
    return json.loads((OUT / nome).read_text())


def streak(mask):
    best = current = 0
    for b in mask:
        current = current + 1 if b else 0
        best = max(best, current)
    return best * .1


def gerar():
    a, p, replay = load('analise.json'), load('prova.json'), load('replay.json')
    fits, cal = load('ajuste_resposta.json'), load('calibracao.json')
    lines = []
    def put(s=''):
        lines.append(s)
    def table(headers, rows):
        def cell(value):
            return str(value).replace('|', '\\|')
        put('| ' + ' | '.join(map(cell, headers)) + ' |')
        put('| ' + ' | '.join(['---']*len(headers)) + ' |')
        for row in rows:
            put('| ' + ' | '.join(map(cell, row)) + ' |')
        put()
    def fmt(x, n=3):
        return 'ND' if x is None else f'{x:.{n}f}'
    inv = a['inventario']
    totals = {k:sum(r['segundos'][k] for r in inv) for k in inv[0]['segundos']}
    known = sum(r['comando_ar_s'] for r in inv)
    put('# Tarefa 2: calibracao e imitacao offline com telemetria real')
    put()
    put('## Conclusao')
    put('**Nao levar esta politica ao drone.** O treino continua sendo imitacao do PD, nao descoberta de um controlador melhor. Os ensaios abaixo sao simulados e o replay real e aberto: nenhuma saida foi enviada ao hardware. Nao se demonstrou que o drone ficaria parado.')
    put()
    put('Trabalho somente em CPU/numpy, sem torch, instalacao, rede, janelas, subagentes, commit ou push. Foram lidos apenas fontes locais e os CSVs sanitizados de `ia/reais/`; nao foram lidos arquivos de `capturas/`, imagens ou videos. Escritas apenas em `ia/real/` e neste relatorio. Os hashes dos fontes protegidos e dados foram comparados antes/depois em `verificacao.json`. Nenhuma coordenada geografica foi usada ou reconstruida.')
    put()
    put('## Inventario e criterios')
    put(f'Os {len(inv)} arquivos do indice somam **{sum(totals.values()):.3f} s** entre primeira e ultima linha. Nao extrapolei o ultimo intervalo nem usei `altura`. Somente **{known:.3f} s** combinam comando conhecido e evidencia compativel com ar/pouso. Isso e uma estimativa operacional, nao uma anotacao visual confirmada.')
    put()
    put('Cada linha representa o intervalo ate a seguinte. Parado: estado 0, |v_vert| <=0,15 m/s, |v_hor| <=0,1 m/s e desvio angular do nivel de referencia <=1 grau. Destravado: mesmos criterios, estado 1; notas explicitas de nao decolagem permitem classificar repouso mesmo com estado diferente. Ar: estado diferente de 0, |v_vert| >=0,2 m/s OU (|v_hor| >=0,2 e desvio angular >=0,5 grau), com |roll| e |pitch| <35 graus. Pousando: evidencia de ar mais fase pouso/descida ou v_vert <=-0,2. Notas explicitas de nao voo vetam a classe ar. O restante fica indeterminado, inclusive tombamentos, mudancas de atitude no chao e ausencia de telemetria. A fase `voando` sozinha nao prova voo. Limiares nao foram validados com video e podem errar, sobretudo durante contato com o solo.')
    put()
    put('O nivel de referencia e a mediana por arquivo em estado 0 ou fases checagem/chao/recalibrar. Usar uma mediana nao separa movimentacao manual de mudanca de offset. As gravacoes longas em que a atitude muda ficam majoritariamente indeterminadas; isso nao contradiz a nota de que nao houve voo. O campo v_hor contem valores negativos: usei modulo para detectar movimento e a magnitude na fusao, sem assumir que o sinal represente uma direcao conhecida.')
    put()
    table(['Arquivo (sem .csv)', 'Parado s', 'Destravado s', 'Ar s', 'Pousando s', 'Indeterm. s', 'Cmd + ar/pouso s'],
        [[r['arquivo']]+[fmt(r['segundos'][k],2) for k in totals]+[fmt(r['comando_ar_s'],2)] for r in inv]+
        [['TOTAL']+[fmt(v,3) for v in totals.values()]+[fmt(known,3)]])
    put('Conhecido significa os quatro campos de comando preenchidos; alternativamente, a fase `frente`/`direita` explicitamente descrita nas tres notas de ensaio de eixo. Nao inferi a temporizacao completa de pulsos de acelerador apenas de uma nota sem marcacao inequivoca. Por isso a contagem e conservadora e nao equivale a segundos de excitacao isolada identificavel. As duas tentativas de teclado sem telemetria valida ficam indeterminadas apesar de terem comandos.')
    put()
    put('## Ruido em repouso')
    put('Para ruido, usei somente as partes estaveis de checagem/chao/recalibrar/destravar ou gravacao sem voo, dentro das classes de repouso. Exclui os trechos curtos (<1 s) e valores ausentes. Centro cada trecho separadamente, sem remover tendencia linear: a deriva lenta de GPS integra o erro observado, mas o vies absoluto de GPS e desconhecido. Para posicao, exigi satelites >=8. Reamostragem causal por retencao em grade de 0,1 s; linhas repetidas nao viram novas medidas independentes. Yaw e desembrulhado antes de centrar, em graus.')
    put()
    table(['Campo', 'Amostras na grade', 'Desvio-padrao', 'P95 |residuo|', 'Maior pico a pico'],
        [[k, r['n'], fmt(r['std'],5), fmt(r['amplitude_p95'],5), fmt(r['pico_a_pico_max'],3)] for k,r in a['ruido'].items()])
    put('Unidades: graus nos angulos, m/s em v_hor e metros em posicao. Os desvios sao agrupados por amostra apos centralizacao por trecho. P95 zero em v_hor reflete quantizacao/muitas leituras zero, nao ausencia de ruido; somente quatro trechos variaveis sustentam sua ACF. Roll/pitch tipicos continuam na ordem de +/-0,05 grau; extremos maiores incluem pequena movimentacao residual. Selecao por repouso trunca extremos de velocidade/inclinacao, portanto nao e uma medida irrestrita do sensor nem de ruido em voo.')
    put()
    table(['Campo']+[f'{.1*i:.1f}s' for i in range(1,11)],
        [[k]+[fmt(v,3) for v in r['acf']] for k,r in a['ruido'].items()])
    put('ACF = mediana da correlacao de Pearson entre pares no mesmo trecho, excluindo variancia zero; nao concatenei fronteiras de voos. Numero de trechos por lag esta em `analise.json`. ACFs de trechos curtos/quantizados e vies de selecao limitam a inferencia; nao ha intervalo de confianca independente por linha, pois elas sao correlacionadas.')
    put()
    se, sn = [a['ruido'][k]['std'] for k in ('leste_m','norte_m')]
    put(f'O Mundo original usa sigma=0,25 m por eixo e AR(1) com rho=0,85 por 0,1 s (rho em 1 s = {0.85**10:.3f}). Em amplitude, e **pessimista no leste por fator {0.25/se:.2f}** e **otimista no norte por fator {sn/.25:.2f}**; nao cabe um unico rotulo para ambos. A correlacao observada em 1 s e {a["ruido"]["leste_m"]["acf"][-1]:.3f}/{a["ruido"]["norte_m"]["acf"][-1]:.3f}, cerca de {a["ruido"]["leste_m"]["acf"][-1]/(.85**10):.1f}/{a["ruido"]["norte_m"]["acf"][-1]/(.85**10):.1f} vezes a original: o simulador e otimista sobre a persistencia da deriva. Ruido de GPS parado nao valida GPS em voo.')
    put()
    put('### Intervalos e medidas retidas')
    table(['Arquivo', 'dt mediano s', 'Intervalos >0,15s', 'Maior dt s', 'Linhas seguintes identicas %'],
        [[r['arquivo'],fmt(r['dt_mediana'],3),r['gaps_015'],fmt(r['dt_max'],3),fmt(100*r['repetidas'],1)] for r in inv])
    ngaps = sum(r['gaps_015'] for r in inv)
    ninterval = sum(r['linhas']-1 for r in inv)
    quiet_gaps = sum(r['gaps_repouso_015'] for r in inv)
    quiet_n = sum(r['intervalos_repouso'] for r in inv)
    put(f'Especificamente nos intervalos cujas duas pontas sao de repouso estrito: **{quiet_gaps}/{quiet_n} intervalos >0,15 s ({100*quiet_gaps/quiet_n:.2f}%)**, maximo {max(r["dt_repouso_max"] for r in inv):.3f} s. Os detalhes por arquivo estao em `analise.json`.')
    put(f'Foram {ngaps}/{ninterval} intervalos entre linhas >0,15 s ({100*ngaps/ninterval:.2f}%). Este e o criterio solicitado, **nao uma taxa comprovada de pacotes UDP perdidos**: inclui agendamento do logger e linhas iniciais sem medida. "Identicas" compara conjuntamente angulos, velocidades e posicao, tratando ausencias iguais; quantizacao tambem produz repeticoes. Alguns logs de teclado repetem dados por ~0,5 s mesmo escrevendo a 20 Hz. Intervalos entre mudancas de angulos/velocidades validos nesses logs: P50/P95/max = '+ '/'.join(fmt(x,3) for x in np.percentile(cal['intervalos_lentos'],[50,95,100]))+' s. Medida identica nao comprova ausencia de pacote e mudanca nao garante atualizacao de todos os campos. O simulador de 10 Hz exatos e otimista quanto a essa irregularidade; nao e honesto chamar todo periodo sem mudanca de perda de rede.')
    put()
    put('## Resposta ao manche')
    put('Degraus anotados: desvio 60 mantido durante ~1,5 s; tempo zero e a primeira linha da fase, nao um timestamp de recepcao do comando no controlador de voo. A tabela usa mediana dos 0,5 s anteriores como baseline; na decolagem essa baseline ja esta em movimento. Retorno = duas amostras consecutivas dentro de max(0,5 grau, 10% do pico), ainda durante a fase. ND indica censura, nao ausencia de lavagem.')
    put()
    table(['Arquivo/eixo', 'Fonte', 'Delta cmd', 'Pico relativo graus', '|pico/cmd|', 'Tempo pico s', 'Onset aparente s', 'Retorno s', '|vh| max'],
        [[r['arquivo']+'/'+r['eixo'],r['fonte'],fmt(r['delta_cmd'],0),fmt(r['pico_deg'],2),fmt(r['ganho_pico'],4),fmt(r['pico_s'],3),fmt(r['atraso_aparente_s'],3),fmt(r['retorno_s'],3),fmt(r['vh_max'],2)] for r in a['respostas']])
    put('Os eventos de teclado nao sao repeticoes independentes de um degrau isolado: ha comandos simultaneos, mudanca de acelerador/yaw, medidas retidas, retorno do comando e contato/tombamento. O evento com pico de roll >170 graus e inadmissivel para identificar dinamica linear. Esses eventos ficam na tabela por transparencia, mas **nao** entram como evidencia de ganho angular linear ou atraso causal. A resposta cruzada e relevante: no ensaio de roll, o pitch muda mais que o roll; o sinal/eixo fisico nao esta confirmado.')
    put()
    put('No melhor exemplo `eixos_frente`, pitch chega a -6,1 graus, contra baseline de chao ~-1,5: excursao ~4,6 graus (0,077 grau/unidade), pico a 0,20 s; usando a baseline imediatamente anterior, a excursao e 4,2 graus (0,070/unidade). Volta proximo da baseline em 0,51-0,61 s com o comando mantido. Em `voofrente`, o retorno relativo ocorre em 0,41 s e |vh| chega a 0,4 m/s. Isso e coerente com o transitorio ja descrito, mas nao mede um ganho estatico de 60 unidades.')
    put()
    put('Ajuste descritivo adicional nos primeiros 0,8 s das fases: resposta de primeira ordem seguida de lavagem, ganho com sinal livre e condicao angular inicial como parametro nuisance. Grade: atraso aparente -0,10 a 0,20 s em 0,05 s; subida 0,04/0,06/0,08/0,10/0,14/0,18/0,25 s; lavagem 0,08/0,10/0,14/0,20/0,30/0,45/0,60 s; alternativa sem lavagem. Atraso negativo testa erro de alinhamento/perturbacao preexistente, **nao atraso fisico negativo**. Envelope = ajustes com RMSE ate 0,5 grau acima do minimo e ganho <=0,5. E um intervalo de sensibilidade dependente da grade, **nao IC de 95%**. Nao ha repeticoes limpas suficientes para um IC estatistico causal defensavel.')
    put()
    table(['Arquivo/eixo', 'N', 'RMSE lavado / mantido graus', 'Melhor subida / lavagem / atraso s', 'Ganho interno', 'Envelope subida; lavagem; atraso; ganho'],
        [[f['arquivo']+'/'+f['eixo'],f['n'],fmt(f['melhor_lavagem']['rmse'])+' / '+fmt(f['melhor_mantido']['rmse']),
          ' / '.join(fmt(f['melhor_lavagem'][k]) for k in ('subida','lavagem','atraso')),fmt(f['melhor_lavagem']['ganho']),
          '; '.join('['+', '.join(fmt(x) for x in f['envelope'][k])+']' for k in ('subida','lavagem','atraso','ganho'))] for f in fits])
    put('No pitch de `eixos_frente`, o melhor ajuste da grade tem subida/lavagem ~0,14/0,14 s e atraso aparente 0,05 s; o envelope e muito largo. O ganho interno ajustado (~0,179 grau/unidade) nao e o ganho de pico: os filtros atenuam o pico. A estimativa de atraso fisico permanece apenas **0-0,2 s**, sem resolucao para separar envio, sensor e logger. Lavagem efetiva de retorno ~0,4-0,6 s nao deve ser confundida com a constante exponencial interna. Nem o valor unico de 0,45 s do simulador original foi identificado com precisao, nem os novos valores sao uma verdade de hardware.')
    put()
    put('**Comparacao dos modelos:** `medido` e qualitativamente melhor que `antigo` para a inclinacao que desaparece sob comando mantido, com confianca moderada apenas nessa caracteristica e baixa nos parametros. O modelo `velocidade` tambem e compativel: uma malha interna de velocidade pode inclinar transitoriamente e depois nivelar; o seu Mundo nem fornece uma previsao angular comparavel. A velocidade observada de ~0,4 m/s com desvio 60 favorece uma escala de 0,0067 m/s/unidade, mas deriva, decolagem e estimador confundem isso. **Nao e possivel decidir entre `velocidade` e `medido` com confianca.** `antigo` fica como hipotese de contraste, nao modelo real confirmado.')
    put()
    put('## Ambiente calibrado')
    put('`ambiente_real.py` herda `Mundo` e mantem seu integrador, vento e criterio de perda, sem copiar nem editar a fisica original. O dicionario fisico e copiado por rodada e reconectado aos eixos, sem mutar MODELOS global.')
    put()
    table(['Parametro sorteado uniformemente por rodada', 'Faixa', 'Interpretacao'], [
        ['Atraso', '0-0,20 s', 'Intervalo conservador, aplicado nos tres modelos'],
        ['Coeficiente angular interno', '0,05-0,20 grau/unidade', 'Hipotese plausivel, nao IC do ganho de pico'],
        ['Constante de subida', '0,04-0,18 s', 'Subfaixa plausivel do envelope, nao cobertura completa'],
        ['Constante de lavagem em medido', '0,10-0,50 s', 'Transitorios incertos; retorno depende tambem da subida'],
        ['Velocidade por unidade', '0,0033-0,010 m/s', '0,2-0,6 m/s para 60 unidades, faixa de sensibilidade'],
        ['Constante de velocidade', '0,20-0,80 s', 'Nao identificada diretamente; hipotese de sensibilidade']])
    put('Em `antigo` nao se acrescenta lavagem; apenas varia-se seu ganho/subida/atraso como hipotese de contraste, portanto nao e a mesma configuracao nominal da tarefa 1. Os intervalos cobrem variabilidade plausivel, nao todas as combinacoes fisicas reais e nao sao uma distribuicao posterior inferida. A mudanca simultanea de condicoes impede atribuir diferencas numericas entre tarefas exclusivamente ao treino.')
    put()
    put(f'Ruido: bootstrap de **{len(cal["traces"])} trechos** estaveis com GPS, centrados por trecho, com selecao proporcional a duracao e inicio aleatorio, rotacionados por um rumo fixo por rodada. Posicao leste/norte e residuo de v_hor sao reamostrados juntos; avancam uma amostra por medida entregue, refletindo nas pontas em vez de criar salto de fronteira. Mantem quantizacao e correlacao local, mas a reflexao e uma convencao artificial, nao um modelo generativo comprovado para 60 s. Trechos reais sao poucos e reutilizados entre treino/prova: a independencia e de sementes simuladas, nao de novas sessoes reais.')
    put()
    put('Velocidade: derivada da posicao com filtro 0,6 anterior +0,4 derivada; a direcao vem dessa derivada, e a magnitude e a media entre sua norma e |v_hor|. A telemetria nao fornece direcao de movimento e yaw e rumo do nariz, nao rumo da velocidade. Na simulacao, v_hor sintetico e norma da velocidade fisica mais residuo observado. Essa fusao 50/50 e uma escolha explicita de engenharia, nao parametro identificado. Em repouso produz comandos por deriva de GPS; nao foi usado estado oculto como entrada da politica ou rotulo.')
    put()
    put('Offset de nivelamento: sorteado entre medianas reais por arquivo e somado apenas a roll_m/pitch_m. Nao atua como aceleracao gravitacional: um offset do sensor nao prova inclinacao fisica. Como a arquitetura obrigatoria recebe apenas posicao/velocidade, esse offset e um parametro nuisance nao observado pela rede e nao permite alegar robustez aprendida a nivelamento.')
    put()
    put('Duas condicoes fixadas antes da prova: **nominal**, agenda de medidas extraida dos intervalos entre linhas dos logs nao-teclado; **retencao**, agenda extraida dos intervalos entre mudancas de angulos/velocidades nos logs de teclado, incluindo as caudas longas. Entre entregas mantem-se toda a observacao anterior. O controle tenta a 10 Hz; a agenda e quantizada pelo passo de controle, sem adicionar atraso extra fixo. Na retencao, aplicar a espera do campo mais lento ao vetor inteiro e um estresse conservador, nao identificacao da perda de pacotes por campo. Os dois ambientes usam os mesmos trechos de ruido; a retencao tambem estica sua escala temporal. Nao ha garantia de extrapolacao para outros tipos de falha.')
    put()
    put('## Treino e prova')
    put('MLP da tarefa 1 **importada, nao modificada**: 22 -> 32 -> 32 -> 2, 1.858 parametros, tanh e saida continua 100*tanh. Cinco observacoes medidas (x,y,vx,vy), ordem temporal, mais comando anterior. Inicializacao repete a primeira observacao e comando zero. Professor PD kp=60, kd=15, limite original +/-60%; rede permite +/-100%. Adam, lote 512, taxa 0,001, ate 100 epocas, paciencia 10, melhoria minima 1e-7, melhor checkpoint da validacao em cada etapa. Normalizacao inicial congelada, piso 0,1. Nao houve dados humanos no treino nem rotulos de estado verdadeiro.')
    put()
    put('Uma clonagem mais tres DAgger puros: a politica anterior visita estados, PD rotula; agrega-se ao conjunto anterior. Ambas as condicoes e os tres modelos entram em todas as etapas. Inicializacao da rede 532019; embaralhamento 532020+etapa. Final escolhido como etapa 3 antes da prova, sem selecionar por resultado do teste. Validacao DAgger usa trajetorias da politica anterior, nunca agregadas ao treino; as perdas entre etapas nao sao do mesmo conjunto de entradas.')
    put()
    train = [load(f'treino_{i}.json') for i in range(4)]
    table(['Etapa', 'Sementes coleta por modelo/condicao', 'Sementes validacao', 'Amostras acumuladas', 'Validacao N', 'Epocas', 'MSE validacao pp^2'],
        [[r['etapa'],str(r['treino_sementes']),str(r['validacao_sementes']),r['total'],r['validacao'],r['epochs'],fmt(r['validation_mse_percent2'],5)] for r in train])
    put('Intervalos de sementes sao inclusivos; nao se sobrepoem a tarefa 1, entre treino/validacao/prova nem entre etapas. Numeros comuns entre modelos/condicoes sao intencionais para comparacao, nao replicas independentes. As contagens por modelo/condicao estao nos quatro JSONs de treino. O trecho medido e menor porque a rodada termina ao sair de 4 m.')
    put()
    put('Prova: **100 sementes ineditas 510000-510099 por modelo, condicao e controlador**, 1.200 rodadas no total. Horizonte 60 s; integracao 50 Hz, comando/historico 10 Hz mesmo quando a medida e retida. Perda: raio verdadeiro >4 m, com interrupcao. Erro medio usa raio verdadeiro a cada passo fisico ate termino e depois media entre rodadas; em perdas ha censura, nao sucesso por ter erro medio <4. Mesmas sementes entre PD/MLP, parametros e sensores separados da acao por RNG independente do sensor. Vento/deriva continuam hipoteses do Mundo original, nao medidos.')
    put()
    summaries = {}
    for key, rows in p['celulas'].items():
        summaries[key] = {k:float(np.mean([r[k] for r in rows])) for k in rows[0] if k != 'seed'}
    table(['Modelo/condicao', 'Ctrl', 'Erro medio m', 'Perdas/100', 'Duracao s', '>=95% %', '>=57% %', 'Variacao pp/passo', 'Medidas retidas %'],
        [[key.rsplit('/',1)[0],key.rsplit('/',1)[1],fmt(s['erro_m'],4),int(round(s['perdida']*100)),fmt(s['duracao_s'],2),fmt(s['saturado']*100,2),fmt(s['limite_pd']*100,2),fmt(s['suavidade'],3),fmt(s['retidas']*100,2)] for key,s in summaries.items()])
    put('>=95% e fracao dos passos com algum eixo perto do limite fisico, >=57% usa limiar comum perto do limite do professor. Variacao = media de (|delta_roll|+|delta_pitch|)/2 por passo, incluindo transicao desde zero. Sao medias por rodada, nao pooling de passos de rodadas com duracoes diferentes.')
    put()
    paired = []
    for model in ('velocidade','antigo','medido'):
        for cond in ('nominal','retencao'):
            pd = p['celulas'][model+'/'+cond+'/PD']
            mlp = p['celulas'][model+'/'+cond+'/MLP']
            delta = np.array([m['erro_m']-b['erro_m'] for m,b in zip(mlp,pd)])
            rng = np.random.default_rng(99117)
            ci = np.percentile(np.mean(rng.choice(delta,(2000,100)),axis=1),[2.5,97.5])
            paired.append([model+'/'+cond,fmt(float(delta.mean()),5),f'[{ci[0]:.5f}, {ci[1]:.5f}]',sum(m['perdida'] for m in mlp)-sum(b['perdida'] for b in pd)])
    table(['Modelo/condicao', 'Delta erro MLP-PD m', 'IC bootstrap pareado 95%', 'Delta perdas'],paired)
    put('ICs reamostram as 100 sementes, 2.000 vezes, semente 99117, condicionados ao simulador e aos dados reutilizados; nao quantificam risco no drone nem incerteza do modelo real. Pequenas diferencas numericas nao demonstram nova capacidade de controle. A rede so recebeu rotulos do PD, sem objetivo de melhorar perdas ou lidar com medidas velhas; nao se demonstrou vantagem consistente de robustez a retencao. Em medido, copiar o professor continua sem resolver o vento/deriva persistente. Zero perdas/100, quando ocorre, nao significa risco zero (limite aproximado da regra de tres ~3%, sob hipotese binomial idealizada).')
    put()
    put('## Replay aberto real')
    put('Reconstituicao causal a 10 Hz, exigindo GPS >=8 e posicao/yaw validos em trechos consecutivos classificados como repouso ou ar/pouso. Alvo e a primeira posicao do trecho; nao se afirma que era o alvo do piloto. Deriva leste/norte filtrada antes de girar para o corpo com yaw de cada amostra; isso evita atribuir rotacao do nariz a velocidade translacional. Mesma fusao de magnitude usada no ambiente. Historico reiniciado ao mudar para indeterminado/sem GPS. Nenhum comando influencia a proxima medida real.')
    put()
    put('**MLP** usa o proprio comando anterior hipotetico, como ocorreria no controle, mas sem fechar a malha fisica. **MLP_csv_anterior** e uma segunda verificacao teacher-forced com o comando de roll/pitch realmente registrado no passo anterior (1500 subtraido), quando disponivel; trechos sem esses campos ficam ausentes nessa variante, e o primeiro comando e zero. O PD nao depende do comando anterior. Os resultados nao devem ser tratados como previsao de trajetoria controlada.')
    put()
    stats, hazards = [], []
    for group in ('repouso','ar_pouso'):
        for ctrl in ('PD','MLP','MLP_csv_anterior'):
            arrays, satmax, limitmax, flips = [], 0., 0., 0
            for seg in replay['trechos']:
                commands = seg['comandos'][ctrl]
                chosen = np.array([c in ('parado','destravado') if group=='repouso' else c in ('ar','pousando') for c in seg['classes']])
                vals = np.array([v if v is not None else [np.nan,np.nan] for v in commands])
                chosen &= np.isfinite(vals).all(axis=1)
                if not chosen.any():
                    continue
                arrays.extend(vals[chosen].tolist())
                sat = chosen & (np.max(np.abs(vals),axis=1) >= 95)
                lim = chosen & (np.max(np.abs(vals),axis=1) >= 57)
                near = chosen[1:] & chosen[:-1]
                rapid = near & np.any((vals[1:]*vals[:-1] < 0) & (np.abs(vals[1:]) >= 30) & (np.abs(vals[:-1]) >=30),axis=1)
                satmax = max(satmax,streak(sat)); limitmax = max(limitmax,streak(lim))
                flips += int(rapid.sum())
                if streak(sat)>=1 or streak(lim)>=2 or rapid.any():
                    hazards.append(dict(grupo=group,controlador=ctrl,arquivo=seg['arquivo'],inicio=seg['inicio'],fim=seg['fim'],sat95_s=streak(sat),sat57_s=streak(lim),inversoes=int(rapid.sum())))
            v = np.array(arrays)
            if not len(v):
                continue
            q = np.percentile(v,[5,50,95])
            norm = np.max(np.abs(v),axis=1)
            stats.append(dict(grupo=group,controlador=ctrl,n=len(v),p5=float(q[0]),p50=float(q[1]),p95=float(q[2]),
                abs_medio=float(np.mean(np.abs(v))),sat95=float(np.mean(norm>=95)),sat57=float(np.mean(norm>=57)),
                abaixo5=float(np.mean(norm<5)),sat95_max_s=satmax,sat57_max_s=limitmax,inversoes=flips))
    table(['Trecho/ctrl','Passos','P5/mediana/P95 pp (eixos juntos)','|cmd| medio','Ambos <5%','>=95%','>=57%','Maior seq. >=95% / >=57% s','Inversoes rapidas'],
        [[r['grupo']+'/'+r['controlador'],r['n'],' / '.join(fmt(r[k],2) for k in ('p5','p50','p95')),fmt(r['abs_medio'],2),fmt(r['abaixo5']*100,2)+'%',fmt(r['sat95']*100,2)+'%',fmt(r['sat57']*100,2)+'%',fmt(r['sat95_max_s'],1)+' / '+fmt(r['sat57_max_s'],1),r['inversoes']] for r in stats])
    put('Inversao rapida: um mesmo eixo muda de sinal entre dois passos adjacentes de 0,1 s, ambos com modulo >=30 pp. Sinalizar risco: >=95% por >=1 s OU >=57% por >=2 s OU qualquer inversao rapida. Estes limiares sao alarmes offline conservadores, nao limites de voo certificados. A contagem de passos tem sobreposicao entre variantes e nao representa segundos independentes de voo.')
    put()
    table(['Grupo/ctrl','Arquivo','Inicio-fim s','Sequencia >=95% s','Sequencia >=57% s','Inversoes'],
        [[h['grupo']+'/'+h['controlador'],h['arquivo'],fmt(h['inicio'],1)+'-'+fmt(h['fim'],1),fmt(h['sat95_s'],1),fmt(h['sat57_s'],1),h['inversoes']] for h in hazards])
    if not hazards:
        put('Nenhum alarme pelos criterios acima nos trechos elegiveis. Isso nao exclui comandos perigosos fora da cobertura, erro de eixo ou de sinal.')
    put('No chao, o comportamento desejavel seria ~zero. Deriva aparente de GPS e erros do estimador podem induzir comandos nao nulos e ate saturacao perto do limite de 60% do professor: isso e um **problema de sanidade**, nao movimento real corrigido. A politica nao tem detector de solo nem vigia, nao recebe a qualidade/idade da medida nas 22 entradas e nao deve ser conectada diretamente ao drone. Comandos pequenos neste replay tampouco validariam controle em voo.')
    put()
    salvar = dict(resumo=stats, alarmes=hazards, prova_resumo=summaries)
    (OUT/'tabelas.json').write_text(json.dumps(salvar,indent=2))
    put('## Limites e recomendacao')
    put('- Nao ha pairado real sustentado, voo em malha fechada, teste de rejeicao de vento medido nem excitacao controlada e independente por eixo. Os poucos segundos no ar incluem subida, pouso e perda de controle.')
    put('- Bateria: a leitura 0-20 sob acelerador e queda de tensao/indicador sem unidade confirmada, nao carga restante. Nao foi usado esse campo como nivel de carga ou parametro dinamico. Faltam dados com bateria nova, carregada e tensao medida sob carga.')
    put('- Altura de telemetria nao e confiavel e nao entrou em nenhuma classificacao, ajuste, observacao ou metrica. Tambem nao ha altitude/yaw controlados, obstaculos, pouso seguro ou recuperacao de falhas neste ambiente horizontal.')
    put('- Os trechos estaveis de GPS sao amostra limitada e possivelmente selecionada; bootstrap reutiliza dados reais, nao aumenta a evidencia experimental. Ganhos, arrasto, vento e correspondencia dos eixos continuam incertos. A grade de parametros nao cobre todos os envelopes ajustados nem todas as falhas reais.')
    put('- Treino por imitacao nao corrige um professor que falha. Sem informacao explicita de idade/qualidade da medida, a arquitetura nao pode distinguir com certeza repouso, medida retida e GPS parado.')
    put()
    put('**Recomendacao: nao colocar o checkpoint no drone.** Primeiro, obter bateria nova/carregada e diagnostico eletrico; gravar por leitura um voo conduzido por pessoa com controle de radio, com trecho de repouso antes/depois, alvo conhecido, pairado e excitacoes pequenas por eixo, sob supervisao e condicoes seguras. Para identificar resposta ao manche, sincronizar tambem o comando do radio por instrumentacao passiva autorizada; telemetria sem comando nao resolve a identificacao. Confirmar sinais/eixos, atraso, atualizacao por campo, contato com o solo e resposta a vento antes de escolher a dinamica. Depois, validar professor/seguranca em simulacao e bancada, limites conservadores e interrupcao independente. Qualquer futuro voo precisaria de autorizacao especifica; este trabalho nao autoriza nenhum.')
    put()
    put('## Reproducao e artefatos')
    put('Todos os comandos abaixo partem da raiz do projeto e foram executados com timeout externo <=1.200.000 ms. Nao e necessario retreinar para reproduzir as tabelas. Use exclusivamente o interpretador indicado; -P evita shadowing e -B impede caches nos diretorios protegidos.')
    put()
    put('```bash')
    base = '/home/vascon1/.local/share/aruco-venv/bin/python -P -B '
    for cmd in ['ia/real/executa.py analise','ia/real/resposta_fit.py']+[f'ia/real/executa.py treino --etapa {i}' for i in range(4)]+['ia/real/executa.py prova','ia/real/executa.py replay','ia/real/executa.py verifica','ia/real/executa.py tabelas']:
        put(base+cmd)
    put('```')
    put()
    put('Para somente regenerar as tabelas e este documento: ultimo comando (`tabelas`). Treino retoma por etapa completa, validando hash do ambiente/calibracao; uma interrupcao perde a coleta/treino da etapa atual, nao as anteriores. Prova salva a cada 10 rodadas e rejeita checkpoint com pesos/ambiente/calibracao diferentes. Nao ha retomada no meio de epoca. O comando `snapshot` e apenas para registrar uma nova auditoria inicial, nao deve ser refeito para mascarar alteracoes entre execucoes.')
    put()
    put('- `analise.py`, `analise.json`: inventario, ACF, eventos e parametros descritivos; `calibracao.json`: trechos e intervalos usados pelo ambiente.')
    put('- `resposta_fit.py`, `ajuste_resposta.json`: grade e envelopes do ajuste angular; os criterios e todas as seis respostas principais estao preservados.')
    put('- `ambiente_real.py`, `executa.py`: ambiente herdado e pipeline com guardas de rede, GUI e escrita fora das entregas no processo principal.')
    put('- `dados_0.npz` a `dados_3.npz`, `pesos_0.npz` a `pesos_3.npz`, `treino_0.json` a `treino_3.json`: conjuntos agregados, pesos e curvas; validacoes sao regeneraveis pelas sementes.')
    put('- `prova.json`: todas as 1.200 rodadas com sementes e metricas. `replay.json`: todos os comandos por trecho/variante, classes e tempos; `tabelas.json`: resumos e alarmes. `relatorio.py`: gerador desta entrega.')
    put('- `fontes_antes.json`, `verificacao.json`: hashes, testes de determinismo, observacoes/rotulos, ausencia de mutacao global, arquitetura, guardas e cobertura das sementes; 12 rodadas recalculadas (uma por celula) devem ser identicas.')
    put()
    put('SHA-256 dos pesos finais: `'+train[-1]['pesos_sha256']+'`. SHA-256 da calibracao: `'+train[-1]['calibracao_sha256']+'`. Nenhum peso da tarefa 1 foi sobrescrito.')
    (ROOT/'docs/resultado_opencode_2.md').write_text('\n'.join(lines)+'\n')
    print('Relatorio e tabelas regenerados:', len(lines), 'linhas')
    print(json.dumps(stats,indent=2))
