"""Voo curto para medir o ângulo (pitch) ao andar para a frente: decola, inclina para a frente, pousa.

Reaproveita as checagens, os limites e o pouso de voo_1m.py. Fases no CSV: decolar, frente, pousar.
O sentido do pitch no manche NUNCA foi confirmado em voo: o valor PITCH_FRENTE pode ir para trás. Por isso é pequeno,
curto, e o CSV guarda roll/pitch/velocidade para descobrir o sentido real. Só ao ar livre, 5 m livres em volta.
Uso: python3 -P scripts/voo_frente.py --confirmo-voo [--pitch 1560] [--acel 1625]
"""
import argparse
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import voo_1m as v  # noqa: E402
from predator import bt  # noqa: E402
from predator.voz import falar  # noqa: E402

T_PULSO = 1.0     # s de acelerador de decolagem
T_FRENTE = 1.5    # s com o pitch aplicado
ACEL_FRENTE = 1600  # acelerador enquanto anda (1600 sem vento andou ~20 cm; 1650 capota)


def voar_frente(link, chao, partida, chegou_no_ar, pulso, frente, fase="frente"):
    link.fase = "decolar"
    v.log("DECOLANDO")
    falar("decolando")
    inicio, no_ar = time.time(), False
    while True:
        passou = time.time() - inicio
        if passou < T_PULSO:
            link.ciclo(pulso)
        elif passou < T_PULSO + T_FRENTE:
            if link.fase != fase:
                link.fase = fase
                v.log(f"MOVIMENTO '{fase}' (desvio aplicado por {T_FRENTE} s)")
            link.ciclo(frente)
        else:
            return "fim da fase de frente", False
        t = link.t
        if not no_ar and (t["height"] - chao >= v.SUBIDA_NO_AR or abs(t["v_speed"]) > 0.3
                          or max(abs(t["roll"]), abs(t["pitch"])) > 15):
            no_ar = True
            chegou_no_ar[0] = True
            v.log(f"saiu do chão (v_speed={t['v_speed']}, roll={t['roll']}, pitch={t['pitch']}) em {passou:.1f} s")
            falar("subindo")
        motivo = v.motivo_para_pousar(link, chao, partida)
        if motivo and motivo != "chegou na altura":
            chegou_no_ar[0] = True
            return motivo, False
        if motivo:  # altura (confiável só para cima): pousa
            chegou_no_ar[0] = True
            return motivo, False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--confirmo-voo", action="store_true")
    p.add_argument("--pitch", type=int, default=1560, help="manche de pitch (1500 = neutro; sentido a confirmar)")
    p.add_argument("--acel", type=int, default=1625, help="acelerador do pulso de decolagem")
    p.add_argument("--eixo", choices=["pitch", "roll"], default="pitch",
                   help="canal do manche que recebe o desvio (20/11: o canal pitch levou o drone para a direita)")
    p.add_argument("--acel-frente", type=int, default=ACEL_FRENTE, help="acelerador durante a fase de movimento")
    a = p.parse_args()
    if not a.confirmo_voo:
        sys.exit("falta --confirmo-voo")
    if not 1500 <= a.pitch <= 1600 or not 1550 <= a.acel <= 1640 or not 1500 <= a.acel_frente <= 1600:
        sys.exit("fora do limite seguro: desvio 1500–1600, acelerador 1550–1640, acelerador da frente 1500–1600")

    pulso = bt.joystick(throttle=a.acel)
    if a.eixo == "roll":
        frente = bt.joystick(roll=a.pitch, throttle=a.acel_frente)
    else:
        frente = bt.joystick(pitch=a.pitch, throttle=a.acel_frente)
    v.PERMITIDOS.update({pulso, frente})

    def sinal(_n, _f):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, sinal)

    raiz = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "capturas")
    caminho = os.path.join(raiz, f"voofrente_{time.strftime('%Y%m%d_%H%M%S')}.csv")
    link = v.Link(v.DRONE, v.IFACE, caminho)
    v.log(f"registrando em {caminho} (eixo {a.eixo} {a.pitch}, acelerador {a.acel}, na fase de movimento {a.acel_frente})")

    no_ar, destravado, estado_chao = [False], False, [None]
    try:
        chao, partida = v.checagem(link)
        estado_chao[0] = chao
        v.destravar(link)
        destravado = True
        chao = v.recalibrar_chao(link, chao)
        estado_chao[0] = chao
        motivo, _ = voar_frente(link, chao, partida, no_ar, pulso, frente)
        v.pousar(link, motivo, chao)
    except v.Encerrar as e:
        v.log(f"ABORTADO: {e}")
        if link.t.get("state") not in (0, None):
            v.travar(link)
    except BaseException as e:
        v.log(f"INTERROMPIDO: {type(e).__name__}: {e}")
        if no_ar[0] or link.fase in ("decolar", "frente"):
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


if __name__ == "__main__":
    main()
