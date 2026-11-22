"""Audita cobertura da prova e resume JSONs sem executar treino ou voo."""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from modelo import np
from ambiente import ROOT, MODELOS, humanos


def main():
    out = ROOT / "ia"
    baseline = json.loads((out / "prova.json").read_text())
    sha = hashlib.sha256((out / "pesos_3.npz").read_bytes()).hexdigest()
    assert baseline["config"]["sha256"] == sha
    assert baseline["config"]["n"] == 100
    assert baseline["config"]["seed"] == 90000
    assert len(baseline["celulas"]) == 6
    repeated = out / "prova_repetida.json"
    if repeated.exists():
        assert json.loads(repeated.read_text()) == baseline
    cells = {}
    for path in sorted(out.glob("robustez_*.json")):
        data = json.loads(path.read_text())
        assert data["config"] == baseline["config"]
        assert not cells.keys() & data["celulas"].keys()
        cells.update(data["celulas"])
    expected = {(m, c, round(d / 100, 2), round(r / 10, 1))
                for m in MODELOS for c in ("PD", "politica")
                for d in range(5, 51, 5) for r in range(1, 7)}
    observed = {(v["modelo"], v["controlador"], v["atraso"], v["ruido"])
                for v in cells.values()}
    assert observed == expected, (len(observed), len(expected))
    for cell in [*baseline["celulas"].values(), *cells.values()]:
        assert cell["n"] == len(cell["rodadas"]) == 100
        for metric in ("erro_m", "perdida", "saturado", "limite_pd", "suavidade", "duracao_s"):
            assert np.isclose(cell[metric], np.mean([r[metric] for r in cell["rodadas"]]))
    summary = {"python": sys.version.split()[0], "numpy": np.__version__,
               "sha256_pesos": sha, "celulas_nominais": 6, "celulas_robustez": len(cells),
               "rodadas_prova_total": 100 * (6 + len(cells)),
               "repeticao_nominal_identica": repeated.exists(), "humano": {}, "robustez": {}}
    for name, info in humanos()["modelos"].items():
        rounds = info["detalhes"]
        summary["humano"][name] = {"rodadas": info["rodadas"], "amostras": info["amostras"],
            "completas": info["completas"], "perdidas_observadas": sum(r["perdida_observada"] for r in rounds),
            **{k: float(np.mean([r[k] for r in rounds]))
               for k in ("erro_m", "saturado", "limite_pd", "suavidade", "duracao_s")}}
    for name in MODELOS:
        for controller in ("PD", "politica"):
            group = [v for v in cells.values() if v["modelo"] == name and v["controlador"] == controller]
            summary["robustez"][f"{name}/{controller}"] = {
                "erro_min_m": min(v["erro_m"] for v in group),
                "erro_max_m": max(v["erro_m"] for v in group),
                "perdas_min_pct": 100 * min(v["perdida"] for v in group),
                "perdas_max_pct": 100 * max(v["perdida"] for v in group),
                "duracao_min_s": min(v["duracao_s"] for v in group),
                "duracao_max_s": max(v["duracao_s"] for v in group),
                "pior_erro_celula": max(group, key=lambda v: v["erro_m"])}
    summary["fontes_sha256"] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [ROOT / "scripts/jogo_correcao.py", ROOT / "scripts/simula_controle.py",
                  ROOT / "predator/controle.py", *sorted(out.glob("*.py")),
                  *sorted((ROOT / "capturas").glob("jogo_*.csv"))]}
    (out / "resumo.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({**summary, "robustez": {
        k: {a: b for a, b in v.items() if a != "pior_erro_celula"}
        for k, v in summary["robustez"].items()}}, indent=2))


if __name__ == "__main__":
    main()
