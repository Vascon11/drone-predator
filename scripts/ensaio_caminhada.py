"""Caminhada guiada por voz, SEM VOAR: você carrega o drone (travado) para frente, trás, direita e esquerda.

Mede o deslocamento por GPS (lat/lon do 0x89) e o decompõe no referencial do nariz usando o yaw (hipótese: yaw = rumo do nariz).
Se "frente" der + na frente do nariz e "direita" der + na direita do nariz, o yaw é o rumo do nariz.
Só leitura: envia SOMENTE o pedido de telemetria. O drone deve estar TRAVADO. O GPS tem ~1 m de erro; use passos grandes (~4).
Uso: python3 -P scripts/ensaio_caminhada.py [--sem-voz] [--passos-s 9]
"""
import argparse
import math
import os
import select
import socket
import statistics
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from predator import bt  # noqa: E402
from predator.voz import PASTA  # noqa: E402

IFACE = b"wlp2s0"
DRONE = ("192.168.0.1", 50000)
ALLOWED = {bt.request_telemetry()}
FASES = ["frente", "tras", "direita", "esquerda"]


class Leitor:
    def __init__(self):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, IFACE)
        self.s.bind(("", 0))
        self.ultimo = 0.0
        self.estado = None
        self.sats = None

    def coletar(self, segundos):
        """Devolve lista de dicts com lat, lon, yaw e h_speed (campos que chegaram em `segundos`)."""
        saida, fim, yaw = [], time.time() + segundos, None
        while time.time() < fim:
            if time.time() - self.ultimo >= 0.2:
                pedido = bt.request_telemetry()
                assert pedido in ALLOWED
                self.s.sendto(pedido, DRONE)
                self.ultimo = time.time()
            if not select.select([self.s], [], [], 0.05)[0]:
                continue
            for q in bt.split(self.s.recvfrom(2048)[0]):
                i = bt.parse(q)
                if i["cmd"] == "0x88":
                    self.estado, yaw = i["state"], i["yaw"]
                elif i["cmd"] == "0x89" and i.get("gps_fix") and yaw is not None:
                    self.sats = i["satellites"]
                    saida.append({"lat": i["lat"], "lon": i["lon"], "yaw": yaw, "vh": i["h_speed"]})
        return saida


def falar(leitor, nome, sem_voz):
    arquivo = os.path.join(PASTA, f"{nome}.wav")
    if sem_voz or not os.path.exists(arquivo):
        print(f"[voz] {nome}")
        return
    p = subprocess.Popen(["paplay", arquivo], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    while p.poll() is None:
        leitor.coletar(0.3)


def pos(amostras):
    return (statistics.median(a["lat"] for a in amostras), statistics.median(a["lon"] for a in amostras))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sem-voz", action="store_true")
    ap.add_argument("--passos-s", type=float, default=9.0, help="segundos para caminhar em cada direção")
    a = ap.parse_args()
    leitor = Leitor()
    leitor.coletar(2)
    if leitor.estado is None:
        sys.exit("sem telemetria do drone (notebook na rede dele?)")
    if leitor.estado != 0:
        sys.exit("o drone não está travado: não faço o ensaio")
    falar(leitor, "c_prepare", a.sem_voz)
    leitor.coletar(3)
    inicio = leitor.coletar(4)
    if len(inicio) < 3 or (leitor.sats or 0) < 8:
        sys.exit(f"GPS insuficiente para o ensaio (satélites {leitor.sats}, amostras {len(inicio)})")
    resultados = {}
    for nome in FASES:
        p0, yaw = pos(inicio), statistics.median(x["yaw"] for x in inicio)
        falar(leitor, f"c_{nome}", a.sem_voz)
        mov = leitor.coletar(a.passos_s)
        fim = leitor.coletar(3)  # parado no ponto final
        if len(fim) < 2:
            print(f"{nome}: sem GPS no fim, pulado")
            continue
        p1 = pos(fim)
        n = (p1[0] - p0[0]) * 111320
        e = (p1[1] - p0[1]) * 111320 * math.cos(math.radians(p0[0]))
        y = math.radians(yaw)
        frente = n * math.cos(y) + e * math.sin(y)
        direita = -n * math.sin(y) + e * math.cos(y)
        vmax = max((m["vh"] for m in mov), default=0)
        resultados[nome] = (frente, direita)
        print(f"{nome}: {frente:+.1f} m na frente do nariz, {direita:+.1f} m na direita do nariz "
              f"(total {math.hypot(n, e):.1f} m, h_speed máx {vmax:.1f}, yaw {yaw:.0f}°)")
        falar(leitor, "c_volte", a.sem_voz)
        leitor.coletar(6)
        inicio = leitor.coletar(4)
        if len(inicio) < 2:
            inicio = fim
    falar(leitor, "c_fim", a.sem_voz)
    print("\nConclusão:")
    esperado = {"frente": (1, 0), "tras": (-1, 0), "direita": (0, 1), "esquerda": (0, -1)}
    certos = 0
    for nome, (f, d) in resultados.items():
        ef, ed = esperado[nome]
        ok = (f * ef + d * ed) > 0.6 * math.hypot(f, d) and math.hypot(f, d) > 1.5
        certos += ok
        print(f"- {nome}: {'bate com o esperado' if ok else 'NÃO bate ou ficou pequeno (< 1,5 m)'}")
    print("yaw parece ser o rumo do nariz." if certos >= 3 else
          "Não dá para confirmar que o yaw é o rumo do nariz com estes dados (GPS ruidoso ou yaw deslocado).")


if __name__ == "__main__":
    main()
