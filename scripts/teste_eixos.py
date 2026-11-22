"""Teste de eixos: UM voo curto por direção (frente, tras, direita, esquerda) para descobrir qual canal do manche vai para onde.

Decola com o pulso, aplica um desvio pequeno e curto no canal escolhido e pousa (mesmas checagens, limites e pouso de voo_1m.py).
Depois do voo, compara o deslocamento por GPS com o yaw e o roll/pitch medidos. O resultado fica no CSV (fase = a direção).
Convenção testada (padrão RC modo 2): frente = pitch acima de 1500, tras = pitch abaixo, direita = roll acima, esquerda = roll abaixo.
Anote a olho para onde o drone foi: a telemetria não é de confiança em 30 cm de movimento.
Uso: python3 -P scripts/teste_eixos.py --direcao frente|tras|direita|esquerda --confirmo-voo [--desvio 60] [--acel 1625]
"""
import argparse
import csv
import math
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import voo_1m as v  # noqa: E402
import voo_frente as vf  # noqa: E402
from predator import bt  # noqa: E402

ACEL_MOVIMENTO = 1550


def manche(direcao, desvio):
    c = 1500
    if direcao == "frente":
        return bt.joystick(pitch=c + desvio, throttle=ACEL_MOVIMENTO)
    if direcao == "tras":
        return bt.joystick(pitch=c - desvio, throttle=ACEL_MOVIMENTO)
    if direcao == "direita":
        return bt.joystick(roll=c + desvio, throttle=ACEL_MOVIMENTO)
    return bt.joystick(roll=c - desvio, throttle=ACEL_MOVIMENTO)


def analisar(caminho, direcao):
    """Deslocamento por GPS decomposto no referencial do nariz (yaw = rumo do nariz, hipótese)."""
    linhas = [x for x in csv.DictReader(open(caminho)) if x["lat"] != ""]
    mov = [x for x in linhas if x["fase"] == direcao]
    if len(mov) < 3:
        print("poucos dados na fase de movimento para analisar")
        return
    a, b = mov[0], mov[-1]
    n = (float(b["lat"]) - float(a["lat"])) * 111320
    e = (float(b["lon"]) - float(a["lon"])) * 111320 * math.cos(math.radians(float(a["lat"])))
    yaw = math.radians(float(a["yaw"]))
    frente = n * math.cos(yaw) + e * math.sin(yaw)
    direita = -n * math.sin(yaw) + e * math.cos(yaw)
    pit = [float(x["pitch"]) for x in mov]
    rol = [float(x["roll"]) for x in mov]
    print(f"\n[{direcao}] deslocamento GPS na fase: {frente:+.2f} m para a frente do nariz, {direita:+.2f} m para a direita do nariz")
    print(f"[{direcao}] pitch {min(pit):+.1f}° a {max(pit):+.1f}°, roll {min(rol):+.1f}° a {max(rol):+.1f}°")
    print("GPS tem ~1 m de erro: se o deslocamento for menor que isso, vale o que você viu a olho.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--direcao", required=True, choices=["frente", "tras", "direita", "esquerda"])
    p.add_argument("--confirmo-voo", action="store_true")
    p.add_argument("--desvio", type=int, default=60, help="desvio do manche em relação a 1500 (20 a 100)")
    p.add_argument("--acel", type=int, default=1625, help="acelerador do pulso de decolagem")
    a = p.parse_args()
    if not a.confirmo_voo:
        sys.exit("falta --confirmo-voo")
    if not 20 <= a.desvio <= 100 or not 1550 <= a.acel <= 1640:
        sys.exit("fora do limite seguro: desvio 20–100, acelerador 1550–1640")

    pulso = bt.joystick(throttle=a.acel)
    mov = manche(a.direcao, a.desvio)
    v.PERMITIDOS.update({pulso, mov})

    def sinal(_n, _f):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, sinal)

    raiz = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "capturas")
    caminho = os.path.join(raiz, f"eixos_{a.direcao}_{time.strftime('%Y%m%d_%H%M%S')}.csv")
    link = v.Link(v.DRONE, v.IFACE, caminho)
    v.log(f"registrando em {caminho} (direção {a.direcao}, desvio {a.desvio}, pulso {a.acel}, acelerador do movimento {ACEL_MOVIMENTO})")

    no_ar, destravado, estado_chao = [False], False, [None]
    try:
        chao, partida = v.checagem(link)
        estado_chao[0] = chao
        v.destravar(link)
        destravado = True
        chao = v.recalibrar_chao(link, chao)
        estado_chao[0] = chao
        motivo, _ = vf.voar_frente(link, chao, partida, no_ar, pulso, mov, fase=a.direcao)
        v.pousar(link, motivo, chao)
    except v.Encerrar as e:
        v.log(f"ABORTADO: {e}")
        if link.t.get("state") not in (0, None):
            v.travar(link)
    except BaseException as e:
        v.log(f"INTERROMPIDO: {type(e).__name__}: {e}")
        if no_ar[0] or link.fase in ("decolar", a.direcao):
            while True:
                try:
                    v.pousar(link, "interrupção", estado_chao[0])
                    break
                except KeyboardInterrupt:
                    v.log("continua pousando")
        elif destravado or link.t.get("state") not in (0, None):
            v.travar(link)
    finally:
        link.f.close()
    v.log(f"estado final: {link.t.get('state')} (0 = travado)")
    try:
        analisar(caminho, a.direcao)
    except Exception as e:
        print(f"análise falhou: {e}")


if __name__ == "__main__":
    main()
