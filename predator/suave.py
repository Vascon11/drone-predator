"""Movimento suave de uma posição a outra: perfil de velocidade + controle do manche. Puro (sem rede), testável.

Ideia: em vez de "tecla apertada = manche cheio", calcula a cada ciclo a velocidade que o drone DEVERIA ter:
acelera aos poucos (amax), anda no máximo a vmax e freia progressivamente perto do alvo (v ≤ √(2·afreio·distância)),
chegando devagar (v_chegada). Serve para a altura agora e, depois, para ir de uma coordenada de GPS a outra (um perfil por eixo).

Medido em 21/11 (estado 2, bateria boa), com o drone segurando a altura sozinho no acelerador 1500:
  1750 (+250) → +1,17 m/s   1250 (−250) → −0,26 m/s   soltar depois de subir: ainda +0,37 m/s por ~3 s (inércia).
"""
import collections
import math
import time

from .movimento import MovimentoConfig

SOBE_M_S_POR_US = 1.17 / 250   # m/s por µs de desvio acima de 1500
DESCE_M_S_POR_US = 0.26 / 250  # m/s por µs de desvio abaixo de 1500 (descer é bem mais lento)
DESVIO_MAX = 250               # µs: manche cheio do app no modo lento


class Perfil:
    """Velocidade de referência para ir de `pos` a `alvo` sem trancos."""

    def __init__(self, vmax, amax, afreio=None, v_chegada=0.0, tol=0.05):
        valores = (vmax, amax, v_chegada, tol) + (() if afreio is None else (afreio,))
        if not all(math.isfinite(v) and v >= 0 for v in valores):
            raise ValueError("parâmetros do perfil devem ser finitos e não negativos")
        self.vmax, self.amax = vmax, amax
        self.afreio = amax if afreio is None else afreio
        self.v_chegada, self.tol = v_chegada, tol
        self.v = 0.0  # última referência (para limitar a aceleração)

    def passo(self, pos, alvo, dt):
        if not all(math.isfinite(v) for v in (pos, alvo, dt)) or dt <= 0:
            raise ValueError("posição, alvo e dt devem ser finitos; dt deve ser positivo")
        dist = alvo - pos
        if abs(dist) <= self.tol:
            meta = 0.0
        else:
            # mais rápido que isso não dá para frear a tempo; nunca abaixo da velocidade de chegada
            freio = math.sqrt(2 * self.afreio * abs(dist)) + self.v_chegada
            meta = math.copysign(min(self.vmax, freio), dist)
        passo_max = self.amax * dt
        self.v += max(-passo_max, min(passo_max, meta - self.v))
        return self.v


class Velocidade:
    """Velocidade vertical pela variação da altura (o v_vert da telemetria ficou em 0,0–0,1 descendo em 21/11).
    Inclinação de uma reta pelos pontos da janela: menos ruído que a diferença de dois pontos."""

    def __init__(self, janela_s=0.6):
        if not math.isfinite(janela_s) or janela_s <= 0:
            raise ValueError("janela deve ser finita e positiva")
        self.janela = janela_s
        self.pts = collections.deque()

    def medir(self, t, h):
        if not math.isfinite(t) or not math.isfinite(h):
            raise ValueError("tempo e medida devem ser finitos")
        if self.pts and t < self.pts[-1][0]:
            self.pts.clear()
        self.pts.append((t, h))
        while self.pts and t - self.pts[0][0] > self.janela:
            self.pts.popleft()
        n = len(self.pts)
        if n < 3:
            return 0.0
        mt = sum(p[0] for p in self.pts) / n
        mh = sum(p[1] for p in self.pts) / n
        den = sum((p[0] - mt) ** 2 for p in self.pts)
        return 0.0 if den < 1e-9 else sum((p[0] - mt) * (p[1] - mh) for p in self.pts) / den


class ControleAltura:
    """Velocidade desejada → desvio do acelerador (µs). Antecipação pelo ganho medido + correção proporcional,
    e o desvio muda no máximo `taxa` µs por segundo (sem degrau no manche)."""

    def __init__(self, kp_us=150.0, taxa=500.0):
        if not all(math.isfinite(v) and v >= 0 for v in (kp_us, taxa)):
            raise ValueError("ganho e taxa devem ser finitos e não negativos")
        self.kp, self.taxa = kp_us, taxa
        self.dev = 0.0

    def passo(self, v_ref, v_med, dt):
        if not all(math.isfinite(v) for v in (v_ref, v_med, dt)) or dt <= 0:
            raise ValueError("velocidades e dt devem ser finitos; dt deve ser positivo")
        ff = v_ref / (SOBE_M_S_POR_US if v_ref >= 0 else DESCE_M_S_POR_US)
        alvo = max(-DESVIO_MAX, min(DESVIO_MAX, ff + self.kp * (v_ref - v_med)))
        passo_max = self.taxa * dt
        self.dev += max(-passo_max, min(passo_max, alvo - self.dev))
        return self.dev


# ---------------- mover_para: posição atual → alvo, suave em x, y e z ----------------
# Horizontal NÃO validado em voo automático: ganho do manche → velocidade só tem 2 medidas (20/11: desvio 60 ≈ 0,4 m/s;
# 21/11 manual: 250 em toques curtos ≈ 0,4–0,5 m/s) e o GPS erra 0,3–4 m. Por isso desvio horizontal limitado a 120 µs,
# velocidade baixa e tolerância de chegada de 1,5 m.
HORIZ_M_S_POR_US = 0.4 / 100
DESVIO_MAX_HORIZ = 120
TERRA_M_POR_GRAU = 111320.0


def metros_ne(lat0, lon0, lat, lon):
    """(norte, leste) em metros de (lat0, lon0) até (lat, lon)."""
    return ((lat - lat0) * TERRA_M_POR_GRAU,
            (lon - lon0) * TERRA_M_POR_GRAU * math.cos(math.radians(lat0)))


def para_corpo(norte, leste, rumo_graus):
    """Vetor norte/leste → (frente, direita) do drone, com o rumo do nariz (yaw da telemetria, graus a partir do norte)."""
    r = math.radians(rumo_graus)
    return (norte * math.cos(r) + leste * math.sin(r), -norte * math.sin(r) + leste * math.cos(r))


def para_mundo(frente, direita, rumo_graus):
    r = math.radians(rumo_graus)
    return (frente * math.cos(r) - direita * math.sin(r), frente * math.sin(r) + direita * math.cos(r))


def gps_valido(tel, min_satelites=8, max_idade=1.5):
    """Aceita objetos antigos sem metadados; Telemetry exige fix, satélites e posição fresca."""
    for campo in ("lat", "lon", "yaw"):
        if hasattr(tel, campo) and not math.isfinite(getattr(tel, campo)):
            return False
    if hasattr(tel, "gps_fix") and not tel.gps_fix:
        return False
    if hasattr(tel, "satellites") and tel.satellites < min_satelites:
        return False
    if not hasattr(tel, "position_updated"):
        return True
    atualizado = tel.position_updated
    return bool(atualizado) and time.monotonic() - atualizado <= max_idade


class MoverPara:
    """Leva o drone da posição atual ao alvo com movimento suave. Crie com o alvo e chame passo() a cada ciclo.

    Alvos (todos opcionais; o eixo sem alvo fica parado onde está):
      altura=  m na altura da telemetria          frente=/direita=  m a partir de onde está, na direção do nariz agora
      norte=/leste=  m relativos à `origem` (lat, lon) — por padrão a posição de quando o comando começou
    passo(t, tel, dt) devolve dict com os desvios do manche (roll, pitch, acel, em µs) e `chegou`.
    """

    def __init__(self, tel, altura=None, frente=None, direita=None, norte=None, leste=None, origem=None,
                 vmax_v=0.8, vmax_desce=0.25, v_toque=0.1, vmax_h=0.5, tol_v=0.15, tol_h=1.5,
                 min_satelites=8, max_idade_gps=1.5, config=None):
        horizontal = any(v is not None for v in (frente, direita, norte, leste))
        if horizontal and not gps_valido(tel, min_satelites, max_idade_gps):
            raise ValueError("GPS sem fix, com poucos satélites ou posição velha")
        self.origem = origem or (tel.lat, tel.lon)
        n0, e0 = metros_ne(*self.origem, tel.lat, tel.lon)
        self.alvo_ne = None
        if frente is not None or direita is not None:
            dn, de = para_mundo(frente or 0.0, direita or 0.0, tel.yaw)
            self.alvo_ne = (n0 + dn, e0 + de)
        elif norte is not None or leste is not None:
            self.alvo_ne = (norte if norte is not None else n0, leste if leste is not None else e0)
        self.alvo_h = altura
        self.tol_v, self.tol_h = tol_v, tol_h
        self.min_satelites, self.max_idade_gps = min_satelites, max_idade_gps
        self.config = config or MovimentoConfig(
            forca_horizontal=DESVIO_MAX_HORIZ,
            forca_vertical_sobe=DESVIO_MAX,
            forca_vertical_desce=DESVIO_MAX,
        )
        self.vmax_v, self.vmax_desce = vmax_v, vmax_desce
        self.pv = Perfil(vmax_v, amax=0.6, afreio=0.4, v_chegada=v_toque)
        self.ph = Perfil(vmax_h, amax=0.3, afreio=0.2)
        self.vel_v = Velocidade()
        self.vel_n, self.vel_e = Velocidade(1.5), Velocidade(1.5)  # GPS: janela maior, filtra o ruído
        self.ctl_v = ControleAltura()
        self.dev_h = [0.0, 0.0]  # frente, direita (µs), com limite de variação

    def passo(self, t, tel, dt):
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("dt deve ser finito e positivo")
        out = {"roll": 0.0, "pitch": 0.0, "acel": 0.0, "chegou": True,
               "v_ref": 0.0, "dist_h": 0.0, "gps_ok": True}
        # --- vertical ---
        v_med = self.vel_v.medir(t, tel.height)
        if self.alvo_h is not None:
            self.pv.vmax = self.vmax_v if self.alvo_h >= tel.height else self.vmax_desce
            v_ref = self.pv.passo(tel.height, self.alvo_h, dt)
            if (abs(self.alvo_h - tel.height) > self.tol_v or abs(v_med) > 0.15
                    or abs(v_ref) > 0.05):
                out["chegou"] = False
        else:
            v_ref = 0.0
        out["acel"] = self.ctl_v.passo(v_ref, v_med, dt)
        out["v_ref"] = v_ref
        # --- horizontal ---
        if self.alvo_ne is not None:
            if not gps_valido(tel, self.min_satelites, self.max_idade_gps):
                out["chegou"], out["gps_ok"] = False, False
                return out
            n, e = metros_ne(*self.origem, tel.lat, tel.lon)
            vn, ve = self.vel_n.medir(t, n), self.vel_e.medir(t, e)
            dn, de = self.alvo_ne[0] - n, self.alvo_ne[1] - e
            dist = math.hypot(dn, de)
            out["dist_h"] = dist
            if dist > self.tol_h or math.hypot(vn, ve) > 0.2 or abs(self.ph.v) > 0.05:
                out["chegou"] = False
            vel = self.ph.passo(-dist, 0.0, dt) if dist > self.tol_h else self.ph.passo(0.0, 0.0, dt)
            un, ue = (dn / dist, de / dist) if dist > 1e-6 else (0.0, 0.0)
            ref_f, ref_d = para_corpo(vel * un, vel * ue, tel.yaw)
            med_f, med_d = para_corpo(vn, ve, tel.yaw)
            for i, (ref, med) in enumerate(((ref_f, med_f), (ref_d, med_d))):
                alvo = ref / HORIZ_M_S_POR_US + 60.0 * (ref - med)
                alvo = max(-DESVIO_MAX_HORIZ, min(DESVIO_MAX_HORIZ, alvo))
                p = 300.0 * dt
                self.dev_h[i] += max(-p, min(p, alvo - self.dev_h[i]))
            out["pitch"], out["roll"] = self.dev_h  # pitch + = frente (W), roll + = direita (D)
        out["roll"], out["pitch"], _, out["acel"] = self.config.limitar(
            out["roll"], out["pitch"], 0.0, out["acel"])
        return out
