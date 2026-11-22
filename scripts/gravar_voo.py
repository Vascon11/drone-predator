"""Grava vídeo (TCP 7060) e telemetria (UDP 50000) ao mesmo tempo, com o mesmo relógio. SÓ LEITURA.

Nenhum comando de voo sai por aqui: o UDP só manda o pedido de telemetria (lista fechada) e o TCP só
inicia/mantém o stream de vídeo. Cria uma pasta capturas/gravacao_<hora>/ com:
  video.h264      vídeo cru (reproduz com ffplay/ffmpeg)
  quadros.csv     t (relógio do notebook), ts_drone, bytes, keyframe: um registro por quadro de vídeo
  telemetria.csv  t (mesmo relógio), roll, pitch, yaw, estado, modo, altura, v_vert, v_hor, satélites, gps_ok, bateria
Para ligar quadro e telemetria: para cada t de quadros.csv, pegue a linha de telemetria.csv com t mais próximo.
Uso: python3 -P scripts/gravar_voo.py [segundos=60] [--fotos]    (--fotos também salva 1 jpg por segundo)
"""
import csv
import os
import select
import socket
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from predator import bt, video  # noqa: E402

DRONE = ("192.168.0.1", 50000)
PERMITIDOS = {bt.request_telemetry()}
parar = threading.Event()


def telemetria(pasta):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, b"wlp2s0")
    s.bind(("", 0))
    campos = ["roll", "pitch", "yaw", "estado", "modo", "altura", "v_vert", "v_hor", "satelites", "gps_ok", "bateria"]
    d = dict.fromkeys(campos, "")
    with open(os.path.join(pasta, "telemetria.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t"] + campos)
        ult_pedido = ult_linha = 0.0
        while not parar.is_set():
            if time.time() - ult_pedido > 0.1:
                assert bt.request_telemetry() in PERMITIDOS
                s.sendto(bt.request_telemetry(), DRONE)
                ult_pedido = time.time()
            if select.select([s], [], [], 0.05)[0]:
                for q in bt.split(s.recvfrom(2048)[0]):
                    i = bt.parse(q)
                    if i["cmd"] == "0x88":
                        d.update(roll=i["roll"], pitch=i["pitch"], yaw=i["yaw"], estado=i["state"], modo=i["mode"])
                    elif i["cmd"] == "0x89":
                        d.update(altura=i["height"], v_vert=i["v_speed"], v_hor=i["h_speed"],
                                 satelites=i["satellites"], gps_ok=i["gps_fix"], bateria=i["battery"])
            if time.time() - ult_linha >= 0.1:
                w.writerow([round(time.time(), 3)] + [d[c] for c in campos])
                f.flush()
                ult_linha = time.time()


def gravar_video(pasta):
    n = 0
    with open(os.path.join(pasta, "video.h264"), "wb") as v, \
            open(os.path.join(pasta, "quadros.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "ts_drone", "bytes", "keyframe"])
        while not parar.is_set():
            try:
                for info, dados in video.frames():
                    if parar.is_set():
                        break
                    if dados:
                        v.write(dados)
                        w.writerow([round(time.time(), 3), info["ts"], len(dados), info["key"]])
                        f.flush()
                        n += 1
            except (OSError, ConnectionError, ValueError):
                time.sleep(1)
    return n


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    segundos = float(args[0]) if args else 60.0
    pasta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "capturas",
                         time.strftime("gravacao_%m%d_%H%M%S"))
    os.makedirs(pasta)
    print("gravando", segundos, "s em", os.path.abspath(pasta), flush=True)
    t = threading.Thread(target=telemetria, args=(pasta,), daemon=True)
    t.start()
    v = threading.Thread(target=gravar_video, args=(pasta,), daemon=True)
    v.start()
    try:
        time.sleep(segundos)
    except KeyboardInterrupt:
        print("interrompido", flush=True)
    parar.set()
    v.join(timeout=8)
    t.join(timeout=2)
    if "--fotos" in sys.argv:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "h264", "-i", os.path.join(pasta, "video.h264"),
                        "-vf", "fps=1", os.path.join(pasta, "foto_%03d.jpg")], check=False)
    tam = os.path.getsize(os.path.join(pasta, "video.h264"))
    print(f"pronto: video.h264 {tam / 1e6:.1f} MB, quadros.csv e telemetria.csv em {os.path.abspath(pasta)}")


if __name__ == "__main__":
    main()
