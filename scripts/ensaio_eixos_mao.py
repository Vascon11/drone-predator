"""Ensaio à mão, SEM VOAR: a voz manda inclinar o drone (frente, trás, direita, esquerda) e o script mede roll/pitch/yaw.

Descobre o sinal da telemetria: nariz para baixo dá pitch + ou −? asa direita para baixo dá roll + ou −?
Só leitura: envia SOMENTE o pedido de telemetria. O drone deve estar TRAVADO (o script recusa se não estiver).
Uso: python3 -P scripts/ensaio_eixos_mao.py [--inclina 4] [--sem-voz]
"""
import argparse
import os
import select
import socket
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from predator import bt  # noqa: E402
from predator.voz import PASTA  # noqa: E402
import subprocess  # noqa: E402

IFACE = b"wlp2s0"
DRONE = ("192.168.0.1", 50000)
ALLOWED = {bt.request_telemetry()}
FASES = [("frente", "e_frente"), ("tras", "e_tras"), ("direita", "e_direita"), ("esquerda", "e_esquerda")]


class Leitor:
    def __init__(self):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, IFACE)
        self.s.bind(("", 0))
        self.ultimo = 0.0
        self.estado = None

    def amostras(self, segundos):
        """Lista de (roll, pitch, yaw) das atitudes 0x88 recebidas em `segundos`."""
        saida, fim = [], time.time() + segundos
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
                    self.estado = i["state"]
                    saida.append((i["roll"], i["pitch"], i["yaw"]))
        return saida


def falar(leitor, nome, sem_voz):
    """Toca a frase inteira, ouvindo a telemetria enquanto fala (para não perder pedidos)."""
    arquivo = os.path.join(PASTA, f"{nome}.wav")
    if sem_voz or not os.path.exists(arquivo):
        print(f"[voz] {nome}")
        return
    p = subprocess.Popen(["paplay", arquivo], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    while p.poll() is None:
        leitor.amostras(0.3)


def med(lista, i):
    return statistics.median(x[i] for x in lista) if lista else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inclina", type=float, default=4.0, help="segundos segurando cada inclinação")
    ap.add_argument("--sem-voz", action="store_true")
    a = ap.parse_args()
    leitor = Leitor()
    base = leitor.amostras(2)
    if not base:
        sys.exit("sem telemetria do drone (notebook na rede dele?)")
    if leitor.estado != 0:
        sys.exit("o drone não está travado: não faço o ensaio")
    falar(leitor, "e_prepare", a.sem_voz)
    leitor.amostras(3)
    nivel = leitor.amostras(3)
    r0, p0 = med(nivel, 0), med(nivel, 1)
    print(f"nivelado: roll {r0:+.1f}°, pitch {p0:+.1f}°")
    resultados = {}
    for nome, frase in FASES:
        falar(leitor, frase, a.sem_voz)
        leitor.amostras(1.5)  # tempo para inclinar
        seg = leitor.amostras(a.inclina)
        resultados[nome] = (med(seg, 0) - r0, med(seg, 1) - p0)
        print(f"{nome}: roll {resultados[nome][0]:+.1f}°, pitch {resultados[nome][1]:+.1f}° (relativos ao nivelado)")
        falar(leitor, "e_nivele", a.sem_voz)
        leitor.amostras(2.5)
    falar(leitor, "e_fim", a.sem_voz)
    f, t, d, e = (resultados[k] for k in ("frente", "tras", "direita", "esquerda"))
    print("\nConclusão (variação medida a partir do nivelado):")
    print(f"- nariz para baixo (frente): pitch {f[1]:+.1f}°  | nariz para cima (trás): pitch {t[1]:+.1f}°")
    print(f"- asa direita para baixo: roll {d[0]:+.1f}°  | asa esquerda para baixo: roll {e[0]:+.1f}°")
    if abs(f[1]) < 8 or abs(t[1]) < 8 or abs(d[0]) < 8 or abs(e[0]) < 8:
        print("AVISO: alguma inclinação ficou abaixo de 8°; o sinal é menos seguro. Repita inclinando mais.")
    cruz = abs(f[0]) > abs(f[1]) or abs(d[1]) > abs(d[0])
    print("AVISO: roll e pitch parecem TROCADOS na telemetria (o canal que mexeu foi o outro)." if cruz
          else "Roll e pitch da telemetria correspondem aos eixos esperados (o sinal acima mostra o sentido).")


if __name__ == "__main__":
    main()
