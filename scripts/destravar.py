"""Teste de destravar: destrava, fica armado alguns segundos no manche mínimo e trava. Não decola.

DESTRAVAR LIGA OS MOTORES (em marcha lenta). Hélices presas ou, melhor, retiradas; drone no chão, ninguém perto.
Registra estado, bateria, roll e pitch em capturas/destravar_*.csv. Ctrl+C ou erro: trava.
Uso: python3 -P scripts/destravar.py --confirmo-destravar [--tentativas 3] [--segura 3]
"""
import argparse
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import voo_1m as v  # noqa: E402
from predator import armar  # noqa: E402
from predator.voz import falar  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--confirmo-destravar", action="store_true")
    p.add_argument("--tentativas", type=int, default=3, choices=range(1, 6))
    p.add_argument("--segura", type=float, default=3.0, help="segundos armado antes de travar (máx. 10)")
    a = p.parse_args()
    if not a.confirmo_destravar:
        sys.exit("falta --confirmo-destravar")
    if not 0 <= a.segura <= 10:
        sys.exit("--segura entre 0 e 10 s")

    def sinal(_n, _f):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, sinal)

    raiz = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "capturas")
    caminho = os.path.join(raiz, f"destravar_{time.strftime('%Y%m%d_%H%M%S')}.csv")
    link = v.Link(v.DRONE, v.IFACE, caminho)
    v.log(f"registrando em {caminho}")
    resultado = "?"
    try:
        link.fase = "checagem"
        inicio = time.time()
        while time.time() - inicio < 3:
            link.ciclo(v.MINIMO)
        t = link.t
        if not link.completo() or link.idade > v.LIMITE_LINK:
            falar("sem_sinal")
            raise v.Encerrar("sem telemetria")
        v.log(f"estado={t['state']} bateria={t['battery']} satélites={t['satellites']} roll={t['roll']} pitch={t['pitch']}")
        if t["state"] != 0:
            raise v.Encerrar("já está destravado: travo e saio")
        link.fase = "destravar"
        falar("destravando")
        ok, dt = armar.destravar(link, v.MINIMO, max_s=3.0, tentativas=a.tentativas, log=v.log)
        resultado = f"destravou em {dt:.2f} s" if ok else "NÃO destravou"
        if ok:
            link.fase = "armado"
            fim = time.time() + a.segura
            while time.time() < fim:
                link.ciclo(v.MINIMO)
    except v.Encerrar as e:
        v.log(f"ABORTADO: {e}")
        resultado = f"abortado: {e}"
    except BaseException as e:
        v.log(f"INTERROMPIDO: {type(e).__name__}: {e}")
        resultado = "interrompido"
    finally:
        link.fase = "travar"
        if link.t.get("state") not in (0, None):
            if not armar.travar(link, v.MINIMO, log=v.log):
                v.log("AVISO: não confirmou travado; use a chave do drone")
        link.f.close()
    v.log(f"resultado: {resultado}; estado final {link.t.get('state')} (0 = travado), bateria {link.t.get('battery')}")


if __name__ == "__main__":
    main()
