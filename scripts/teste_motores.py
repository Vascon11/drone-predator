"""Teste de motores: DESTRAVA (marcha lenta) por no máximo 2 s e TRAVA. Nunca decola.

- Acelerador sempre no mínimo (1000); nenhum comando de decolar existe neste arquivo.
- Qualquer erro, Ctrl+C ou fim do programa → envia travar (0x79 01) + emergência (0x94 02) repetidas vezes.
Uso: python3 scripts/teste_motores.py
"""
import os
import select
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from predator import bt  # noqa: E402

IFACE = b"wlp2s0"
DRONE = ("192.168.0.1", 50000)
MAX_MOTOR_S = 2.0
ALLOWED = {bt.request_telemetry(), bt.unlock(), bt.lock(), bt.frame(0x94, [2]),
           bt.joystick(throttle=1000)}
EMERGENCY = bt.frame(0x94, [2])


class Link:
    def __init__(self):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, IFACE)
        self.s.bind(("", 0))
        self.state = None
        self.last_tele = 0

    def send(self, data):
        if data not in ALLOWED:
            raise RuntimeError(f"bloqueado: {data.hex(' ')}")
        self.s.sendto(data, DRONE)

    def tick(self, wait=0.05):
        """Mantém o 'controle virtual' vivo e lê telemetria por `wait` segundos."""
        self.send(bt.joystick(throttle=1000))
        if time.time() - self.last_tele > 0.5:
            self.send(bt.request_telemetry())
            self.last_tele = time.time()
        end = time.time() + wait
        while (left := end - time.time()) > 0:
            if not select.select([self.s], [], [], left)[0]:
                continue
            pkt, _ = self.s.recvfrom(2048)
            for f in bt.split(pkt):
                info = bt.parse(f)
                if info['cmd'] == '0x88':
                    self.state = info['state']

    def safe_stop(self):
        for _ in range(10):
            try:
                self.send(bt.lock())
                self.send(EMERGENCY)
            except OSError:
                pass
            time.sleep(0.05)


def log(msg):
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def main():
    link = Link()
    try:
        for _ in range(20):
            link.tick()
        log(f"estado inicial: {link.state} (0 = travado)")
        if link.state is None:
            log("sem telemetria — abortando sem destravar")
            return
        if link.state != 0:
            log("drone NÃO está travado — abortando")
            return

        log("DESTRAVANDO (marcha lenta)")
        start = time.time()
        unlocked_at = None
        while time.time() - start < MAX_MOTOR_S:
            if unlocked_at is None:
                link.send(bt.unlock())
            link.tick()
            if link.state not in (0, None) and unlocked_at is None:
                unlocked_at = time.time()
                log(f"drone reportou estado {link.state} (destravado) após {unlocked_at - start:.2f} s")
        log("TRAVANDO")
        for _ in range(20):
            link.send(bt.lock())
            link.tick()
            if link.state == 0:
                break
        log(f"estado final: {link.state}")
        if unlocked_at is None:
            log("o drone NÃO reportou destravamento")
    finally:
        link.safe_stop()
        log("travar + emergência enviados")


if __name__ == "__main__":
    main()
