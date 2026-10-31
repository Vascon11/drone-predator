"""Teste de PTZ com o drone DESTRAVADO (só SEM HÉLICES): testa se a câmera só responde com motores ligados.

- Acelerador sempre no mínimo (1000); nenhum comando de decolar existe neste arquivo.
- Motores ligados por no máximo MAX_MOTOR_S. Sem telemetria por LINK_TIMEOUT → trava na hora.
- Qualquer erro, Ctrl+C ou fim do programa → envia travar (0x79 01) + emergência (0x94 02) repetidas vezes.
- Salva um PNG por fase em capturas/ptz_armado_<hora>/.
Uso: python3 -P scripts/teste_camera_destravado.py
"""
import os
import select
import socket
import sys
import time

import numpy as np
import pygame

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from predator import bt  # noqa: E402
from predator.video import VideoStream  # noqa: E402

IFACE = b"wlp2s0"
DRONE = ("192.168.0.1", 50000)
CENTER = 1500
MAX_MOTOR_S = 25.0
LINK_TIMEOUT = 1.5
# (nome, ptz1, ptz2, segundos): soma abaixo de MAX_MOTOR_S
PHASES = [
    ("referencia", CENTER, CENTER, 3),
    ("ptz2_alto", CENTER, 1800, 5),
    ("ptz2_volta", CENTER, CENTER, 1),
    ("ptz2_baixo", CENTER, 1200, 5),
    ("ptz2_centro", CENTER, CENTER, 1),
    ("ptz1_alto", 1800, CENTER, 3),
    ("ptz1_baixo", 1200, CENTER, 3),
]
EMERGENCY = bt.frame(0x94, [2])
ALLOWED = ({bt.request_telemetry(), bt.unlock(), bt.lock(), EMERGENCY}
           | {bt.joystick(throttle=1000, ptz1=a, ptz2=b) for _, a, b, _ in PHASES})


class Link:
    def __init__(self):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, IFACE)
        self.s.bind(("", 0))
        self.state = None
        self.updated = 0.0
        self.last_tele = 0

    def send(self, data):
        if data not in ALLOWED:
            raise RuntimeError(f"bloqueado: {data.hex(' ')}")
        self.s.sendto(data, DRONE)

    def tick(self, ptz1=CENTER, ptz2=CENTER, wait=0.05):
        self.send(bt.joystick(throttle=1000, ptz1=ptz1, ptz2=ptz2))
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
                    self.updated = time.time()

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


def gray(frame):
    a = np.frombuffer(frame, np.uint8).reshape(VideoStream.HEIGHT, VideoStream.WIDTH, 3)
    return a[::8, ::8].mean(axis=2)


def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "capturas",
                       time.strftime("ptz_armado_%H%M%S"))
    os.makedirs(out)
    link = Link()
    video = VideoStream().start()
    try:
        for _ in range(100):
            link.tick()
            if link.state is not None and video.latest:
                break
        log(f"estado: {link.state} (0 = travado), vídeo: {'ok' if video.latest else 'sem quadros'}")
        if link.state != 0 or not video.latest:
            log("abortando sem destravar: precisa de drone travado e vídeo")
            return

        log("DESTRAVANDO")
        start = time.time()
        while link.state == 0 and time.time() - start < 3:
            link.send(bt.unlock())
            link.tick()
        if link.state == 0:
            log("o drone NÃO destravou")
            return
        log(f"destravado (estado {link.state}) após {time.time() - start:.2f} s")

        ref = None
        for name, ptz1, ptz2, seconds in PHASES:
            end = time.time() + seconds
            while time.time() < end:
                link.tick(ptz1, ptz2)
                if time.time() - start > MAX_MOTOR_S:
                    log("limite de tempo atingido")
                    return
                if time.time() - link.updated > LINK_TIMEOUT:
                    log("telemetria perdida")
                    return
                if link.state == 0:
                    log(f"drone travou sozinho na fase {name}")
                    return
            frame = video.latest
            pygame.image.save(pygame.image.frombuffer(frame, (video.WIDTH, video.HEIGHT), "RGB"),
                              os.path.join(out, f"{name}.png"))
            g = gray(frame)
            if ref is None:
                ref = g
            log(f"{name:12} ptz1={ptz1} ptz2={ptz2}  diferença p/ referência: {np.abs(g - ref).mean():6.2f}")
    finally:
        link.safe_stop()
        for _ in range(20):
            link.tick()
        log(f"travar + emergência enviados; estado final: {link.state}")
        video.stop()
        log(f"imagens em {os.path.normpath(out)}")


if __name__ == "__main__":
    main()
