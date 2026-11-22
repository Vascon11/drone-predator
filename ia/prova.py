"""Prova offline: 100 sementes ineditas por celula, checkpoint por controlador."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from modelo import MLP, np
from ambiente import ROOT, MODELOS, episodio


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pesos", default="ia/pesos_3.npz")
    ap.add_argument("--atraso", type=float, nargs="*", help="Grade: .05 .10 ... .50")
    ap.add_argument("--ruido", type=float, nargs="*", default=[.1, .2, .3, .4, .5, .6])
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=90000)
    ap.add_argument("--saida", default="ia/prova.json")
    a = ap.parse_args()
    weights, output = (ROOT / a.pesos).resolve(), (ROOT / a.saida).resolve()
    if not weights.is_relative_to(ROOT / "ia") or not output.is_relative_to(ROOT / "ia"):
        ap.error("Pesos e resultados devem ficar em ia/")
    if a.n < 1 or a.seed < 90000:
        ap.error("Use n positivo e sementes de prova >=90000")
    model = MLP.load(weights)
    fingerprint = hashlib.sha256(weights.read_bytes()).hexdigest()
    config = {"sha256": fingerprint, "n": a.n, "seed": a.seed, "duracao_s": 60,
              "saturacao_pct": 95, "limite_pd_pct": 57}
    if output.exists():
        result = json.loads(output.read_text())
        if result["config"] != config:
            ap.error("Checkpoint incompativel com pesos ou configuracao")
    else:
        result = {"config": config, "celulas": {}}
    conditions = [(None, .25)] if a.atraso is None else [(d, r) for d in a.atraso for r in a.ruido]
    for delay, noise in conditions:
        for name in MODELOS:
            for label, policy in (("PD", None), ("politica", model)):
                key = f"{name}/{label}/atraso={delay}/ruido={noise}"
                if key not in result["celulas"]:
                    rounds = [episodio(name, s, policy, noise, delay)[0]
                              for s in range(a.seed, a.seed + a.n)]
                    result["celulas"][key] = {"modelo": name, "controlador": label,
                        "atraso": delay, "ruido": noise, "n": a.n,
                        **{k: float(np.mean([r[k] for r in rounds])) for k in rounds[0]},
                        "rodadas": rounds}
                    output.write_text(json.dumps(result, indent=2) + "\n")
                cell = result["celulas"][key]
                print(f"{key}: erro={cell['erro_m']:.4f}m perdidas={100*cell['perdida']:.1f}% "
                      f"sat={100*cell['saturado']:.2f}% sat60={100*cell['limite_pd']:.2f}% "
                      f"variacao={cell['suavidade']:.3f}", flush=True)


if __name__ == "__main__":
    main()
