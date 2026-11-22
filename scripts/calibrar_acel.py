"""Calibra o acelerômetro (0x7A F1) com o drone TRAVADO, parado e nivelado. Lista fechada de pacotes.
Uso: python3 -P scripts/calibrar_acel.py --confirmo
"""
import os
import select
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from predator import bt  # noqa: E402

DRONE = ("192.168.0.1", 50000)
CALIBRAR = bt.frame(0x7A, [0xF1])
PERMITIDOS = {bt.request_telemetry(), CALIBRAR}
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, b"wlp2s0")
s.bind(("", 0))


def ler(segundos, pedir=True):
    fim, ult, amostras, extras = time.time() + segundos, 0, [], []
    while time.time() < fim:
        if pedir and time.time() - ult > 0.1:
            assert bt.request_telemetry() in PERMITIDOS
            s.sendto(bt.request_telemetry(), DRONE)
            ult = time.time()
        if select.select([s], [], [], 0.05)[0]:
            for q in bt.split(s.recvfrom(2048)[0]):
                i = bt.parse(q)
                if i["cmd"] == "0x88":
                    amostras.append((i["roll"], i["pitch"], i["state"]))
                elif i["cmd"] in ("0x28", "0x7a"):
                    extras.append((round(time.time() - T0, 1), i["cmd"], i.get("raw")))
    return amostras, extras


def media(a):
    return round(sum(x[0] for x in a) / len(a), 2), round(sum(x[1] for x in a) / len(a), 2)


if "--confirmo" not in sys.argv:
    sys.exit("falta --confirmo")
T0 = time.time()
antes, _ = ler(3)
if not antes or any(x[2] != 0 for x in antes):
    sys.exit("drone não está travado ou sem telemetria: não calibro")
print("antes  roll/pitch:", media(antes), flush=True)
for _ in range(3):
    s.sendto(CALIBRAR, DRONE)
    time.sleep(0.1)
print("comando de calibração enviado", flush=True)
_, extras = ler(12)
depois, extras2 = ler(4)
print("depois roll/pitch:", media(depois) if depois else "sem telemetria")
for e in (extras + extras2)[:12]:
    print("  ", e)
