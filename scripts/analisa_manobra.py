"""Para onde o drone foi em cada tecla de movimento (W/S/A/D), pelo GPS, no referencial do nariz.

Lê capturas/piloto_*/dados.csv (piloto, roteiro --manobra ou tecla G). Para cada trecho com uma única tecla de
movimento segurada, mede o deslocamento do início do trecho até `--depois` segundos após soltar (o drone tem atraso
e inércia) e projeta no rumo do nariz (yaw da telemetria) do início do trecho: frente (+) / trás (−), direita (+) / esquerda (−).
O GPS erra 0,3–4 m parado: deslocamentos abaixo de ~1 m não provam nada, olhe o sinal de vários trechos juntos.
Uso: python3 -P scripts/analisa_manobra.py [pasta ou dados.csv] [--depois 1.5]
"""
import argparse
import csv
import glob
import math
import os

ESPERADO = {"w": "frente", "s": "trás", "d": "direita", "a": "esquerda"}
M_POR_GRAU = 111320.0


def ler(caminho):
    if os.path.isdir(caminho):
        caminho = os.path.join(caminho, "dados.csv")
    return list(csv.DictReader(open(caminho)))


def trechos(linhas):
    """[(tecla, i_ini, i_fim)] com uma só tecla de movimento segurada, no ar."""
    out, atual, ini = [], None, None
    for i, x in enumerate(linhas):
        mov = x["teclas"].replace("e", "").replace("q", "")  # subir/descer junto não atrapalha a leitura horizontal
        k = mov if x["fase"] == "voando" and mov in ESPERADO else None
        if k != atual:
            if atual:
                out.append((atual, ini, i - 1))
            atual, ini = k, i
    if atual:
        out.append((atual, ini, len(linhas) - 1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("caminho", nargs="?", default=None)
    ap.add_argument("--depois", type=float, default=1.5)
    ap.add_argument("--min-dur", type=float, default=0.3, help="ignora toques mais curtos que isso (s)")
    a = ap.parse_args()
    caminho = a.caminho or sorted(glob.glob("capturas/piloto_*"))[-1]
    L = ler(caminho)
    t = [float(x["t"]) for x in L]
    print(f"{caminho}: {len(L)} linhas")
    print(f"{'tecla':6} {'dur':>5} {'frente':>7} {'direita':>8} {'dist':>5}  {'inclinação máx (roll/pitch)':>28}  resultado")
    resumo = {}
    for k, i0, i1 in trechos(L):
        dur = t[i1] - t[i0]
        if dur < a.min_dur:
            continue
        j = i1
        while j + 1 < len(L) and t[j + 1] <= t[i1] + a.depois:
            j += 1
        x0, x1 = L[i0], L[j]
        lat0, lon0 = float(x0["lat"]), float(x0["lon"])
        dn = (float(x1["lat"]) - lat0) * M_POR_GRAU
        de = (float(x1["lon"]) - lon0) * M_POR_GRAU * math.cos(math.radians(lat0))
        r = math.radians(float(x0["yaw"]))
        frente = dn * math.cos(r) + de * math.sin(r)
        direita = -dn * math.sin(r) + de * math.cos(r)
        trecho = L[i0:j + 1]
        rmax = max((float(x["roll"]) for x in trecho), key=abs)
        pmax = max((float(x["pitch"]) for x in trecho), key=abs)
        dist = math.hypot(frente, direita)
        eixo = {"w": frente, "s": -frente, "d": direita, "a": -direita}[k]
        lateral = abs(direita) if k in "ws" else abs(frente)
        if dist < 0.5:
            res = "andou pouco (dentro do erro do GPS)"
        elif eixo > 0 and lateral < eixo:
            res = f"OK: foi para {ESPERADO[k]}"
        else:
            sentido = ("frente" if frente > 0 else "trás") if abs(frente) >= abs(direita) else ("direita" if direita > 0 else "esquerda")
            res = f"ERRADO: esperava {ESPERADO[k]}, foi para {sentido}"
        resumo.setdefault(k, []).append(res.split(":")[0])
        print(f"{k.upper():6} {dur:5.1f} {frente:+7.2f} {direita:+8.2f} {dist:5.2f}  {rmax:+12.1f}° / {pmax:+6.1f}°        {res}")
    if not resumo:
        print("nenhum trecho com W/A/S/D no ar")
        return
    print("\nresumo:", {k.upper(): v for k, v in resumo.items()})
    print("roll + = asa direita para baixo; pitch − = nariz para baixo (convenção vista em 20/11)")


if __name__ == "__main__":
    main()
