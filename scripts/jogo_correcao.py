"""Jogo de manter o drone parado, SEM drone e sem rede: você corrige com WASD e o programa grava observação → ação.

Vista de cima. O alvo é o centro; o ponto azul é onde a TELEMETRIA diz que o drone está (ruidosa, 10 Hz); o drone real (cinza, opcional)
é empurrado por deriva e vento, e responde ao manche com o modelo medido em 20/11 (atraso ~0,15 s):
  velocidade : o manche comanda uma velocidade (60 unidades ≈ 0,4 m/s), hipótese B
  medido     : a inclinação sobe e volta a ~0 em ~0,5 s com o comando mantido (como nos dados reais)
  antigo     : ângulo mantido, atraso 0,4 s (o que eu supus antes)
Teclas: W frente (sobe na tela)  S trás  D direita  A esquerda   1–7 amplitude = % de força máxima (15, 20, 30, 40, 60, 80, 100)   N rodada nova   M troca o modelo
        V mostra/esconde o drone verdadeiro   Esc sai.
Cada rodada dura 60 s e acaba antes se o erro passar de 4 m. Grava capturas/jogo_<hora>.csv a 10 Hz:
  t, rodada, modelo, amp, med_x, med_y, vel_x, vel_y, real_x, real_y, cmd_roll, cmd_pitch   (x = direita, y = frente, em metros; cmd_* = % de força, de -100 a +100)
--auto N joga N rodadas por modelo com o controlador PD de predator/controle.py (sem janela) e grava no mesmo formato: serve de
professor e de linha de base para comparar com as suas correções.
Uso: python3 -P scripts/jogo_correcao.py [--modelo velocidade|medido|antigo] [--auto 20] [--ruido 0.25]
"""
import argparse
import csv
import math
import os
import random
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from predator.controle import Ganhos, PD  # noqa: E402
from simula_controle import MODELOS, Eixo  # noqa: E402

G, ARRASTO = 9.81, 0.6
DT, AMOSTRA = 0.02, 0.1       # física a 50 Hz, telemetria a 10 Hz
DURACAO, LIMITE = 60.0, 4.0
PRESETS = (15, 20, 30, 40, 60, 80, 100)   # % de força máxima do preset (100 unidades = 100 %)
SOBE, DESCE = 4.0, 6.0   # tecla = manche analógico: segurar leva a força a 100 % do preset em ~0,25 s; soltar volta a 0 em ~0,17 s


class Mundo:
    def __init__(self, modelo, semente, ruido=0.25):
        self.nome, self.m, self.rnd, self.ruido = modelo, MODELOS[modelo], random.Random(semente), ruido
        self.por_vel = "vel_por_unidade" in self.m
        vento = self.m.get("vento_residual", 0.25)
        deriva = 0.0 if self.por_vel else 0.35
        # vento: uma direção que gira DEVAGAR (~5°/s no máximo) e uma intensidade que varia devagar (~15 s), como no ar livre
        self.dir = self.rnd.uniform(0, 2 * math.pi)
        self.mag0 = self.rnd.uniform(0.5, 1.0) * (vento + deriva)
        self.mag = self.mag0
        self.nx = self.ny = 0.0  # ruído da medida correlacionado no tempo (~0,5 s), não um tremor branco
        ang, raio = self.rnd.uniform(0, 2 * math.pi), self.rnd.uniform(0.3, 1.5)
        self.x, self.y, self.vx, self.vy = raio * math.cos(ang), raio * math.sin(ang), 0.0, 0.0
        self.ex, self.ey = Eixo(self.m), Eixo(self.m)
        self.fila, self.cr, self.cp, self.t = [], 0.0, 0.0, 0.0
        self.sx, self.sy, self.vsx, self.vsy, self.ult = self.x, self.y, 0.0, 0.0, 0.0
        self.medir(0.0)

    def passo(self, r, p):
        """Avança 20 ms com o comando (r, p) pedido agora."""
        m = self.m
        self.fila.append((self.t + m["atraso"], r, p))
        while self.fila and self.fila[0][0] <= self.t:
            _, self.cr, self.cp = self.fila.pop(0)
        self.dir += self.rnd.gauss(0, 1) * 0.08 * math.sqrt(DT)
        self.mag = max(0.0, self.mag + (self.mag0 - self.mag) * DT / 15 + 0.02 * math.sqrt(DT) * self.rnd.gauss(0, 1))
        ax_v, ay_v = self.mag * math.cos(self.dir), self.mag * math.sin(self.dir)
        if self.por_vel:
            self.vx += (self.cr * m["vel_por_unidade"] - self.vx) * DT / m["tau_vel"] + ax_v * DT
            self.vy += (self.cp * m["vel_por_unidade"] - self.vy) * DT / m["tau_vel"] + ay_v * DT
        else:
            roll, pitch = self.ex.passo(self.cr), self.ey.passo(self.cp)
            self.vx += (G * math.tan(math.radians(roll)) - ARRASTO * self.vx + ax_v) * DT
            self.vy += (G * math.tan(math.radians(pitch)) - ARRASTO * self.vy + ay_v) * DT
        self.x += self.vx * DT
        self.y += self.vy * DT
        self.t += DT

    def medir(self, agora):
        """Telemetria a 10 Hz: posição ruidosa e velocidade estimada (derivada filtrada), como o piloto real vê."""
        a_ = 0.85  # correlação do ruído entre medidas de 0,1 s
        self.nx = a_ * self.nx + math.sqrt(1 - a_ * a_) * self.ruido * self.rnd.gauss(0, 1)
        self.ny = a_ * self.ny + math.sqrt(1 - a_ * a_) * self.ruido * self.rnd.gauss(0, 1)
        mx, my = self.x + self.nx, self.y + self.ny
        dt = agora - self.ult
        if dt > 0:
            self.vsx = 0.6 * self.vsx + 0.4 * (mx - self.sx) / dt
            self.vsy = 0.6 * self.vsy + 0.4 * (my - self.sy) / dt
        self.sx, self.sy, self.ult = mx, my, agora

    @property
    def erro(self):
        return math.hypot(self.x, self.y)


CAB = ["t", "rodada", "modelo", "amp", "med_x", "med_y", "vel_x", "vel_y", "real_x", "real_y", "cmd_roll", "cmd_pitch"]


def linha(w, rodada, amp, cr, cp):
    return [f"{w.t:.2f}", rodada, w.nome, amp, f"{w.sx:.3f}", f"{w.sy:.3f}", f"{w.vsx:.3f}", f"{w.vsy:.3f}",
            f"{w.x:.3f}", f"{w.y:.3f}", f"{cr:.1f}", f"{cp:.1f}"]


def auto(n, ruido, saida):
    pd = PD(Ganhos(kp=60, kd=15))
    print(f"Controlador PD (kp 60, kd 15) em {n} rodadas por modelo:")
    for modelo in MODELOS:
        erros, fora = [], 0
        for s in range(n):
            w, passos, acum = Mundo(modelo, 1000 + s, ruido), 0, []
            cr = cp = 0.0
            while w.t < DURACAO and w.erro < LIMITE:
                if passos % int(AMOSTRA / DT) == 0:
                    w.medir(w.t)
                    cr, cp = pd.comando(w.sx, w.sy, w.vsx, w.vsy)
                    saida.writerow(linha(w, f"pd_{modelo}_{s}", 0, cr, cp))
                w.passo(cr, cp)
                acum.append(w.erro)
                passos += 1
            erros.append(statistics.mean(acum))
            fora += w.erro >= LIMITE
        print(f"  {modelo:<10} erro médio {statistics.mean(erros):.2f} m, saiu dos 4 m em {fora}/{n}")


def avalia(ganhos, modelo, n, ruido):
    """Erro médio e rodadas perdidas do PD com `ganhos` no `modelo`, n rodadas com as mesmas sementes."""
    pd, erros, fora = PD(ganhos), [], 0
    for s in range(n):
        w, passos, acum, cr, cp = Mundo(modelo, 1000 + s, ruido), 0, [], 0.0, 0.0
        while w.t < DURACAO and w.erro < LIMITE:
            if passos % int(AMOSTRA / DT) == 0:
                w.medir(w.t)
                cr, cp = pd.comando(w.sx, w.sy, w.vsx, w.vsy)
            w.passo(cr, cp)
            acum.append(w.erro)
            passos += 1
        erros.append(statistics.mean(acum))
        fora += w.erro >= LIMITE
    return statistics.mean(erros), fora


def sintonia(n, ruido):
    print(f"Grade de ganhos do PD, {n} rodadas por célula (erro médio em m / rodadas perdidas):")
    print(f"  {'kp':>4} {'kd':>4} | {'velocidade':>16} | {'antigo':>16}")
    melhor = None
    for kp in (10, 15, 20, 30, 45, 60):
        for kd in (0, 5, 10, 15, 30):
            ev, fv = avalia(Ganhos(kp=kp, kd=kd), "velocidade", n, ruido)
            ea, fa = avalia(Ganhos(kp=kp, kd=kd), "antigo", n, ruido)
            print(f"  {kp:>4} {kd:>4} | {ev:>9.2f} m {fv:>2}/{n} | {ea:>9.2f} m {fa:>2}/{n}")
            chave = (fv + fa, ev + ea)
            if melhor is None or chave < melhor[0]:
                melhor = (chave, kp, kd, ev, ea)
    print(f"\nMelhor soma nos dois modelos: kp {melhor[1]}, kd {melhor[2]} (velocidade {melhor[3]:.2f} m, antigo {melhor[4]:.2f} m)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sintonia", type=int, default=0, help="grade de ganhos do PD nos modelos velocidade e antigo, N rodadas por célula")
    ap.add_argument("--modelo", choices=list(MODELOS), default="velocidade")
    ap.add_argument("--auto", type=int, default=0)
    ap.add_argument("--ruido", type=float, default=0.25)
    ap.add_argument("--auto-sair", type=float, default=0, help="TESTE: fecha sozinho depois de N segundos")
    a = ap.parse_args()
    if a.sintonia:
        sintonia(a.sintonia, a.ruido)
        return
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "capturas",
                           time.strftime("jogo_%m%d_%H%M%S") + ("_pd" if a.auto else "") + ".csv")
    arq = open(caminho, "w", newline="")
    w_csv = csv.writer(arq)
    w_csv.writerow(CAB)
    if a.auto:
        auto(a.auto, a.ruido, w_csv)
        arq.close()
        print("gravado em", caminho)
        return
    import tkinter as tk
    raiz = tk.Tk()
    raiz.title("Jogo: segure o drone no centro")
    L = 720
    tela = tk.Canvas(raiz, width=L, height=L, bg="#0b1020", highlightthickness=0)
    tela.pack()
    info = tk.Label(raiz, font=("monospace", 11), bg="#111", fg="#eee", anchor="w", justify="left", width=90, height=3)
    info.pack(fill="x")
    PX = 100.0
    estado = {"modelos": list(MODELOS), "i": list(MODELOS).index(a.modelo), "rodada": 0, "amp": 4, "ver": False, "teclas": set(),
              "mundo": None, "trilha": [], "fim": "", "pontos": 0, "soma": 0.0, "t0": time.time(), "ult_amostra": 0.0, "cr": 0.0, "cp": 0.0, "fr": 0.0, "fp": 0.0, "ult_tick": time.time()}
    soltar = {}

    def nova():
        estado["rodada"] += 1
        estado["mundo"] = Mundo(estado["modelos"][estado["i"]], int(time.time() * 1000) % 100000, a.ruido)
        estado.update(trilha=[], fim="", pontos=0, soma=0.0, ult_amostra=0.0, cr=0.0, cp=0.0, fr=0.0, fp=0.0, ult_tick=time.time())

    def desenha():
        w = estado["mundo"]
        tela.delete("all")
        c = L / 2
        for r in (0.5, 1, 2, 3, 4):
            tela.create_oval(c - r * PX, c - r * PX, c + r * PX, c + r * PX, outline="#26324f" if r < 4 else "#7a2330")
        tela.create_line(c - 12, c, c + 12, c, fill="#9fb3d9")
        tela.create_line(c, c - 12, c, c + 12, fill="#9fb3d9")
        for i in range(1, len(estado["trilha"])):
            x0, y0, x1, y1 = estado["trilha"][i - 1] + estado["trilha"][i]
            tela.create_line(c + x0 * PX, c - y0 * PX, c + x1 * PX, c - y1 * PX, fill="#2e5a9c")
        if estado["ver"]:
            tela.create_oval(c + w.x * PX - 9, c - w.y * PX - 9, c + w.x * PX + 9, c - w.y * PX + 9, outline="#888")
        tela.create_oval(c + w.sx * PX - 7, c - w.sy * PX - 7, c + w.sx * PX + 7, c - w.sy * PX + 7, fill="#4da3ff", outline="")
        tela.create_line(c + w.sx * PX, c - w.sy * PX, c + (w.sx + w.vsx) * PX, c - (w.sy + w.vsy) * PX, fill="#ffd166", width=2)
        med = estado["soma"] / estado["pontos"] if estado["pontos"] else 0.0
        info.config(text=(f"rodada {estado['rodada']}   modelo: {w.nome}   tempo {w.t:4.1f}/{DURACAO:.0f} s   "
                          f"erro (medido) {math.hypot(w.sx, w.sy):.2f} m   erro médio {med:.2f} m   {estado['fim']}\n"
                          f"amplitude {PRESETS[estado['amp']]}  teclas {''.join(sorted(estado['teclas'])) or '-'}   "
                          f"WASD corrigem · 1–7 força máx · N nova · M troca modelo · V verdadeiro · Esc sai\n"
                          f"gravando em {os.path.basename(caminho)}"))

    def ciclo():
        w = estado["mundo"]
        if not estado["fim"]:
            t = estado["teclas"]
            amp = PRESETS[estado["amp"]]
            alvo_r, alvo_p = ("d" in t) - ("a" in t), ("w" in t) - ("s" in t)
            dt_r = time.time() - estado["ult_tick"]
            for chave, alvo in (("fr", alvo_r), ("fp", alvo_p)):
                f = estado[chave]
                taxa = (SOBE if abs(alvo) > abs(f) or alvo * f < 0 else DESCE) * dt_r
                estado[chave] = f + max(-taxa, min(taxa, alvo - f))
            cr, cp = amp * estado["fr"], amp * estado["fp"]
            agora = time.time()
            passos = max(1, min(5, round((agora - estado["ult_tick"]) / DT)))  # acompanha o relógio mesmo se a janela atrasar
            estado["ult_tick"] = agora
            for _ in range(passos):
                w.passo(cr, cp)
            estado["cr"], estado["cp"] = cr, cp
            if w.t - estado["ult_amostra"] >= AMOSTRA:
                estado["ult_amostra"] = w.t
                w.medir(w.t)
                w_csv.writerow(linha(w, estado["rodada"], amp, cr, cp))
                estado["trilha"].append((w.sx, w.sy))
                estado["pontos"] += 1
                estado["soma"] += w.erro
            if w.erro >= LIMITE:
                estado["fim"] = "SAIU: o drone se perdeu (N para nova rodada)"
            elif w.t >= DURACAO:
                estado["fim"] = "FIM da rodada (N para nova)"
        desenha()
        if a.auto_sair and time.time() - estado["t0"] > a.auto_sair:
            arq.close()
            raiz.destroy()
            return
        raiz.after(int(DT * 1000), ciclo)

    def baixo(ev):
        k = ev.keysym.lower()
        if k in soltar:
            raiz.after_cancel(soltar.pop(k))
            return
        if k in ("w", "a", "s", "d"):
            estado["teclas"].add(k)
        elif k in "1234567" and len(k) == 1:
            estado["amp"] = int(k) - 1
        elif k == "n":
            nova()
        elif k == "m":
            estado["i"] = (estado["i"] + 1) % len(estado["modelos"])
            nova()
        elif k == "v":
            estado["ver"] = not estado["ver"]
        elif k == "escape":
            arq.close()
            raiz.destroy()

    def cima(ev):
        k = ev.keysym.lower()
        soltar[k] = raiz.after(40, lambda: (estado["teclas"].discard(k), soltar.pop(k, None)))

    raiz.bind("<KeyPress>", baixo)
    raiz.bind("<KeyRelease>", cima)
    raiz.focus_force()
    nova()
    ciclo()
    raiz.mainloop()
    print("gravado em", caminho)


if __name__ == "__main__":
    main()
