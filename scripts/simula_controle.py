"""Simulação (sem drone, sem rede) do controlador de predator/controle.py ficando parado.

O modelo vem dos voos de 20/11 (capturas/eixos_frente_*.csv e voofrente_*.csv):
- o desvio de 60 no manche deu um pico de ~4,3° em ~0,2 s e a inclinação VOLTOU a ~0 em ~0,5 s com o comando ainda aplicado:
  o drone reage à MUDANÇA do comando, não ao valor mantido (modelo "lavagem": passa-alta com constante ~0,45 s);
- atraso comando → inclinação ≤ 0,1–0,2 s; telemetria a 10 Hz; ruído parado de roll/pitch ±0,05°.
`--modelo antigo` usa o que eu tinha suposto antes (ângulo mantido, 0,1°/unidade, atraso 0,4 s), para comparar.
Aceleração horizontal = g·tan(inclinação) − arrasto; vento e deriva própria são constantes por voo, mais um ruído.
Uso: python3 -P scripts/simula_controle.py [--sementes 40] [--ruido 0.25] [--modelo medido|antigo]
"""
import argparse
import math
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from predator.controle import Ganhos, PD, Vigia  # noqa: E402

DT = 0.02
CONTROLE_HZ = 10.0
G = 9.81
ARRASTO = 0.6

MODELOS = {
    # hipótese B: o manche comanda VELOCIDADE (o drone segura a velocidade e a inclinação volta a ~0): 60 unidades ≈ 0,4 m/s (vh medido)
    "velocidade": dict(vel_por_unidade=0.0067, tau_vel=0.5, atraso=0.15, vento_residual=0.1),
    "medido": dict(graus_por_unidade=0.07, tau_subida=0.1, tau_lavagem=0.45, atraso=0.15),
    "antigo": dict(graus_por_unidade=0.10, tau_subida=0.25, tau_lavagem=None, atraso=0.40),
}


class Eixo:
    """Inclinação a partir do comando: 1ª ordem; com lavagem, só a parte que muda (passa-alta) vira ângulo."""

    def __init__(self, m):
        self.m, self.ang, self.filtrado = m, 0.0, 0.0

    def passo(self, cmd):
        m = self.m
        alvo = cmd
        if m["tau_lavagem"]:
            self.filtrado += (cmd - self.filtrado) * DT / m["tau_lavagem"]
            alvo = cmd - self.filtrado
        self.ang += (alvo * m["graus_por_unidade"] - self.ang) * DT / m["tau_subida"]
        return self.ang


def simula(g, semente, modelo, duracao=25.0, ruido=0.25, vento=0.25, deriva=0.35, troca=False, sinal_real=1):
    """Devolve (erro máximo, erro médio depois de 5 s, fração saturada, motivo do Vigia ou None)."""
    m = MODELOS[modelo]
    por_velocidade = "vel_por_unidade" in m
    if por_velocidade:
        vento, deriva = m["vento_residual"], 0.0
    rnd = random.Random(semente)
    pd, vigia = PD(g), Vigia()
    ex_, ey_ = Eixo(m), Eixo(m)
    x = y = vx = vy = 0.0
    fx = rnd.uniform(-vento, vento) + rnd.uniform(-deriva, deriva)
    fy = rnd.uniform(-vento, vento) + rnd.uniform(-deriva, deriva)
    fila, cmd_r, cmd_p = [], 0.0, 0.0
    t, prox, erros, sat, n = 0.0, 0.0, [], 0, 0
    vx_f = vy_f = 0.0
    ant = (0.0, 0.0, 0.0)
    roll = pitch = 0.0
    while t < duracao:
        if t >= prox:
            prox += 1.0 / CONTROLE_HZ
            mx, my = x + rnd.gauss(0, ruido), y + rnd.gauss(0, ruido)
            dt_m = t - ant[2]
            if dt_m > 0:
                vx_f = 0.6 * vx_f + 0.4 * (mx - ant[0]) / dt_m
                vy_f = 0.6 * vy_f + 0.4 * (my - ant[1]) / dt_m
            ant = (mx, my, t)
            r, p = pd.comando(mx, my, vx_f, vy_f)
            if troca:
                r, p = p, r
            r, p = r * sinal_real, p * sinal_real
            fila.append((t + m["atraso"], r, p))
            motivo = vigia.verifica(t, r, p, math.hypot(mx, my), roll, pitch)
            n += 1
            sat += max(abs(r), abs(p)) >= 0.95 * g.maximo
            if motivo:
                return max(erros, default=0.0), float("nan"), sat / n, motivo
        while fila and fila[0][0] <= t:
            _, cmd_r, cmd_p = fila.pop(0)
        if por_velocidade:
            vx += (cmd_r * m["vel_por_unidade"] - vx) * DT / m["tau_vel"] + (fx + rnd.gauss(0, 0.05)) * DT
            vy += (cmd_p * m["vel_por_unidade"] - vy) * DT / m["tau_vel"] + (fy + rnd.gauss(0, 0.05)) * DT
            x += vx * DT
            y += vy * DT
            erros.append(math.hypot(x, y))
            t += DT
            continue
        roll, pitch = ex_.passo(cmd_r), ey_.passo(cmd_p)
        vx += (G * math.tan(math.radians(roll)) - ARRASTO * vx + fx + rnd.gauss(0, 0.05)) * DT
        vy += (G * math.tan(math.radians(pitch)) - ARRASTO * vy + fy + rnd.gauss(0, 0.05)) * DT
        x += vx * DT
        y += vy * DT
        erros.append(math.hypot(x, y))
        t += DT
    return max(erros), statistics.mean(erros[int(5 / DT):]), sat / max(n, 1), None


def resumo(g, sementes, modelo, **kw):
    res = [simula(g, s, modelo, **kw) for s in range(sementes)]
    ok = [r for r in res if not r[3]]
    return {
        "vigia": sum(1 for r in res if r[3]),
        "pior": statistics.mean(r[0] for r in res),
        "medio": statistics.mean(r[1] for r in ok) if ok else float("nan"),
        "sat": statistics.mean(r[2] for r in res),
        "motivos": sorted({r[3] for r in res if r[3]}),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sementes", type=int, default=40)
    ap.add_argument("--ruido", type=float, default=0.25, help="m de ruído na medida de posição")
    ap.add_argument("--modelo", choices=list(MODELOS), default="medido")
    a = ap.parse_args()
    comum = dict(ruido=a.ruido)
    print(f"Modelo '{a.modelo}': {MODELOS[a.modelo]}")
    livre = [simula(Ganhos(kp=0, kd=0), s, a.modelo, **comum) for s in range(a.sementes)]
    print(f"Sem controle: erro máximo médio em 25 s = {statistics.mean(r[0] for r in livre):.1f} m\n")
    print(f"  {'kp':>4} {'kd':>4} | {'Vigia':>6} {'erro máx':>9} {'erro médio':>11} {'saturado':>9}")
    melhor = None
    for kp in (10, 20, 30, 45, 60):
        for kd in (15, 30, 60, 100):
            g = Ganhos(kp=kp, kd=kd)
            r = resumo(g, a.sementes, a.modelo, **comum)
            print(f"  {kp:>4} {kd:>4} | {r['vigia']:>6} {r['pior']:>8.2f}m {r['medio']:>10.2f}m {100 * r['sat']:>8.0f}%")
            if melhor is None or (r["vigia"], r["pior"]) < melhor[0]:
                melhor = ((r["vigia"], r["pior"]), g, r)
    g, r = melhor[1], melhor[2]
    print(f"\nMelhor: kp {g.kp:.0f}, kd {g.kd:.0f}: erro máximo {r['pior']:.2f} m, Vigia pousou {r['vigia']}/{a.sementes}")
    print("Mesmos ganhos, com defeitos no drone (o Vigia deve pousar):")
    for nome, kw in (("roll e pitch trocados", dict(troca=True)), ("sinal invertido", dict(sinal_real=-1))):
        d = resumo(g, a.sementes, a.modelo, **comum, **kw)
        print(f"  {nome}: Vigia pousou {d['vigia']}/{a.sementes} ({', '.join(d['motivos']) or 'nenhum'}), pior erro {d['pior']:.2f} m")


if __name__ == "__main__":
    main()
