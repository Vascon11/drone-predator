"""Procura a folha ArUco (DICT_4X4_100, marcadores de 4 cm, a mesma do XS9) no vídeo gravado do Predator. Só lê arquivo.

Grave antes com: python3 -P scripts/gravar_voo.py 10 --fotos   (câmera inclinada para baixo à mão, folha no chão).
Usa o venv do OpenCV: ~/.local/share/aruco-venv/bin/python scripts/ver_aruco.py [pasta da gravação] [--salvar]
Sem pasta, usa a gravação mais recente em capturas/gravacao_*. Mostra, por segundo, quantos marcadores aparecem e o tamanho em pixels.
"""
import glob
import os
import sys

import cv2
import numpy as np

LADO_M = 0.04
DICIONARIO = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100)


def pasta_alvo(args):
    pastas = [a for a in args if not a.startswith("--")]
    if pastas:
        return pastas[0]
    raiz = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "capturas", "gravacao_*")
    todas = sorted(glob.glob(raiz), key=os.path.getmtime)
    if not todas:
        sys.exit("nenhuma gravação em capturas/")
    return todas[-1]


def main():
    pasta = pasta_alvo(sys.argv[1:])
    video = os.path.join(pasta, "video.h264")
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        sys.exit(f"não abri {video}")
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    det = cv2.aruco.ArucoDetector(DICIONARIO, params)
    fps = cap.get(cv2.CAP_PROP_FPS) or 20.0
    n, com, por_seg, melhores, dim = 0, 0, {}, [], (0, 0)
    salvou = False
    while True:
        ok, quadro = cap.read()
        if not ok:
            break
        dim = (quadro.shape[1], quadro.shape[0])
        cinza = cv2.cvtColor(quadro, cv2.COLOR_BGR2GRAY)
        cantos, ids, _ = det.detectMarkers(cinza)
        seg = int(n / fps)
        achou = ids is not None and len(ids) > 0
        por_seg.setdefault(seg, []).append(len(ids) if achou else 0)
        if achou:
            com += 1
            lados = [np.mean([np.linalg.norm(c[0][i] - c[0][(i + 1) % 4]) for i in range(4)]) for c in cantos]
            melhores.append((len(ids), float(np.mean(lados))))
            if "--salvar" in sys.argv and not salvou:
                cv2.aruco.drawDetectedMarkers(quadro, cantos, ids)
                cv2.imwrite(os.path.join(pasta, "aruco_detectado.jpg"), quadro)
                salvou = True
        n += 1
    print(f"{pasta}\n{n} quadros ({dim[0]}x{dim[1]}), {com} com marcador "
          f"({100 * com / max(n, 1):.0f}%)")
    for s, v in sorted(por_seg.items()):
        print(f"  {s:>2} s: média {sum(v) / len(v):.1f} marcadores, máx {max(v)}")
    if melhores:
        px = [m[1] for m in melhores]
        print(f"lado médio do marcador: {np.mean(px):.0f} px (4 cm reais); máx de marcadores num quadro: {max(m[0] for m in melhores)}")
        print("Com a lente do Predator ainda não calibrada, a distância real só sai depois de medir uma vez a 30 cm.")
    else:
        print("Nenhum marcador encontrado: folha fora do campo, desfocada ou pequena demais; aproxime ou inclua mais luz.")


if __name__ == "__main__":
    main()
