"""Teste de PTZ: varia ptz1/ptz2 no manche 0xB5 com o drone TRAVADO e mede se a imagem muda.

- Nenhum comando de destravar/decolar existe neste arquivo. Acelerador em 1000 até confirmar o drone
  travado e na saída; nas fases fica em 1500, o valor que o app envia parado (FlyCtrl.initSendData).
- Só saem pacotes da whitelist. Aborta se o drone não estiver travado ou sem telemetria.
- Em cada fase compara o vídeo com a referência (0 = idêntico) e salva um PNG em capturas/ptz_<hora>/.
Uso: python3 -P scripts/teste_camera.py  (-P: scripts/dis.py esconde o módulo dis da stdlib)
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
# (nome, ptz1, ptz2, segundos)
PHASES = [
    ("referencia", CENTER, CENTER, 4),
    ("controle", CENTER, CENTER, 3),  # mede o ruído: nada mudou em relação à referência
    # 1800/1200 são os valores que o app envia na barra do gimbal (onYuntaiProgress)
    ("ptz2_alto", CENTER, 1800, 8),
    ("ptz2_volta", CENTER, CENTER, 2),
    ("ptz2_baixo", CENTER, 1200, 8),
    ("ptz2_centro", CENTER, CENTER, 2),
]
ALLOWED = ({bt.request_telemetry(), bt.joystick(throttle=1000)}
           | {bt.joystick(throttle=CENTER, ptz1=a, ptz2=b) for _, a, b, _ in PHASES})


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

    def tick(self, ptz1=CENTER, ptz2=CENTER, throttle=1000, wait=0.05):
        self.send(bt.joystick(throttle=throttle, ptz1=ptz1, ptz2=ptz2))
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


def log(msg):
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def gray(frame):
    """Quadro RGB → cinza reduzido 8×, para a comparação ignorar ruído de pixel."""
    a = np.frombuffer(frame, np.uint8).reshape(VideoStream.HEIGHT, VideoStream.WIDTH, 3)
    return a[::8, ::8].mean(axis=2)


def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "capturas",
                       time.strftime("ptz_%H%M%S"))
    os.makedirs(out)
    link = Link()
    video = VideoStream().start()
    try:
        for _ in range(100):  # até 5 s esperando telemetria e o primeiro quadro
            link.tick()
            if link.state is not None and video.latest:
                break
        log(f"estado: {link.state} (0 = travado), vídeo: {'ok' if video.latest else 'sem quadros'}")
        if link.state != 0 or not video.latest:
            log("abortando: precisa de drone travado e vídeo")
            return

        ref = None
        for name, ptz1, ptz2, seconds in PHASES:
            end = time.time() + seconds
            while time.time() < end:
                link.tick(ptz1, ptz2, throttle=CENTER)
                if link.state != 0:
                    log(f"estado mudou para {link.state} — abortando")
                    return
            frame = video.latest
            pygame.image.save(pygame.image.frombuffer(frame, (video.WIDTH, video.HEIGHT), "RGB"),
                              os.path.join(out, f"{name}.png"))
            g = gray(frame)
            if ref is None:
                ref = g
            log(f"{name:12} ptz1={ptz1} ptz2={ptz2}  diferença p/ referência: {np.abs(g - ref).mean():6.2f}")
    finally:
        for _ in range(10):  # deixa os dois canais no centro ao sair
            link.tick()
        video.stop()
        log(f"canais no centro; imagens em {os.path.normpath(out)}")


if __name__ == "__main__":
    main()
