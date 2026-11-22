"""Acompanha a leitura da bateria do Predator durante a carga. Só leitura: envia SOMENTE o pedido de telemetria.

Uma leitura a cada --intervalo s (média de 3 s), registrada em capturas/bateria_*.csv com o tempo decorrido.
Fala "bateria em boas condições" uma vez ao chegar em --alvo; para ao chegar em --alvo + 10 sem subir mais ou no --max.
Uso: python3 -P scripts/monitor_bateria.py [--intervalo 30] [--max 90] [--alvo 80]   (--max em minutos)
"""
import argparse
import csv
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import falar_status as fs  # noqa: E402
from predator.voz import falar  # noqa: E402


def media_bateria(segundos=3):
    t = fs.ler(segundos)
    return t.get("battery"), t.get("state"), t.get("satellites")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--intervalo", type=float, default=30)
    p.add_argument("--max", type=float, default=90, help="minutos")
    p.add_argument("--alvo", type=int, default=80)
    a = p.parse_args()
    raiz = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "capturas")
    caminho = os.path.join(raiz, f"bateria_{time.strftime('%Y%m%d_%H%M%S')}.csv")
    inicio, avisou, maior = time.time(), False, -1
    with open(caminho, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["hora", "min", "bateria", "estado", "satelites"])
        print(f"registrando em {caminho}", flush=True)
        while (dt := (time.time() - inicio) / 60) < a.max:
            bat, estado, sats = media_bateria()
            w.writerow([time.strftime("%H:%M:%S"), round(dt, 1), bat if bat is not None else "", estado if estado is not None else "",
                        sats if sats is not None else ""])
            f.flush()
            print(f"{time.strftime('%H:%M:%S')} +{dt:.1f} min bateria={bat} estado={estado}", flush=True)
            if bat is not None:
                maior = max(maior, bat)
                if bat >= a.alvo and not avisou:
                    avisou = True
                    falar("bateria_ok")
                if bat >= a.alvo + 10:
                    break
            time.sleep(max(0, a.intervalo - 3))
    print(f"fim: maior leitura {maior}", flush=True)


if __name__ == "__main__":
    main()
