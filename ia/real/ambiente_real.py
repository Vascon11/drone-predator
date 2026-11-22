"""Mundo original com bootstrap de ruido observado e hipoteses de dinamica."""
import json
import math
import random
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ia'))
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))
from modelo import np
from jogo_correcao import Mundo, DT
from predator.controle import PD, Ganhos

PROFESSOR = PD(Ganhos(kp=60, kd=15))
MODELOS = ('velocidade', 'antigo', 'medido')
CONDICOES = ('nominal', 'retencao')
CAL = json.loads((ROOT / 'ia/real/calibracao.json').read_text())


def fundir(vx, vy, vh):
    """Direcao vem da derivada, nao do yaw; vh nao informa direcao horizontal."""
    norm = math.hypot(vx, vy)
    if norm < 1e-9:
        return 0., 0.
    speed = .5 * norm + .5 * abs(vh)
    return vx * speed / norm, vy * speed / norm


class MundoReal(Mundo):
    def __init__(self, modelo, semente, condicao='nominal'):
        self.pronto = False
        super().__init__(modelo, semente, ruido=0.)
        # RNG de sensores separado: politica nao muda o sorteio fisico.
        self.sensor = random.Random(semente + 7100000)
        self.m = dict(self.m)
        for key, bounds in CAL['dinamica'].items():
            if key in self.m and self.m[key] is not None:
                self.m[key] = self.sensor.uniform(*bounds)
        # Antigo continua sendo a hipotese de angulo mantido, nao um ajuste confirmado.
        self.ex.m = self.ey.m = self.m
        self.offset = self.sensor.choice(CAL['offsets'])
        self.roll_m, self.pitch_m = self.offset
        self.condicao = condicao
        self.trace = self.sensor.choices(CAL['traces'], weights=[len(t) for t in CAL['traces']], k=1)[0]
        self.trace_i = self.sensor.randrange(len(self.trace))
        self.sentido = 1
        self.yaw = self.sensor.uniform(-math.pi, math.pi)
        self.proxima = 0.
        self.dvx = self.dvy = 0.
        self.pronto = True
        self.medir(0.)

    def medir(self, agora):
        if not self.pronto:
            return
        if agora + 1e-8 < self.proxima:
            return
        e, n, nv = self.trace[self.trace_i]
        # Reflexao evita saltos artificiais ao reiniciar um trecho curto.
        if self.trace_i + self.sentido not in range(len(self.trace)):
            self.sentido *= -1
        self.trace_i += self.sentido
        nx = e * math.cos(self.yaw) - n * math.sin(self.yaw)
        ny = e * math.sin(self.yaw) + n * math.cos(self.yaw)
        mx, my = self.x + nx, self.y + ny
        delta = agora - self.ult
        if delta > 0:
            self.dvx = .6*self.dvx + .4*(mx-self.sx)/delta
            self.dvy = .6*self.dvy + .4*(my-self.sy)/delta
        self.sx, self.sy, self.ult = mx, my, agora
        self.vsx, self.vsy = fundir(self.dvx, self.dvy, math.hypot(self.vx, self.vy) + nv)
        self.roll_m = self.ex.ang + self.offset[0]
        self.pitch_m = self.ey.ang + self.offset[1]
        pool = CAL['intervalos'] if self.condicao == 'nominal' else CAL['intervalos_lentos']
        intervalo = self.sensor.choice(pool)
        self.proxima = max(self.proxima + max(.1, intervalo), agora + .001)


def episodio(nome, seed, politica=None, condicao='nominal', coletar=False):
    w = MundoReal(nome, seed, condicao)
    hist, anterior = None, np.zeros(2)
    xs, ys, errors, commands = [], [], [], []
    stale, measures = 0, 0
    for tick in range(3000):
        if tick % 5 == 0:
            old = w.ult
            if tick:
                w.medir(w.t)
            stale += int(tick > 0 and old == w.ult)
            obs = [w.sx, w.sy, w.vsx, w.vsy]
            hist = [obs[:] for _ in range(5)] if hist is None else hist[1:] + [obs]
            entrada = np.r_[np.asarray(hist).ravel(), anterior]
            label = np.asarray(PROFESSOR.comando(*obs))
            cmd = label if politica is None else np.asarray(politica(entrada))
            if not np.isfinite(cmd).all() or np.max(np.abs(cmd)) > 100.000001:
                raise ValueError('Comando invalido')
            if coletar:
                xs.append(entrada)
                ys.append(label)
            commands.append(cmd)
            anterior = cmd
            measures += 1
        w.passo(float(cmd[0]), float(cmd[1]))
        errors.append(w.erro)
        if w.erro > 4:
            break
    cmds = np.array(commands)
    return dict(erro_m=float(np.mean(errors)), perdida=int(w.erro > 4),
        duracao_s=len(errors)*DT, saturado=float(np.mean(np.max(np.abs(cmds), axis=1) >= 95)),
        limite_pd=float(np.mean(np.max(np.abs(cmds), axis=1) >= 57)),
        suavidade=float(np.mean(np.abs(np.diff(np.vstack((np.zeros((1,2)), cmds)), axis=0)))),
        retidas=stale/measures), xs, ys
