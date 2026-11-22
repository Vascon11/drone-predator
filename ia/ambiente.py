"""Adaptador estritamente offline para o Mundo original, sem copiar a fisica."""
import csv
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from jogo_correcao import Mundo, DT, AMOSTRA
from predator.controle import PD, Ganhos
from modelo import np

MODELOS = ("velocidade", "antigo", "medido")
PROFESSOR = PD(Ganhos(kp=60, kd=15))  # Limite original: 60%, nao 100%.


def episodio(nome, seed, politica=None, ruido=.25, atraso=None, coletar=False):
    w = Mundo(nome, seed, ruido)
    # Copia local: nao altera MODELOS nem o mundo de outra rodada.
    w.m = dict(w.m)
    if atraso is not None:
        w.m["atraso"] = atraso
    w.ex.m = w.ey.m = w.m
    hist, anterior = None, np.zeros(2)
    xs, ys = [], []
    erro, sat, sat60, suave, medidas, passos = 0., 0, 0, 0., 0, 0
    for tick in range(3000):
        if tick % round(AMOSTRA / DT) == 0:
            w.medir(w.t)
            obs = [w.sx, w.sy, w.vsx, w.vsy]
            hist = [obs[:] for _ in range(5)] if hist is None else hist[1:] + [obs]
            entrada = np.concatenate((np.asarray(hist).ravel(), anterior))
            label = np.asarray(PROFESSOR.comando(*obs))
            cmd = label if politica is None else np.asarray(politica(entrada))
            if not np.isfinite(cmd).all() or np.max(np.abs(cmd)) > 100.000001:
                raise ValueError("Comando invalido")
            if coletar:
                xs.append(entrada)
                ys.append(label)
            sat += np.max(np.abs(cmd)) >= 95
            sat60 += np.max(np.abs(cmd)) >= 57
            suave += float(np.mean(np.abs(cmd - anterior)))
            anterior = cmd
            medidas += 1
        w.passo(float(cmd[0]), float(cmd[1]))
        erro += w.erro
        passos += 1
        if w.erro > 4:
            break
    metrics = {"erro_m": erro / passos, "perdida": int(w.erro > 4),
               "saturado": sat / medidas, "limite_pd": sat60 / medidas,
               "suavidade": suave / medidas, "duracao_s": passos * DT}
    return metrics, xs, ys


def humanos():
    groups = {}
    files = []
    for path in sorted((ROOT / "capturas").glob("jogo_*.csv")):
        if "_pd" in path.stem:
            continue
        files.append(path.name)
        with path.open() as f:
            for row in csv.DictReader(f):
                key = (path.name, row["rodada"], row["modelo"])
                groups.setdefault(key, []).append(row)
    summary = {"arquivos": files, "modelos": {}}
    for name in MODELOS:
        rounds = []
        for key, rows in groups.items():
            if key[2] != name:
                continue
            commands = np.array([[float(r["cmd_roll"]), float(r["cmd_pitch"])] for r in rows])
            times = np.array([float(r["t"]) for r in rows])
            errors = np.array([math.hypot(float(r["real_x"]), float(r["real_y"])) for r in rows])
            rounds.append({"arquivo": key[0], "rodada": key[1], "amostras": len(rows),
                           "duracao_s": float(times[-1] - times[0]),
                           "erro_m": float(errors.mean()), "perdida_observada": int(np.max(errors) > 4),
                           "completa": bool(times[-1] >= 59.8 or np.max(errors) > 4),
                           "saturado": float(np.mean(np.max(np.abs(commands), axis=1) >= 95)),
                           "limite_pd": float(np.mean(np.max(np.abs(commands), axis=1) >= 57)),
                           "suavidade": float(np.abs(np.diff(np.vstack((np.zeros((1, 2)), commands)), axis=0)).mean())})
        summary["modelos"][name] = {"rodadas": len(rounds),
            "amostras": sum(r["amostras"] for r in rounds),
            "completas": sum(r["completa"] for r in rounds), "detalhes": rounds}
    return summary
