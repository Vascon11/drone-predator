"""Clonagem PD + tres iteracoes DAgger, CPU, retomavel por etapa."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from modelo import MLP, np
from ambiente import ROOT, MODELOS, episodio, humanos

OUT = ROOT / "ia"


def dataset(seed, n, politica=None):
    xs, ys, counts = [], [], {}
    for nome in MODELOS:
        count = 0
        for s in range(seed, seed + n):
            _, x, y = episodio(nome, s, politica, coletar=True)
            xs.extend(x)
            ys.extend(y)
            count += len(x)
        counts[nome] = count
    return np.array(xs), np.array(ys), counts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--etapa", type=int, required=True, choices=range(4))
    args = ap.parse_args()
    human = humanos()
    (OUT / "humanos.json").write_text(json.dumps(human, indent=2) + "\n")
    if args.etapa == 0:
        # Decisao pre-treino: >=10 rodadas completas/modelo para segundo professor.
        print("Dados humanos:", {k: {a: v[a] for a in ("rodadas", "amostras", "completas")}
                                  for k, v in human["modelos"].items()}, flush=True)
        if any(v["completas"] >= 10 for v in human["modelos"].values()):
            raise RuntimeError("Reavaliar inclusao humana: limiar de dados atingido")
        x, y, counts = dataset(10000, 50)
        xv, yv, val_counts = dataset(20000, 12)
        model = MLP()
        model.mean = x.mean(axis=0)
        model.std = np.maximum(x.std(axis=0), .1)
        np.savez(OUT / "validacao.npz", x=xv, y=yv)
        metadata = {"etapa": 0, "treino_sementes": [10000, 10049],
                    "validacao_sementes": [20000, 20011], "contagens": counts,
                    "validacao_contagens": val_counts}
    else:
        prev = args.etapa - 1
        model = MLP.load(OUT / f"pesos_{prev}.npz")
        with np.load(OUT / f"dados_{prev}.npz") as z:
            x, y = z["x"], z["y"]
        first = 10000 + 1000 * args.etapa
        xn, yn, counts = dataset(first, 25, model)
        x, y = np.concatenate((x, xn)), np.concatenate((y, yn))
        # Validacao on-policy em sementes disjuntas, nunca agregada ao treino.
        xv, yv, val_counts = dataset(20000, 12, model)
        metadata = {"etapa": args.etapa, "dagger_sementes": [first, first + 24],
                    "contagens_novas": counts, "validacao_contagens": val_counts}
    fit = model.fit(x, y, xv, yv, seed=42 + args.etapa)
    model.save(OUT / f"pesos_{args.etapa}.npz")
    np.savez(OUT / f"dados_{args.etapa}.npz", x=x, y=y)
    metadata.update(fit)
    metadata["amostras_acumuladas"] = len(x)
    metadata["arquitetura"] = [22, 32, 32, 2]
    (OUT / f"treino_{args.etapa}.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps({k: v for k, v in metadata.items() if k != "trace"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
