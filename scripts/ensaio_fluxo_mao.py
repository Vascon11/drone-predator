"""Ensaio SEM VOAR: a voz guia você a mover o drone (travado, câmera para baixo) e o fluxo óptico do XS9 é comparado com o pedido.

Grava vídeo e telemetria (scripts/gravar_voo.py, só leitura), toca as frases da Thalita (scripts/voz/f_*.wav), registra os
horários em eventos.csv e roda scripts/analisa_fluxo.py com o venv do OpenCode no fim. O drone deve estar TRAVADO.
Uso: python3 -P scripts/ensaio_fluxo_mao.py [--sem-voz]
"""
import csv
import glob
import os
import subprocess
import sys
import time

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
VOZ = os.path.join(RAIZ, "scripts", "voz")
VENV_PY = os.path.expanduser("~/.local/share/aruco-venv/bin/python")
SEQUENCIA = ["direita", "esquerda", "frente", "tras", "sobe", "desce"]
JANELA_MOVER = 4.0   # s depois da frase para mover
JANELA_PARAR = 3.0   # s parado depois do movimento


def tocar(nome, sem_voz):
    arq = os.path.join(VOZ, f"{nome}.wav")
    if sem_voz or not os.path.exists(arq):
        print(f"[voz] {nome}")
        time.sleep(3)
        return
    subprocess.run(["paplay", arq], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)


def main():
    sem_voz = "--sem-voz" in sys.argv
    total = 2 + 6 + len(SEQUENCIA) * (3.5 + JANELA_MOVER + JANELA_PARAR) + 4
    rec = subprocess.Popen([sys.executable, "-P", os.path.join(RAIZ, "scripts", "gravar_voo.py"), str(int(total))],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(3)  # tempo do vídeo começar
    eventos = []
    tocar("f_prepare", sem_voz)
    time.sleep(3)
    for nome in SEQUENCIA:
        tocar(f"f_{nome}", sem_voz)
        t0 = time.time()
        time.sleep(JANELA_MOVER)
        eventos.append((t0, time.time(), nome))
        time.sleep(JANELA_PARAR)
    tocar("f_fim", sem_voz)
    saida = rec.communicate(timeout=total + 30)[0]
    print(saida.strip().splitlines()[-1] if saida.strip() else "sem saída do gravador")
    pastas = sorted(glob.glob(os.path.join(RAIZ, "capturas", "gravacao_*")), key=os.path.getmtime)
    pasta = pastas[-1]
    with open(os.path.join(pasta, "eventos.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_inicio", "t_fim", "nome"])
        for t0, t1, nome in eventos:
            w.writerow([f"{t0:.3f}", f"{t1:.3f}", nome])
    print(f"eventos em {pasta}/eventos.csv\n")
    subprocess.run([VENV_PY, "-P", os.path.join(RAIZ, "scripts", "analisa_fluxo.py"), pasta])


if __name__ == "__main__":
    main()
