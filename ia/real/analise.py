"""Analise offline dos CSVs sanitizados; nunca usa altura ou coordenadas globais."""
import csv
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'ia/real'
sys.path.insert(0, str(ROOT / 'ia'))
from modelo import np

CLASSES = ('parado', 'destravado', 'ar', 'pousando', 'indeterminado')


def numero(row, key):
    return float(row[key]) if row.get(key, '') != '' else float('nan')


def carregar():
    indice = json.loads((ROOT / 'ia/reais/INDICE.json').read_text())
    dados = []
    for nome, meta in indice.items():
        with (ROOT / 'ia/reais' / (nome + '.csv')).open() as f:
            rows = list(csv.DictReader(f))
        a = {k: np.array([numero(r, k) for r in rows]) for k in rows[0] if k != 'fase' and k != 'altura'}
        fases = np.array([r['fase'] for r in rows])
        t = a['t']
        dt = np.r_[np.diff(t), 0.]
        valid = np.isfinite(a['roll']) & np.isfinite(a['v_hor'])
        referencia = valid & ((a['estado'] == 0) | np.isin(fases, ['checagem', 'chao', 'recalibrar']))
        base = [float(np.median(a[k][referencia])) if referencia.any() else 0. for k in ('roll', 'pitch')]
        tilt = np.hypot(a['roll'] - base[0], a['pitch'] - base[1])
        quiet = (np.abs(a['v_vert']) <= .15) & (np.abs(a['v_hor']) <= .1) & (tilt <= 1.)
        c = np.full(len(t), 'indeterminado', dtype='<U16')
        c[valid & quiet & (a['estado'] == 0)] = 'parado'
        c[valid & quiet & (a['estado'] == 1)] = 'destravado'
        if nome.startswith('gravacao') or 'não saiu do chão' in meta['nota'] or 'não decolou' in meta['nota'] or 'não subiu' in meta['nota']:
            c[valid & quiet] = np.where(a['estado'][valid & quiet] == 0, 'parado', 'destravado')
        # Estado sozinho nao prova voo: exige movimento e inclinacao plausivel.
        movimento = (np.abs(a['v_vert']) >= .2) | ((np.abs(a['v_hor']) >= .2) & (tilt >= .5))
        ar = valid & movimento & (a['estado'] != 0) & (np.abs(a['roll']) < 35) & (np.abs(a['pitch']) < 35)
        if any(s in meta['nota'] for s in ('não decolou', 'não saiu do chão', 'não subiu', 'sem voar')):
            ar[:] = False
        c[ar] = 'ar'
        pouso = np.array(['pous' in f or 'desc' in f for f in fases])
        c[ar & (pouso | (a['v_vert'] <= -.2))] = 'pousando'
        known = np.all(np.isfinite(np.array([a[k] for k in ('roll_us', 'pitch_us', 'yaw_us', 'acel_us')])), axis=0)
        # As notas so localizam o comando na fase explicitamente nomeada.
        if nome in ('voofrente_20261120_151454', 'eixos_frente_20261120_182234'):
            known |= fases == 'frente'
        if nome == 'eixos_direita_20261120_210706':
            known |= fases == 'direita'
        # Repouso estrito: nao usar todos os trechos de baixa velocidade apos voo.
        repouso = valid & quiet & np.isin(c, ['parado', 'destravado']) & (
            np.isin(fases, ['checagem', 'chao', 'recalibrar', 'destravar']) | nome.startswith('gravacao'))
        dados.append(dict(nome=nome, meta=meta, a=a, fases=fases, c=c, dt=dt, known=known, repouso=repouso, base=base))
    return dados


def segmentos(mask):
    ids = np.flatnonzero(mask)
    return np.split(ids, np.flatnonzero(np.diff(ids) != 1) + 1) if len(ids) else []


def estat_segmentos(dados, key, gps=False):
    residuos, ranges, ac = [], [], [[] for _ in range(10)]
    for d in dados:
        a = d['a']
        mask = d['repouso'] & np.isfinite(a[key])
        if gps:
            mask &= a['satelites'] >= 8
        for ids in segmentos(mask):
            if len(ids) < 5 or a['t'][ids[-1]] - a['t'][ids[0]] < 1:
                continue
            ts, vs = a['t'][ids], a[key][ids]
            if key == 'yaw':
                vs = np.rad2deg(np.unwrap(np.deg2rad(vs)))
            # Grade causal de 10 Hz: nao inventa atualizacoes nos logs de 20 Hz.
            grid = np.arange(ts[0], ts[-1], .1)
            v = vs[np.searchsorted(ts, grid, side='right') - 1]
            r = v - np.mean(v)
            residuos.extend(r.tolist())
            ranges.append(float(np.ptp(v)))
            for lag in range(1, 11):
                if len(r) > lag + 3 and np.std(r[:-lag]) > 1e-8 and np.std(r[lag:]) > 1e-8:
                    ac[lag - 1].append(float(np.corrcoef(r[:-lag], r[lag:])[0, 1]))
    r = np.array(residuos)
    return dict(n=len(r), std=float(np.std(r)) if len(r) else None,
                amplitude_p95=float(np.percentile(np.abs(r), 95)) if len(r) else None,
                pico_a_pico_max=max(ranges, default=0.),
                acf=[float(np.median(x)) if x else None for x in ac],
                acf_segmentos=[len(x) for x in ac])


def respostas(dados):
    eventos = []
    for d in dados:
        a, fases, t = d['a'], d['fases'], d['a']['t']
        if d['nome'] in ('voofrente_20261120_151454', 'eixos_frente_20261120_182234', 'eixos_direita_20261120_210706'):
            fase = 'direita' if 'direita' in d['nome'] else 'frente'
            ids = np.flatnonzero(fases == fase)
            if len(ids):
                eventos.append(evento(d, ids[0], ids[-1], 60., 'roll' if fase == 'direita' else 'pitch', 'nota'))
        if d['nome'].startswith('piloto'):
            for key, eixo in [('roll_us', 'roll'), ('pitch_us', 'pitch')]:
                u = a[key] - 1500
                # Degrau de >=20 unidades, mantido >=0.3s; exclui alteracoes simultaneas.
                for i in range(1, len(t) - 2):
                    if not np.isfinite(u[i - 1:i + 1]).all() or abs(u[i] - u[i-1]) < 20:
                        continue
                    j = i
                    while j + 1 < len(t) and u[j + 1] == u[i] and t[j + 1] - t[i] < 2:
                        j += 1
                    if t[j] - t[i] >= .3 and np.any(np.isin(d['c'][i:j+1], ['ar', 'pousando'])):
                        eventos.append(evento(d, i, j, u[i] - u[i-1], eixo, 'csv'))
    return eventos


def evento(d, i, j, du, eixo, fonte):
    a, t = d['a'], d['a']['t']
    pre = (t >= t[i] - .5) & (t < t[i]) & np.isfinite(a[eixo])
    baseline = float(np.median(a[eixo][pre])) if pre.any() else d['base'][0 if eixo == 'roll' else 1]
    ids = np.arange(i, j+1)
    v = a[eixo][ids] - baseline
    pico = int(np.nanargmax(np.abs(v)))
    amp = float(v[pico])
    lim = max(.5, abs(amp) * .1)
    retorno = None
    for k in range(pico + 1, len(v) - 1):
        if np.all(np.abs(v[k:k+2]) <= lim):
            retorno = float(t[ids[k]] - t[i])
            break
    onset = np.flatnonzero(np.abs(v) >= max(.3, abs(amp)*.2))
    return dict(arquivo=d['nome'], eixo=eixo, fonte=fonte, inicio=float(t[i]), fim=float(t[j]),
                delta_cmd=float(du), pico_deg=amp, ganho_pico=abs(amp/du),
                pico_s=float(t[ids[pico]]-t[i]), atraso_aparente_s=float(t[ids[onset[0]]]-t[i]) if len(onset) else None,
                retorno_s=retorno, vh_max=float(np.nanmax(np.abs(a['v_hor'][ids]))),
                ar_s=float(d['dt'][ids][np.isin(d['c'][ids], ['ar', 'pousando'])].sum()),
                pre_pico_deg=float(np.ptp(a[eixo][pre])) if pre.any() else None)


def analisar():
    dados = carregar()
    inventario = []
    for d in dados:
        a, dt = d['a'], d['dt']
        gaps = np.diff(a['t'])
        fields = np.stack([a[k] for k in ['roll', 'pitch', 'yaw', 'v_hor', 'v_vert', 'leste_m', 'norte_m']], axis=1)
        iguais = np.all((fields[1:] == fields[:-1]) | (np.isnan(fields[1:]) & np.isnan(fields[:-1])), axis=1)
        repouso_pair = d['repouso'][1:] & d['repouso'][:-1]
        inventario.append(dict(arquivo=d['nome'], nota=d['meta']['nota'], linhas=len(dt),
            segundos={k:float(dt[d['c']==k].sum()) for k in CLASSES},
            comando_ar_s=float(dt[d['known'] & np.isin(d['c'], ['ar', 'pousando'])].sum()),
            repouso_s=float(dt[d['repouso']].sum()), base=d['base'],
            dt_mediana=float(np.median(gaps)), gaps_015=int(np.sum(gaps > .15)),
            gaps_repouso_015=int(np.sum((gaps > .15) & repouso_pair)),
            intervalos_repouso=int(np.sum(repouso_pair)),
            dt_repouso_max=float(max(gaps[repouso_pair], default=0.)),
            dt_max=float(max(gaps)), repetidas=float(np.mean(iguais))))
    ruido = {k:estat_segmentos(dados, k, k in ('leste_m', 'norte_m')) for k in ['roll', 'pitch', 'yaw', 'v_hor', 'leste_m', 'norte_m']}
    traces, intervalos, lentos = [], [], []
    for d in dados:
        a = d['a']
        mask = d['repouso'] & (a['satelites'] >= 8) & np.isfinite(a['leste_m']) & np.isfinite(a['norte_m'])
        for ids in segmentos(mask):
            ts = a['t'][ids]
            if len(ids) < 5 or ts[-1] - ts[0] < 2:
                continue
            grid = np.arange(ts[0], ts[-1], .1)
            ii = ids[np.searchsorted(ts, grid, side='right')-1]
            v = np.stack([a[k][ii] for k in ('leste_m', 'norte_m', 'v_hor')], axis=1)
            v -= v.mean(axis=0)
            traces.append(v.tolist())
        gaps = np.diff(a['t'])
        if not d['nome'].startswith('piloto'):
            intervalos.extend(gaps.tolist())
        else:
            vals = np.stack([a[k] for k in ('roll', 'pitch', 'yaw', 'v_hor', 'v_vert')], axis=1)
            change = np.r_[True, np.any(vals[1:] != vals[:-1], axis=1)] & np.all(np.isfinite(vals), axis=1)
            lentos.extend(np.diff(a['t'][change]).tolist())
    result = dict(inventario=inventario, ruido=ruido, respostas=respostas(dados))
    calibration = dict(traces=traces, intervalos=intervalos, intervalos_lentos=lentos,
        offsets=[d['base'] for d in dados if d['repouso'].sum() >= 10],
        dinamica=dict(atraso=[.0, .2], graus_por_unidade=[.05, .20], tau_subida=[.04, .18],
            tau_lavagem=[.10, .50], vel_por_unidade=[.0033, .010], tau_vel=[.2, .8]))
    (OUT / 'calibracao.json').write_text(json.dumps(calibration, allow_nan=False))
    (OUT / 'analise.json').write_text(json.dumps(result, indent=2, allow_nan=False))
    print(json.dumps(dict(segundos={k:sum(r['segundos'][k] for r in inventario) for k in CLASSES},
        comando_ar_s=sum(r['comando_ar_s'] for r in inventario), ruido=ruido,
        traces=len(traces), intervalos_lentos_percentis=np.percentile(lentos, [50, 95, 100]).tolist()), indent=2))
    return result


if __name__ == '__main__':
    analisar()
