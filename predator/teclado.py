"""Das teclas para o manche do Predator. Puro: sem janela, sem rede, sem hardware (testável).

W/S = pitch (frente/trás), D/A = roll (direita/esquerda), E/Q = acelerador (sobe/desce, como no piloto do XS9), C/Z = yaw (girar direita/esquerda).
Os sentidos de cada canal do Predator NÃO foram confirmados em voo (em 20/11 o desvio no canal de pitch levou o drone para a
direita): cada eixo tem um sinal que o piloto pode inverter na hora.
O desvio é somado a 1500 (centro do manche, 1000..2000). Limites pequenos de propósito.
"""

from .movimento import MovimentoConfig

CENTRO = 1500
# 250 = manche cheio do app no modo de velocidade BAIXA (a biblioteca do app multiplica o desvio de ±500 por 0,5; ×1,0 no rápido).
# O piloto só chega aqui com --app; o padrão dele continua nos presets pequenos (±60 deu ~4–6° em 20/11).
MAX_RP = 250
MAX_YAW = 250
MAX_ACEL_SOBE = 100   # 1600; o pulso de decolagem usa 1625 e fica fora do teclado
MAX_ACEL_DESCE = 150  # 1350; 1300 é o que o script de voo usa para descer


def comando_teclas(teclas, amp_rp=None, amp_yaw=None, amp_acel=None, sinais=(1, 1, 1, 1), config=None):
    """teclas: conjunto de letras minúsculas. sinais = (pitch, roll, yaw, acelerador), cada um ±1.
    Devolve desvios (roll, pitch, yaw, acelerador) em unidades do manche; teclas opostas se anulam.
    Se `config` for fornecida, ela também limita todas as forças; sem ela, preserva os limites antigos."""
    limites = config or MovimentoConfig(MAX_RP, MAX_ACEL_SOBE, MAX_ACEL_DESCE, MAX_YAW)
    amp_rp = limites.forca_horizontal if amp_rp is None else min(abs(amp_rp), limites.forca_horizontal)
    amp_yaw = limites.forca_giro if amp_yaw is None else min(abs(amp_yaw), limites.forca_giro)
    amp_acel = limites.forca_vertical_desce if amp_acel is None else abs(amp_acel)
    frente = ("w" in teclas) - ("s" in teclas)
    lado = ("d" in teclas) - ("a" in teclas)
    giro = ("c" in teclas) - ("z" in teclas)
    sobe = ("e" in teclas) - ("q" in teclas)
    acel = sobe * amp_acel
    desvios = (sinais[1] * lado * amp_rp, sinais[0] * frente * amp_rp,
               sinais[2] * giro * amp_yaw, sinais[3] * acel)
    return limites.limitar(*desvios)


def para_manche(desvios, config=None):
    """Desvios (roll, pitch, yaw, acelerador) → dict em microssegundos para Drone.set_sticks, dentro de 1000..2000."""
    if config is not None:
        desvios = config.limitar(*desvios)
    r, p, y, a = (max(1000, min(2000, CENTRO + int(d))) for d in desvios)
    return {"roll": r, "pitch": p, "yaw": y, "throttle": a}
