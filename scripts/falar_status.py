"""Fala o estado do Predator com a voz da Thalita. Só leitura: envia SOMENTE o pedido de telemetria.

Se não chegar telemetria, diz "sem sinal do drone" e nunca inventa valores.
Uso: python3 -P scripts/falar_status.py [segundos de escuta, padrão 4] [--mudo]
"""
import os
import select
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from predator import bt  # noqa: E402
from predator.voz import falar  # noqa: E402

IFACE = b"wlp2s0"
DRONE = ("192.168.0.1", 50000)
ALLOWED = {bt.request_telemetry()}
MIN_SATS = 8
BATERIA_VOO = 70   # regra da skill: só proponho voo com ~70 ou mais em repouso
BATERIA_BAIXA = 30


def ler(segundos):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, IFACE)
        s.bind(("", 0))
    except OSError:
        return {}
    t, fim = {}, time.time() + segundos
    while time.time() < fim:
        pedido = bt.request_telemetry()
        assert pedido in ALLOWED
        try:
            s.sendto(pedido, DRONE)
        except OSError:
            return t
        corte = time.time() + 0.5
        while (resta := corte - time.time()) > 0:
            if not select.select([s], [], [], resta)[0]:
                continue
            for q in bt.split(s.recvfrom(2048)[0]):
                i = bt.parse(q)
                if i["cmd"] in ("0x88", "0x89"):
                    t.update(i)
    return t


def frases(t):
    """Devolve (texto para tela, lista de nomes de áudio)."""
    if not t or "state" not in t:
        return "sem sinal do drone", ["sem_sinal"]
    nomes, partes = [], []
    if t["state"] == 0:
        nomes.append("travado"); partes.append("travado")
    else:
        nomes.append("destravado"); partes.append("DESTRAVADO")
    bat, sats = t.get("battery"), t.get("satellites")
    if bat is not None:
        partes.append(f"bateria {bat}")
        nomes.append("bateria_ok" if bat >= BATERIA_VOO else "bateria_baixa")
    if sats is not None:
        partes.append(f"{sats} satélites")
        nomes.append("gps_ok" if t.get("gps_fix") and sats >= MIN_SATS else "gps_fraco")
    if max(abs(t.get("roll", 0)), abs(t.get("pitch", 0))) > 10:
        nomes.append("inclinado"); partes.append("inclinado")
    nomes.append("sem_voo")
    return ", ".join(partes), nomes


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    segundos = float(args[0]) if args else 4
    t = ler(segundos)
    texto, nomes = frases(t)
    print(texto)
    if "--mudo" not in sys.argv:
        for n in nomes:
            falar(n, esperar=True)


if __name__ == "__main__":
    main()
