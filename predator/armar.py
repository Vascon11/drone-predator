"""Destravar e travar os motores do Predator, com tentativas, pausa e registro.

Biblioteca usada por scripts/destravar.py, voo_1m.py e voo_frente.py. Não abre socket: recebe um `link`
com `ciclo(manche, comando=None)`, `t` (telemetria) e `idade`, como a classe Link de scripts/voo_1m.py.
Só envia `0x79 00` (destravar), `0x79 01` (travar) e o manche mínimo, que o `link` precisa deixar passar.
Destravar liga os motores: só chamar depois de o usuário autorizar aquele voo/teste.
"""
import time

from . import bt

LIMITE_LINK = 1.0  # s sem telemetria: não confia no estado


def _imprime(msg):
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def _telemetria(link):
    if hasattr(link, "telemetry"):
        tel = link.telemetry
        return {"state": tel.state, "battery": tel.battery}, link.telemetry_age, tel.updated
    return link.t, link.idade, getattr(link, "recebido", None)


def _ciclo(link, minimo, comando=None):
    if hasattr(link, "ciclo"):
        link.ciclo(minimo, comando)
        return
    link.set_sticks(throttle=1000)
    if comando == bt.unlock():
        link.command("destravar", repeat=1)
    elif comando == bt.lock():
        link.command("travar", repeat=1)
    elif comando is not None:
        raise ValueError("comando não suportado pelo Drone")
    time.sleep(link.period)


def destravar(link, minimo, max_s=3.0, tentativas=1, pausa=1.0, log=_imprime):
    """Manda destravar até o estado mudar. Devolve (True, segundos) ou (False, None)."""
    for n in range(1, tentativas + 1):
        _, _, marcador_inicial = _telemetria(link)
        inicio = time.monotonic()
        while time.monotonic() - inicio < max_s:
            _ciclo(link, minimo, bt.unlock())
            _ciclo(link, minimo)
            tel, idade, marcador = _telemetria(link)
            confirmou = marcador is not None and marcador != marcador_inicial
            if tel.get("state") not in (0, None) and idade < LIMITE_LINK and confirmou:
                dt = time.monotonic() - inicio
                log(f"destravado em {dt:.2f} s (tentativa {n}/{tentativas}, bateria {tel.get('battery')})")
                return True, dt
        tel, _, _ = _telemetria(link)
        log(f"não destravou na tentativa {n}/{tentativas} em {max_s:.0f} s "
            f"(estado {tel.get('state')}, bateria {tel.get('battery')})")
        if n < tentativas:
            fim = time.monotonic() + pausa  # pausa com o manche mínimo; o drone às vezes precisa de um intervalo
            while time.monotonic() < fim:
                _ciclo(link, minimo)
    return False, None


def travar(link, minimo, max_s=2.0, log=_imprime):
    """Manda travar até o estado voltar a 0 com telemetria fresca. Devolve True/False."""
    _, _, marcador_inicial = _telemetria(link)
    inicio = time.monotonic()
    while time.monotonic() - inicio < max_s:
        _ciclo(link, minimo, bt.lock())
        _ciclo(link, minimo)
        tel, idade, marcador = _telemetria(link)
        confirmou = marcador is not None and marcador != marcador_inicial
        if tel.get("state") == 0 and idade < LIMITE_LINK and confirmou:
            log("travado")
            return True
    # o estado às vezes passa por 2 antes de 0: dá mais um instante só lendo
    fim = time.monotonic() + 2.0
    while time.monotonic() < fim:
        _ciclo(link, minimo)
        tel, idade, marcador = _telemetria(link)
        confirmou = marcador is not None and marcador != marcador_inicial
        if tel.get("state") == 0 and idade < LIMITE_LINK and confirmou:
            log("travado (confirmado depois)")
            return True
    return False
