"""Controlador para o Predator ficar parado: PD em posição/velocidade horizontal, com `Vigia` de segurança.

SÓ calcula: recebe medidas e devolve desvios de manche (unidades de 1500 ± desvio). Não envia nada ao drone.
Convenção da IA: a saída é CONTÍNUA, de −100 % a +100 % de força; 100 unidades de manche = 100 % (o limite do --forte do piloto;
o padrão do voo real é 60 %). Use `para_percentual` e `de_percentual` para converter.
Referencial do corpo: x = direita do nariz, y = frente do nariz (como a caminhada de 20/11 mostrou: yaw = rumo do nariz).
A relação manche → movimento do Predator NÃO foi confirmada em voo (o canal de pitch levou o drone para a direita), por isso
`sinal_roll`, `sinal_pitch` e `troca_eixos` existem: são ajustados depois dos voos de eixo e a simulação mostra que o Vigia
pousa quando o sinal está errado.
"""
import dataclasses
import math

MAX_DESVIO = 60  # unidades do manche = % de força (1500 ± 60 deu ~6° de inclinação em 20/11)
UNIDADES_100 = 100.0  # 100 unidades de manche = 100 % de força


def para_percentual(unidades):
    """Desvio de manche (unidades) → % de força, de −100 a +100."""
    return max(-100.0, min(100.0, 100.0 * unidades / UNIDADES_100))


def de_percentual(pct):
    """% de força (−100 a +100) → desvio de manche em unidades."""
    return max(-100.0, min(100.0, pct)) * UNIDADES_100 / 100.0


def limita(v, m):
    return max(-m, min(m, v))


@dataclasses.dataclass
class Ganhos:
    kp: float = 30.0       # unidades de manche por metro de erro
    kd: float = 60.0       # unidades por m/s
    trim_roll: float = 0.0   # desvio fixo que cancela a deriva própria do drone
    trim_pitch: float = 0.0
    maximo: float = MAX_DESVIO
    sinal_roll: int = 1      # +1: roll positivo leva o drone para a direita (asa direita para baixo)
    sinal_pitch: int = 1     # +1: pitch positivo leva o drone para a frente (a confirmar)
    troca_eixos: bool = False


class PD:
    """Chame `comando(erro_x, erro_y, vel_x, vel_y)` a cada medida (erro = onde o drone está − onde deveria estar)."""

    def __init__(self, g=None):
        self.g = g or Ganhos()

    def comando(self, ex, ey, vx, vy):
        if not all(math.isfinite(v) for v in (ex, ey, vx, vy)):
            raise ValueError("erro e velocidade devem ser finitos")
        g = self.g
        # quer ir contra o erro: aceleração desejada para a direita = −kp·ex − kd·vx
        ax = -(g.kp * ex + g.kd * vx)
        ay = -(g.kp * ey + g.kd * vy)
        roll = limita(g.sinal_roll * ax + g.trim_roll, g.maximo)
        pitch = limita(g.sinal_pitch * ay + g.trim_pitch, g.maximo)
        if g.troca_eixos:
            roll, pitch = pitch, roll
        return roll, pitch


class Vigia:
    """Manda pousar se o controle não está funcionando: comando saturado sem o erro cair, erro grande ou inclinação alta."""

    def __init__(self, maximo=MAX_DESVIO, t_saturado=2.5, erro_max=3.0, tilt_max=20.0):
        self.maximo, self.t_saturado, self.erro_max, self.tilt_max = maximo, t_saturado, erro_max, tilt_max
        self.sat_desde = None
        self.erro_sat = None

    def verifica(self, t, roll_cmd, pitch_cmd, erro, roll_deg=0.0, pitch_deg=0.0):
        """Devolve None ou o motivo para pousar."""
        if not all(math.isfinite(v) for v in (t, roll_cmd, pitch_cmd, erro, roll_deg, pitch_deg)):
            return "telemetria inválida"
        if erro > self.erro_max:
            return "erro grande"
        if max(abs(roll_deg), abs(pitch_deg)) > self.tilt_max:
            return "inclinação alta"
        saturado = max(abs(roll_cmd), abs(pitch_cmd)) >= 0.95 * self.maximo
        if saturado:
            if self.sat_desde is None:
                self.sat_desde, self.erro_sat = t, erro
            elif t - self.sat_desde > self.t_saturado and erro >= 0.9 * self.erro_sat:
                return "comando saturado sem melhorar o erro"
        else:
            self.sat_desde = None
        return None


def posicao_corpo(norte, leste, yaw_graus):
    """Converte deslocamento (norte, leste) em (direita do nariz, frente do nariz) pelo yaw (rumo do nariz)."""
    y = math.radians(yaw_graus)
    frente = norte * math.cos(y) + leste * math.sin(y)
    direita = -norte * math.sin(y) + leste * math.cos(y)
    return direita, frente
