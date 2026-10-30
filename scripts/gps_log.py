"""Registra o GPS do drone (só leitura): satélites, fix, lat/lon, altura, a cada 1 s, em CSV.

Para sozinho quando o GPS fica firme (fix + >= MIN_SATS satélites) por STABLE_S segundos, ou no tempo máximo.
Nenhum comando de voo pode sair por aqui: whitelist checada antes de cada envio.
Uso: python3 scripts/gps_log.py [minutos] [arquivo.csv]
"""
import csv
import os
import select
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from predator import bt  # noqa: E402

IFACE = b"wlp2s0"  # a rede de casa (cabo) também é 192.168.0.x
DRONE = ("192.168.0.1", 50000)
ALLOWED = {bt.request_telemetry()}
MIN_SATS = 6
STABLE_S = 15


def send(sock, data):
    if data not in ALLOWED:
        raise RuntimeError(f"bloqueado: {data.hex(' ')}")
    sock.sendto(data, DRONE)


def main():
    minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 10
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "capturas")
    os.makedirs(root, exist_ok=True)
    path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(root, f"gps_{time.strftime('%Y%m%d_%H%M%S')}.csv")

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, IFACE)
    s.bind(("", 0))

    start, stable_since, last = time.time(), None, None
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["hora", "satelites", "gps_ok", "lat", "lon", "altura_m", "distancia_m", "bateria"])
        print(f"registrando em {path}", flush=True)
        while time.time() - start < minutes * 60:
            send(s, bt.request_telemetry())
            pos = None
            deadline = time.time() + 1.0
            while (left := deadline - time.time()) > 0:
                if not select.select([s], [], [], left)[0]:
                    continue
                for fr in bt.split(s.recvfrom(2048)[0]):
                    info = bt.parse(fr)
                    if info["cmd"] == "0x89":
                        pos = info
            if not pos:
                print(f"{time.strftime('%H:%M:%S')} sem resposta do drone", flush=True)
                continue
            row = [time.strftime("%H:%M:%S"), pos["satellites"], int(pos["gps_fix"]), f"{pos['lat']:.7f}",
                   f"{pos['lon']:.7f}", pos["height"], pos["distance"], pos["battery"]]
            w.writerow(row)
            f.flush()
            key = (pos["satellites"], pos["gps_fix"], round(pos["lat"], 5), round(pos["lon"], 5))
            if key != last:  # só imprime quando algo muda
                print(f"{row[0]} satélites={row[1]} gps_ok={row[2]} lat={row[3]} lon={row[4]} bateria={row[7]}",
                      flush=True)
                last = key
            if pos["gps_fix"] and pos["satellites"] >= MIN_SATS:
                stable_since = stable_since or time.time()
                if time.time() - stable_since >= STABLE_S:
                    print(f"GPS firme por {STABLE_S} s — encerrando", flush=True)
                    break
            else:
                stable_since = None
    print("fim", flush=True)


if __name__ == "__main__":
    main()
