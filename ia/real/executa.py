"""Pipeline CPU retomavel: analise, treino, prova, replay e tabelas."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'ia/real'


def guarda(event, args):
    if event.startswith(('socket.', 'subprocess.', 'os.system')):
        raise RuntimeError('Rede/processos proibidos no pipeline offline')
    if event == 'import' and args[0].split('.')[0] in ('tkinter', 'cv2'):
        raise RuntimeError('GUI proibida')
    if event == 'open':
        path, mode, flags = args
        writing = (isinstance(mode, str) and any(k in mode for k in 'wax+')) or (flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT))
        if writing and not isinstance(path, int):
            p = Path(path).resolve()
            if not p.is_relative_to(OUT) and p != ROOT / 'docs/resultado_opencode_2.md':
                raise RuntimeError('Escrita fora das entregas: ' + str(p))


sys.addaudithook(guarda)
sys.path.insert(0, str(OUT))
from analise import np, carregar, analisar, segmentos


def salvar(nome, data):
    path = OUT / nome
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, allow_nan=False))
    tmp.replace(path)


def hashfile(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def treino(etapa):
    from ambiente_real import episodio, MODELOS, CONDICOES
    from modelo import MLP
    dest = OUT / f'pesos_{etapa}.npz'
    signature = [hashfile(OUT / p) for p in ('calibracao.json', 'ambiente_real.py')]
    if dest.exists() and (OUT / f'treino_{etapa}.json').exists():
        old = json.loads((OUT / f'treino_{etapa}.json').read_text())
        if old.get('signature') == signature:
            print('Etapa concluida:', etapa)
            return
    politica = None if etapa == 0 else MLP.load(OUT / f'pesos_{etapa-1}.npz')
    # Novos intervalos, sem intersecao com os da tarefa 1 ou entre etapas.
    inicio, quantidade = 310000 + 1000*etapa, 24 if etapa == 0 else 12
    xs, ys, xv, yv, contagem = [], [], [], [], {}
    for nome in MODELOS:
        for cond in CONDICOES:
            n = 0
            for seed in range(inicio, inicio+quantidade):
                _, x, y = episodio(nome, seed, politica, cond, True)
                xs.extend(x); ys.extend(y); n += len(x)
            contagem[nome+'/'+cond] = n
            for seed in range(410000 + etapa*1000, 410004 + etapa*1000):
                _, x, y = episodio(nome, seed, politica, cond, True)
                xv.extend(x); yv.extend(y)
    x, y, xv, yv = map(np.asarray, (xs, ys, xv, yv))
    if etapa:
        with np.load(OUT / f'dados_{etapa-1}.npz', allow_pickle=False) as old:
            x, y = np.concatenate((old['x'], x)), np.concatenate((old['y'], y))
    model = MLP(532019) if etapa == 0 else MLP.load(OUT / f'pesos_{etapa-1}.npz')
    if etapa == 0:
        model.mean, model.std = x.mean(axis=0), np.maximum(x.std(axis=0), .1)
    result = model.fit(x, y, xv, yv, epochs=100, patience=10, seed=532020+etapa)
    np.savez(OUT / f'dados_{etapa}.npz', x=x, y=y)
    model.save(dest)
    result.update(etapa=etapa, contagem=contagem, total=len(x), validacao=len(xv),
        treino_sementes=[inicio, inicio+quantidade-1], validacao_sementes=[410000+etapa*1000, 410003+etapa*1000],
        pesos_sha256=hashfile(dest), calibracao_sha256=hashfile(OUT / 'calibracao.json'), signature=signature)
    salvar(f'treino_{etapa}.json', result)
    print(json.dumps({k:v for k,v in result.items() if k != 'trace'}, indent=2))


def prova():
    from ambiente_real import episodio, MODELOS, CONDICOES
    from modelo import MLP
    model = MLP.load(OUT / 'pesos_3.npz')
    signature = [hashfile(OUT / p) for p in ('pesos_3.npz', 'calibracao.json', 'ambiente_real.py')]
    path = OUT / 'prova.json'
    data = json.loads(path.read_text()) if path.exists() else dict(signature=signature, celulas={})
    if data['signature'] != signature:
        raise ValueError('Checkpoint da prova pertence a outro experimento')
    for nome in MODELOS:
        for cond in CONDICOES:
            for ctrl, pol in [('PD', None), ('MLP', model)]:
                key = '/'.join((nome, cond, ctrl))
                rows = data['celulas'].setdefault(key, [])
                for seed in range(510000+len(rows), 510100):
                    m, _, _ = episodio(nome, seed, pol, cond)
                    rows.append(dict(seed=seed, **m))
                    if len(rows) % 10 == 0:
                        salvar('prova.json', data)
                print(key, len(rows), round(np.mean([r['erro_m'] for r in rows]), 4), sum(r['perdida'] for r in rows), flush=True)
    salvar('prova.json', data)


def replay():
    from ambiente_real import fundir, PROFESSOR
    from modelo import MLP
    from predator.controle import posicao_corpo
    model = MLP.load(OUT / 'pesos_3.npz')
    results = []
    for d in carregar():
        a = d['a']
        mask = np.isin(d['c'], ['parado', 'destravado', 'ar', 'pousando']) & np.isfinite(a['leste_m']) & np.isfinite(a['norte_m']) & np.isfinite(a['yaw']) & (a['satelites'] >= 8)
        for ids in segmentos(mask):
            if len(ids) < 3 or a['t'][ids[-1]] - a['t'][ids[0]] < .4:
                continue
            # Reseta alvo/historico em cada trecho, nao segue posicao futura.
            grid = np.arange(a['t'][ids[0]], a['t'][ids[-1]], .1)
            ii = ids[np.searchsorted(a['t'][ids], grid, side='right')-1]
            e0, n0 = a['leste_m'][ii[0]], a['norte_m'][ii[0]]
            ve = vn = 0.
            hist = None
            last = None
            cmds = {'PD': [], 'MLP': [], 'MLP_csv_anterior': []}
            anterior = np.zeros(2)
            for k, i in enumerate(ii):
                e, n = a['leste_m'][i], a['norte_m'][i]
                if last is not None:
                    ve, vn = .6*ve + .4*(e-last[0])/.1, .6*vn + .4*(n-last[1])/.1
                last = e, n
                vx, vy = fundir(ve, vn, a['v_hor'][i])
                x, y = posicao_corpo(n-n0, e-e0, a['yaw'][i])
                vx, vy = posicao_corpo(vy, vx, a['yaw'][i])
                obs = [x, y, vx, vy]
                hist = [obs[:] for _ in range(5)] if hist is None else hist[1:] + [obs]
                features = np.asarray(hist).ravel()
                cmd = model(np.r_[features, anterior])
                cmds['MLP'].append(cmd.tolist())
                cmds['PD'].append(list(PROFESSOR.comando(*obs)))
                # Variante teacher-forced: comando realmente registrado no passo anterior.
                j = ii[max(0, k-1)]
                real = np.array([a['roll_us'][j]-1500, a['pitch_us'][j]-1500])
                if k == 0:
                    real[:] = 0
                cmds['MLP_csv_anterior'].append(model(np.r_[features, real]).tolist() if np.isfinite(real).all() else None)
                anterior = cmd
            results.append(dict(arquivo=d['nome'], inicio=float(grid[0]), fim=float(grid[-1]),
                classes=d['c'][ii].tolist(), comandos=cmds))
    salvar('replay.json', dict(trechos=results, pesos_sha256=hashfile(OUT / 'pesos_3.npz')))
    print('Replay:', len(results), 'trechos')


def tabelas():
    from relatorio import gerar
    gerar()


def verificar():
    from ambiente_real import MundoReal, episodio, CAL
    from modelo import MLP
    from simula_controle import MODELOS
    original = json.dumps(MODELOS, sort_keys=True)
    for cond in ('nominal', 'retencao'):
        one = episodio('medido', 610001, condicao=cond, coletar=True)
        two = episodio('medido', 610001, condicao=cond, coletar=True)
        assert one[0] == two[0] and np.array_equal(one[1], two[1])
        assert np.asarray(one[1]).shape[1] == 22
        x, y = np.array(one[1]), np.array(one[2])
        assert np.allclose(y, np.clip(-60*x[:,16:18]-15*x[:,18:20], -60, 60))
        assert np.all(x[0,-2:] == 0)
        assert np.allclose(x[0,:4], x[0,16:20])
        w = MundoReal('medido', 1, cond)
        assert CAL['dinamica']['atraso'][0] <= w.m['atraso'] <= CAL['dinamica']['atraso'][1]
    assert original == json.dumps(MODELOS, sort_keys=True)
    policy = MLP.load(OUT / 'pesos_3.npz')
    assert sum(p.size for p in policy.params.values()) == 1858
    assert np.isfinite(policy(np.zeros(22))).all()
    for etapa in range(4):
        meta = json.loads((OUT / f'treino_{etapa}.json').read_text())
        assert meta['pesos_sha256'] == hashfile(OUT / f'pesos_{etapa}.npz')
        assert meta['signature'] == [hashfile(OUT / name) for name in ('calibracao.json', 'ambiente_real.py')]
        assert meta['treino_sementes'][1] < meta['validacao_sementes'][0] < 510000
        with np.load(OUT / f'dados_{etapa}.npz', allow_pickle=False) as data:
            assert len(data['x']) == meta['total'] and data['x'].shape[1] == 22
            assert data['y'].shape == (meta['total'], 2)
            assert np.isfinite(data['x']).all() and np.isfinite(data['y']).all()
            assert np.allclose(data['y'], np.clip(-60*data['x'][:,16:18]-15*data['x'][:,18:20], -60,60))
    p = json.loads((OUT / 'prova.json').read_text())
    assert len(p['celulas']) == 12
    for rows in p['celulas'].values():
        assert [r['seed'] for r in rows] == list(range(510000, 510100))
    rep = json.loads((OUT / 'replay.json').read_text())
    assert rep['pesos_sha256'] == hashfile(OUT / 'pesos_3.npz')
    for seg in rep['trechos']:
        for ctrl, cmds in seg['comandos'].items():
            assert len(cmds) == len(seg['classes'])
            valid = np.array([c for c in cmds if c is not None])
            assert np.isfinite(valid).all() and np.max(np.abs(valid), initial=0) <= 100
    import re
    report = ROOT/'docs/resultado_opencode_2.md'
    if report.exists():
        width = None
        for line in report.read_text().splitlines():
            if line.startswith('|'):
                count = len(re.split(r'(?<!\\)\|', line))
                if width is None:
                    width = count
                assert count == width, line
            else:
                width = None
    for event, args in [('socket.connect', ()), ('open', (str(ROOT/'ia/proibido'), 'w', os.O_WRONLY))]:
        try:
            guarda(event, args)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Guarda inativa')
    # Recalculo de uma rodada por celula, com pesos congelados.
    for key, rows in p['celulas'].items():
        nome, cond, ctrl = key.split('/')
        m, _, _ = episodio(nome, 510000, None if ctrl == 'PD' else policy, cond)
        assert all(m[k] == rows[0][k] for k in m)
    files = [ROOT/'ia/modelo.py', ROOT/'ia/ambiente.py', ROOT/'ia/treina.py', ROOT/'ia/prova.py', ROOT/'scripts/jogo_correcao.py', ROOT/'scripts/simula_controle.py', ROOT/'predator/controle.py']
    files += sorted((ROOT/'ia/reais').glob('*.csv')) + [ROOT/'ia/reais/INDICE.json']
    hashes = {str(f.relative_to(ROOT)):hashfile(f) for f in files}
    before = OUT/'fontes_antes.json'
    if before.exists():
        assert hashes == json.loads(before.read_text())
    salvar('verificacao.json', dict(testes='ok', celulas=12, rodadas=1200, repetidas=12, hashes=hashes))
    print('Verificacoes offline OK; 12 rodadas repetidas identicas')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('acao', choices=['analise', 'treino', 'prova', 'replay', 'tabelas', 'verifica', 'snapshot'])
    parser.add_argument('--etapa', type=int, choices=range(4), default=0)
    args = parser.parse_args()
    if args.acao == 'analise':
        analisar()
    elif args.acao == 'treino':
        treino(args.etapa)
    elif args.acao == 'prova':
        prova()
    elif args.acao == 'replay':
        replay()
    elif args.acao == 'tabelas':
        tabelas()
    elif args.acao == 'verifica':
        verificar()
    elif args.acao == 'snapshot':
        files = [ROOT/p for p in ['ia/modelo.py','ia/ambiente.py','ia/treina.py','ia/prova.py','scripts/jogo_correcao.py','scripts/simula_controle.py','predator/controle.py']]
        files += sorted((ROOT/'ia/reais').glob('*.csv')) + [ROOT/'ia/reais/INDICE.json']
        salvar('fontes_antes.json', {str(f.relative_to(ROOT)):hashfile(f) for f in files})
