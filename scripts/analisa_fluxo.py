"""Roda o fluxo óptico do XS9 (xs9/fluxo.py) no vídeo do Predator e compara com os movimentos pedidos por voz. Só lê arquivo.

Uso (venv do OpenCV): ~/.local/share/aruco-venv/bin/python -P scripts/analisa_fluxo.py <pasta da gravação>
A pasta precisa de video.h264, quadros.csv e eventos.csv (t_inicio, t_fim, nome), feitos por scripts/ensaio_fluxo_mao.py.
"""
import csv
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, "/home/vascon1/Documentos/drone/xs9")
from xs9 import fluxo  # noqa: E402

LARG = 640  # o fluxo do XS9 foi feito para 640x480; reduz o 1280x720 do Predator


def main():
    if len(sys.argv) < 2:
        sys.exit("uso: analisa_fluxo.py <pasta>")
    pasta = sys.argv[1]
    tempos = [float(r["t"]) for r in csv.DictReader(open(os.path.join(pasta, "quadros.csv")))]
    eventos = [(float(r["t_inicio"]), float(r["t_fim"]), r["nome"]) for r in csv.DictReader(open(os.path.join(pasta, "eventos.csv")))]
    cap = cv2.VideoCapture(os.path.join(pasta, "video.h264"))
    if not cap.isOpened():
        sys.exit("não abri o vídeo")
    ant, i, passos = None, 0, []  # (t, dx, dy, escala, valido)
    fator = None
    while True:
        ok, q = cap.read()
        if not ok:
            break
        cinza = cv2.cvtColor(q, cv2.COLOR_BGR2GRAY)
        fator = LARG / cinza.shape[1]
        cinza = cv2.resize(cinza, (LARG, int(cinza.shape[0] * fator)))
        t = tempos[i] if i < len(tempos) else tempos[-1]
        if ant is not None:
            m = fluxo.movimento(ant, cinza)
            passos.append((t, m["dx"] if m else 0.0, m["dy"] if m else 0.0, m["escala"] if m else 1.0, m is not None))
        ant, i = cinza, i + 1
    print(f"{i} quadros de vídeo, {len(tempos)} em quadros.csv; fluxo válido em "
          f"{100 * sum(p[4] for p in passos) / max(len(passos), 1):.0f}% dos pares")
    if i != len(tempos):
        print("AVISO: contagem de quadros diferente do quadros.csv; o alinhamento por tempo pode errar um pouco")
    print("\nMovimento pedido  -> deslocamento acumulado do chão na imagem (px a 640 de largura)")
    resultado = {}
    for t0, t1, nome in eventos:
        seg = [p for p in passos if t0 <= p[0] <= t1]
        if not seg:
            continue
        dx, dy = sum(p[1] for p in seg), sum(p[2] for p in seg)
        esc = float(np.prod([p[3] for p in seg]))
        val = 100 * sum(p[4] for p in seg) / len(seg)
        resultado[nome] = (dx, dy, esc)
        print(f"  {nome:<9} dx {dx:+7.1f}  dy {dy:+7.1f}  escala {esc:5.3f}  (válido {val:.0f}%)")
    if len(resultado) < 4:
        return
    print("\nLeitura:")
    for a, b, eixo in (("direita", "esquerda", 0), ("frente", "tras", 1)):
        if a in resultado and b in resultado:
            va, vb = resultado[a][eixo], resultado[b][eixo]
            print(f"- {a}/{b}: eixo {'x' if eixo == 0 else 'y'} da imagem, {va:+.0f} e {vb:+.0f} px: "
                  f"{'sinais opostos (coerente)' if va * vb < 0 else 'MESMO sinal: algo está errado'}")
    d, f = resultado.get("direita"), resultado.get("frente")
    if d and f:
        eixo_d = "x" if abs(d[0]) >= abs(d[1]) else "y"
        eixo_f = "x" if abs(f[0]) >= abs(f[1]) else "y"
        print(f"- 'direita' mexe principalmente no eixo {eixo_d} e 'frente' no eixo {eixo_f} da imagem "
              f"({'montagem alinhada com o drone' if eixo_d != eixo_f else 'eixos NÃO separados: a imagem pode estar girada'}).")
        print(f"- sinal: ao ir para a direita o chão anda {'+' if d[0] >= 0 else '-'} em x; ao ir para a frente anda {'+' if f[1] >= 0 else '-'} em y.")
    s, de = resultado.get("sobe"), resultado.get("desce")
    if s and de:
        print(f"- escala subindo {s[2]:.3f} e descendo {de[2]:.3f} (esperado: abaixo e acima de 1, em sentidos opostos).")


if __name__ == "__main__":
    main()
