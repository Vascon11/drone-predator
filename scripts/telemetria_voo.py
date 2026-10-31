"""Registra telemetria de voo em CSV (só leitura): atitude, altura, velocidade, GPS e bateria.

Nenhum comando de voo sai por aqui: lista fechada só com o pedido de telemetria.
Uso: python3 -P scripts/telemetria_voo.py [segundos] [arquivo.csv]
"""
import csv
import os
import select
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from predator import bt  # noqa: E402

IFACE = b"wlp2s0"
DRONE = ("192.168.0.1", 50000)
PERMITIDOS = {bt.request_telemetry()}


def enviar(s, dados):
    if dados not in PERMITIDOS:
        raise RuntimeError("bloqueado")
    s.sendto(dados, DRONE)


def main():
    segundos = float(sys.argv[1]) if len(sys.argv) > 1 else 300
    raiz = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    caminho = sys.argv[2] if len(sys.argv) > 2 else os.path.join(raiz, "capturas", f"voo_{time.strftime('%Y%m%d_%H%M%S')}.csv")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, IFACE)
    s.bind(("", 0))
    campos = ["t", "roll", "pitch", "yaw", "estado", "modo", "altura", "v_vert", "v_hor", "satelites", "gps_ok", "bateria"]
    dados = dict.fromkeys(campos[1:], "")
    fim, ultimo, escrito = time.time() + segundos, 0, 0
    with open(caminho, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(campos)
        while time.time() < fim:
            if time.time() - ultimo > 0.1:
                enviar(s, bt.request_telemetry())
                ultimo = time.time()
            if select.select([s], [], [], 0.05)[0]:
                for q in bt.split(s.recvfrom(2048)[0]):
                    i = bt.parse(q)
                    if i["cmd"] == "0x88":
                        dados.update(roll=i["roll"], pitch=i["pitch"], yaw=i["yaw"], estado=i["state"], modo=i["mode"])
                    elif i["cmd"] == "0x89":
                        dados.update(altura=i["height"], v_vert=i["v_speed"], v_hor=i["h_speed"], satelites=i["satellites"],
                                     gps_ok=i["gps_fix"], bateria=i["battery"])
            if time.time() - escrito >= 0.1:
                w.writerow([round(time.time(), 2)] + [dados[c] for c in campos[1:]])
                f.flush()
                escrito = time.time()
    print("salvo em", caminho)


if __name__ == "__main__":
    main()
