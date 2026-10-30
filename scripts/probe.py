"""Teste de leitura: envia SOMENTE o pedido de telemetria BT (0x88/0x89) e escuta.

Nenhum comando de voo pode sair por aqui: whitelist checada antes de cada envio.
Uso: python3 scripts/probe.py [segundos]
"""
import collections
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


def send(sock, data):
    if data not in ALLOWED:
        raise RuntimeError(f"bloqueado: {data.hex(' ')}")
    sock.sendto(data, DRONE)


def main():
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 8
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, IFACE)
    s.bind(("", 0))
    counts, last = collections.Counter(), {}
    end = time.time() + duration
    while time.time() < end:
        send(s, bt.request_telemetry())
        deadline = time.time() + 1.0
        while (left := deadline - time.time()) > 0:
            if not select.select([s], [], [], left)[0]:
                continue
            pkt, _ = s.recvfrom(2048)
            for f in bt.split(pkt):
                info = bt.parse(f)
                counts[info['cmd']] += 1
                last[info['cmd']] = info
    print("quadros recebidos por comando:", dict(counts))
    for cmd, info in sorted(last.items()):
        print(" ", info)


if __name__ == "__main__":
    main()
