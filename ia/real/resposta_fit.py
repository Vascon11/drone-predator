"""Ajustes descritivos de transitorios, nao identificacao causal de voo."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analise import np, carregar


def ajustar():
    result = []
    for d in carregar():
        if d['nome'] not in ('eixos_frente_20261120_182234', 'voofrente_20261120_151454', 'eixos_direita_20261120_210706'):
            continue
        fase = 'direita' if 'direita' in d['nome'] else 'frente'
        ids = np.flatnonzero(d['fases'] == fase)
        a = d['a']
        t = a['t'][ids] - a['t'][ids[0]]
        # Janela fixa de 0.8 s: evita ajustar o pouso ao degrau inicial.
        take = t <= .81
        ts = t[take]
        for eixo in ('roll', 'pitch'):
            baseline = d['base'][0 if eixo == 'roll' else 1]
            v = a[eixo][ids][take] - baseline
            fits = []
            for delay in np.arange(-.1, .201, .05):
                tt = np.maximum(0, ts-delay)
                for rise in (.04, .06, .08, .10, .14, .18, .25):
                    for wash in (.08, .10, .14, .20, .30, .45, .60, None):
                        if wash == rise:
                            shape = tt/rise*np.exp(-tt/rise)
                        elif wash is None:
                            shape = 1-np.exp(-tt/rise)
                        else:
                            shape = wash/(wash-rise)*(np.exp(-tt/wash)-np.exp(-tt/rise))
                        # Primeiro angulo e perturbacao ja presente na decolagem.
                        initial = np.exp(-ts/rise)
                        design = np.stack([60*shape, initial], axis=1)
                        coef = np.linalg.lstsq(design, v, rcond=None)[0]
                        rmse = float(np.sqrt(np.mean((design@coef-v)**2)))
                        fits.append(dict(atraso=round(float(delay), 3), subida=rise, lavagem=wash,
                            ganho=abs(float(coef[0])), inicial_deg=float(coef[1]), rmse=rmse))
            lavado = sorted((f for f in fits if f['lavagem'] is not None), key=lambda f:f['rmse'])
            antigo = min((f for f in fits if f['lavagem'] is None), key=lambda f:f['rmse'])
            plausible = [f for f in lavado if f['rmse'] <= lavado[0]['rmse']+.5 and f['ganho'] <= .5]
            result.append(dict(arquivo=d['nome'], eixo=eixo, n=len(ts),
                melhor_lavagem=lavado[0], melhor_mantido=antigo,
                envelope={k:[min(f[k] for f in plausible), max(f[k] for f in plausible)] for k in ('atraso','subida','lavagem','ganho')}))
    path = Path(__file__).resolve().parent / 'ajuste_resposta.json'
    path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    ajustar()
