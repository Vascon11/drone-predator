"""Calibração completa em etapas (acelerômetro 0x7A F1, bússola 0x7A E1) conferida com o celular.

Só com o drone TRAVADO, no chão, SEM hélices girando. Lista fechada de pacotes: pedido de telemetria,
0x7A F1 e 0x7A E1. Nenhum comando de voo (destravar, decolar, manche) pode sair por aqui.

Como usar o celular como referência (app "Nível"/bolha e "Bússola"):
  1. acelerômetro: ponha o drone e o celular numa superfície que o celular mostra 0,0°/0,0°; o script
     calibra e confere se roll/pitch do drone ficam a até --tol graus (padrão 1,0) de 0;
  2. bússola: depois de girar o drone, aponte a frente dele para um rumo lido na bússola do celular,
     digite o rumo e o script mostra a diferença para o yaw do drone (a referência do yaw do drone é
     a mesma depois da calibração; use a diferença para ver se ela é estável entre rumos).
O vídeo do Captain Drone mostra DUAS passadas por calibração; use --passadas 2 para repetir cada uma.

Uso: python3 -P scripts/calibrar_completo.py --confirmo [--passadas 2] [--tol 1.0] [--so-acel|--so-bussola]
     python3 -P scripts/calibrar_completo.py --seco     (só lê telemetria, não calibra nada)
Registra o que o drone mandou em capturas/calibracao_<hora>.csv (0x28, 0x04, 0x7a e atitude).
"""
import argparse
import csv
import os
import select
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from predator import bt  # noqa: E402

DRONE = ("192.168.0.1", 50000)
ACEL = bt.frame(0x7A, [0xF1])
BUSSOLA = bt.frame(0x7A, [0xE1])
PERMITIDOS = {bt.request_telemetry(), ACEL, BUSSOLA}

ap = argparse.ArgumentParser()
ap.add_argument("--confirmo", action="store_true", help="necessário para enviar a calibração")
ap.add_argument("--seco", action="store_true", help="não envia calibração; só lê e registra")
ap.add_argument("--passadas", type=int, default=1, choices=(1, 2, 3))
ap.add_argument("--tol", type=float, default=1.0, help="tolerância de roll/pitch em graus (celular)")
ap.add_argument("--so-acel", action="store_true")
ap.add_argument("--so-bussola", action="store_true")
a = ap.parse_args()
if not (a.confirmo or a.seco):
    sys.exit("falta --confirmo (ou --seco para só ler)")

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, b"wlp2s0")
s.bind(("", 0))
T0 = time.time()
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "capturas"), exist_ok=True)
arq = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "capturas", time.strftime("calibracao_%m%d_%H%M%S.csv"))
log = csv.writer(open(arq, "w", newline=""))
log.writerow(["t", "etapa", "cmd", "hex"])
etapa = "inicio"


def enviar(dado):
    if dado not in PERMITIDOS:
        raise RuntimeError(f"bloqueado: {dado.hex(' ')}")
    s.sendto(dado, DRONE)


def ler(segundos):
    """Lê telemetria por `segundos`; devolve amostras (roll, pitch, yaw, estado) e quadros 0x28/0x7a vistos."""
    fim, ult, am, extras = time.time() + segundos, 0.0, [], []
    while time.time() < fim:
        if time.time() - ult > 0.1:
            enviar(bt.request_telemetry())
            ult = time.time()
        if select.select([s], [], [], 0.05)[0]:
            for q in bt.split(s.recvfrom(2048)[0]):
                i = bt.parse(q)
                log.writerow([round(time.time() - T0, 2), etapa, i["cmd"], q.hex(" ")])
                if i["cmd"] == "0x88":
                    am.append((i["roll"], i["pitch"], i["yaw"], i["state"]))
                elif i["cmd"] in ("0x28", "0x7a"):
                    extras.append((round(time.time() - T0, 1), i["cmd"], q[5:-1].hex(" ")))
    return am, extras


def media(am):
    n = len(am)
    return tuple(round(sum(x[k] for x in am) / n, 2) for k in range(3))


def resumo_extras(extras):
    """Mostra só as mudanças dos quadros 0x28/0x7a (o 0x28 chega 20 vezes por segundo)."""
    vistos, ult = [], {}
    for t, cmd, hx in extras:
        if ult.get(cmd) != hx:
            vistos.append((t, cmd, hx))
            ult[cmd] = hx
    for t, cmd, hx in vistos[:20]:
        print(f"    t={t:5.1f}s {cmd} {hx}")
    return vistos


def exige_travado():
    am, _ = ler(3)
    if not am:
        sys.exit("sem telemetria do drone: conecte no Wi-Fi do drone")
    if any(x[3] != 0 for x in am):
        sys.exit("drone destravado: não calibro (trave-o e deixe no chão)")
    return am


def acelerometro():
    global etapa
    for p in range(1, a.passadas + 1):
        etapa = f"acel{p}"
        input(f"\n[acelerômetro, passada {p}/{a.passadas}] Drone NIVELADO e parado (celular 0,0°/0,0°). ENTER... ")
        antes = media(exige_travado())
        print("  antes   roll/pitch/yaw:", antes)
        if a.seco:
            continue
        for _ in range(3):
            enviar(ACEL)
            time.sleep(0.1)
        print("  0x7A F1 enviado; aguarde 12 s sem mexer")
        _, ex = ler(12)
        am, ex2 = ler(4)
        resumo_extras(ex + ex2)
        if not am:
            print("  sem telemetria depois da calibração")
            continue
        r, pt, y = media(am)
        ok = abs(r) <= a.tol and abs(pt) <= a.tol
        print(f"  depois  roll={r:+.2f}° pitch={pt:+.2f}° (limite ±{a.tol}°) -> {'OK' if ok else 'FORA DO LIMITE'}")
        if not ok:
            print("  confira se a superfície está mesmo nivelada no celular e repita a passada")


def bussola():
    global etapa
    for p in range(1, a.passadas + 1):
        etapa = f"bussola{p}"
        input(f"\n[bússola, passada {p}/{a.passadas}] Longe de metal, carro e do celular. ENTER para começar... ")
        exige_travado()
        if not a.seco:
            for _ in range(3):
                enviar(BUSSOLA)
                time.sleep(0.1)
            print("  0x7A E1 enviado: gire o drone devagar nos 3 eixos por ~25 s (como no app)")
        _, ex = ler(25)
        resumo_extras(ex)
        rumos = []
        for i in range(1, 4):
            r = input(f"  aponte a frente do drone para um rumo; digite o rumo da bússola do celular (graus, ENTER para pular) [{i}/3]: ").strip()
            if not r:
                continue
            am, _ = ler(2)
            if am:
                y = media(am)[2]
                d = (y - float(r) + 180) % 360 - 180
                rumos.append(d)
                print(f"    yaw do drone {y:.1f}°  celular {float(r):.1f}°  diferença {d:+.1f}°")
        if len(rumos) >= 2:
            print(f"  variação da diferença entre rumos: {max(rumos) - min(rumos):.1f}° (quanto menor, melhor a calibração)")


try:
    print("arquivo de registro:", arq)
    if not a.so_bussola:
        acelerometro()
    if not a.so_acel:
        bussola()
finally:
    print("\nfim; o drone nunca recebeu comando de voo. Registro em", arq)
