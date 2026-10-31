"""Controle do drone pelo computador: vídeo ao vivo, telemetria, botões e teclado.

Uso:
  python3 controle.py                   # controle completo
  python3 controle.py --somente-leitura # só vídeo + telemetria; nenhum comando de voo sai
Teclas: veja AJUDA abaixo ou a barra inferior da janela.
"""
import argparse
import os
import time

import pygame

from predator.link import Drone
from predator.video import VideoStream

VIDEO_W, VIDEO_H = 960, 540
PANEL_W = 320
BUTTONS_H = 116
HELP_H = BUTTONS_H + 74
CONFIRM_S = 1.5
SPEED_SLOW, SPEED_FAST = 200, 400  # deflexão do manche em torno de 1500
GIMBAL_UP, GIMBAL_DOWN = 1800, 1200  # valores da barra do app (onYuntaiProgress); enquanto segurar

AJUDA = [
    "ESPAÇO = EMERGÊNCIA (corta motores)   U U = destravar   J = travar   T T = decolar   L = pousar",
    "W/S = frente/trás   A/D = esquerda/direita   Q/E = girar   R/F = subir/descer   SHIFT = rápido",
    "P = pairar   H H = voltar pra casa   C = foto   V = gravar   I/K = câmera   F11 = tela cheia   ESC = sair (pousa antes)",
]

# Cada botão equivale a uma tecla, então vale a mesma confirmação em dois toques.
BUTTON_ROWS = [
    [("DESTRAVAR", pygame.K_u), ("TRAVAR", pygame.K_j), ("DECOLAR", pygame.K_t),
     ("POUSAR", pygame.K_l), ("PAIRAR", pygame.K_p), ("CASA", pygame.K_h)],
    [("CÂMERA ▲", pygame.K_i), ("CÂMERA ▼", pygame.K_k), ("FOTO", pygame.K_c), ("GRAVAR", pygame.K_v)],
]
HOLD_KEYS = (pygame.K_i, pygame.K_k)  # só agem enquanto seguradas
BUTTON_W, BUTTON_H, BUTTON_GAP = 156, 46, 8
EMERGENCY_W = 260


def build_buttons():
    """Retorna [(texto, tecla, Rect)] da barra abaixo do vídeo."""
    out = []
    for r, row in enumerate(BUTTON_ROWS):
        for c, (label, key) in enumerate(row):
            out.append((label, key, pygame.Rect(16 + c * (BUTTON_W + BUTTON_GAP),
                                                VIDEO_H + 10 + r * (BUTTON_H + BUTTON_GAP), BUTTON_W, BUTTON_H)))
    out.append(("EMERGÊNCIA", pygame.K_SPACE,
                pygame.Rect(VIDEO_W + PANEL_W - EMERGENCY_W - 16, VIDEO_H + 10, EMERGENCY_W, 2 * BUTTON_H + BUTTON_GAP)))
    return out

CAPTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "capturas")


class App:
    def __init__(self, read_only, fullscreen=False):
        self.read_only = read_only
        self.drone = Drone(read_only=read_only).start()
        self.video = VideoStream().start()
        self.flying = False  # True depois de decolar, até o drone voltar a travar
        self.takeoff_at = 0.0
        self.pending = {}  # tecla -> instante do 1º toque (confirmação dupla)
        self.messages = []
        self.exit_requested_at = None
        self.buttons = build_buttons()
        self.held_button = None  # tecla do botão seguro com o mouse

        pygame.init()
        pygame.display.set_caption("Predator — controle")
        # SCALED mantém as coordenadas lógicas: os cliques continuam certos em qualquer tamanho
        self.set_fullscreen(fullscreen)
        self.font = pygame.font.SysFont("dejavusans", 18)
        self.big = pygame.font.SysFont("dejavusans", 28, bold=True)
        self.small = pygame.font.SysFont("dejavusans", 14)
        self.say("somente leitura: comandos de voo desativados" if read_only else "pronto")

    # --- utilidades ---
    def set_fullscreen(self, on):
        self.fullscreen = on
        flags = pygame.SCALED | pygame.RESIZABLE | (pygame.FULLSCREEN if on else 0)
        self.screen = pygame.display.set_mode((VIDEO_W + PANEL_W, VIDEO_H + HELP_H), flags)

    def say(self, text):
        self.messages = (self.messages + [f"{time.strftime('%H:%M:%S')} {text}"])[-6:]

    def send(self, name):
        if self.read_only:
            self.say(f"(somente leitura) ignorado: {name}")
            return
        self.drone.command(name)
        self.say(f"enviado: {name}")

    def confirmed(self, key, label):
        """Exige dois toques na mesma tecla em até CONFIRM_S segundos."""
        now = time.time()
        if now - self.pending.get(key, 0) <= CONFIRM_S:
            self.pending.pop(key)
            return True
        self.pending[key] = now
        self.say(f"aperte de novo para {label}")
        return False

    # --- teclado ---
    def on_key(self, key):
        tel = self.drone.telemetry
        if key == pygame.K_SPACE:
            self.send("emergencia")
            self.send("travar")
            self.flying = False
        elif key == pygame.K_u and not self.drone.armed and self.confirmed(key, "DESTRAVAR"):
            self.send("destravar")
        elif key == pygame.K_j:
            if self.flying and tel.height > 0.3:
                self.say("no ar: use L para pousar (ou ESPAÇO em emergência)")
            else:
                self.send("travar")
        elif key == pygame.K_t and self.confirmed(key, "DECOLAR"):
            self.send("decolar")
            self.flying = True
            self.takeoff_at = time.time()
        elif key == pygame.K_l:
            self.send("pousar")
        elif key == pygame.K_p:
            self.send("pairar")
        elif key == pygame.K_h and self.confirmed(key, "VOLTAR PRA CASA"):
            self.send("casa")
        elif key == pygame.K_c:
            self.snapshot()
        elif key == pygame.K_v:
            path = os.path.join(CAPTURES, f"video_{time.strftime('%Y%m%d_%H%M%S')}.h264")
            started = self.video.toggle_recording(path)
            self.say(f"gravando {os.path.basename(path)}" if started else "gravação parada")
        elif key == pygame.K_F11:
            self.set_fullscreen(not self.fullscreen)
        elif key == pygame.K_ESCAPE:
            self.request_exit()

    # --- mouse ---
    def on_mouse_down(self, pos):
        for _, key, rect in self.buttons:
            if rect.collidepoint(pos):
                if key in HOLD_KEYS:
                    self.held_button = key
                else:
                    self.on_key(key)
                return

    def gimbal_value(self, k):
        if k[pygame.K_i] or self.held_button == pygame.K_i:
            return GIMBAL_UP
        if k[pygame.K_k] or self.held_button == pygame.K_k:
            return GIMBAL_DOWN
        return 1500

    def update_sticks(self):
        if self.read_only:
            return
        k = pygame.key.get_pressed()
        ptz2 = self.gimbal_value(k)
        if not self.flying:
            self.drone.set_sticks(throttle=1000, ptz2=ptz2)  # no chão: acelerador no mínimo, manche travado
            return
        d = SPEED_FAST if k[pygame.K_LSHIFT] or k[pygame.K_RSHIFT] else SPEED_SLOW
        axis = lambda plus, minus: 1500 + d * (k[plus] - k[minus])  # noqa: E731
        self.drone.set_sticks(roll=axis(pygame.K_d, pygame.K_a), pitch=axis(pygame.K_w, pygame.K_s),
                              yaw=axis(pygame.K_e, pygame.K_q), throttle=axis(pygame.K_r, pygame.K_f), ptz2=ptz2)

    # --- saída segura ---
    def request_exit(self):
        if not self.drone.armed or self.read_only or not self.drone.link_ok:
            self.exit_requested_at = 0  # pode sair já
            return
        if self.exit_requested_at:
            self.say("saindo à força: enviando pousar")
            self.send("pousar")
            self.exit_requested_at = 0
            return
        self.exit_requested_at = time.time()
        if self.flying:
            self.send("pousar")
            self.say("pousando antes de sair... (ESC de novo força a saída)")
        else:
            self.send("travar")
            self.say("travando antes de sair...")

    def should_exit(self):
        if self.exit_requested_at == 0:
            return True
        return bool(self.exit_requested_at) and not self.drone.armed

    # --- desenho ---
    def snapshot(self):
        os.makedirs(CAPTURES, exist_ok=True)
        path = os.path.join(CAPTURES, f"foto_{time.strftime('%Y%m%d_%H%M%S')}.png")
        if self.video.latest:
            img = pygame.image.frombuffer(self.video.latest, (VideoStream.WIDTH, VideoStream.HEIGHT), "RGB")
            pygame.image.save(img, path)
            self.say(f"foto: {os.path.basename(path)}")
        else:
            self.say("sem vídeo para fotografar")

    def text(self, s, pos, font=None, color=(230, 230, 230)):
        self.screen.blit((font or self.font).render(s, True, color), pos)

    def draw_buttons(self):
        now = time.time()
        for label, key, rect in self.buttons:
            waiting = now - self.pending.get(key, 0) <= CONFIRM_S
            if key == pygame.K_SPACE:
                color = (190, 30, 30)
            elif waiting:
                color, label = (190, 150, 30), "CONFIRMAR?"
            elif key == self.held_button:
                color = (60, 110, 170)
            elif key == pygame.K_v and self.video.recording:
                color, label = (150, 40, 40), "PARAR"
            else:
                color = (52, 54, 64)
            pygame.draw.rect(self.screen, color, rect, border_radius=6)
            surf = (self.big if key == pygame.K_SPACE else self.font).render(label, True, (240, 240, 240))
            self.screen.blit(surf, surf.get_rect(center=rect.center))

    def draw(self):
        self.screen.fill((18, 18, 22))
        tel, drone = self.drone.telemetry, self.drone

        if self.video.latest and time.time() - self.video.latest_time < 2:
            img = pygame.image.frombuffer(self.video.latest, (VideoStream.WIDTH, VideoStream.HEIGHT), "RGB")
            self.screen.blit(pygame.transform.smoothscale(img, (VIDEO_W, VIDEO_H)), (0, 0))
        else:
            self.text("sem vídeo (conectado no Wi-Fi do drone?)", (260, VIDEO_H // 2), self.font, (200, 120, 120))
        if self.video.recording:
            pygame.draw.circle(self.screen, (230, 40, 40), (24, 24), 9)
            self.text("REC", (40, 12), self.font, (230, 40, 40))

        x, y = VIDEO_W + 16, 14
        if not drone.link_ok:
            status, color = "SEM SINAL", (240, 80, 80)
        elif not drone.armed:
            status, color = "TRAVADO", (120, 200, 120)
        elif self.flying:
            status, color = "VOANDO", (250, 170, 40)
        else:
            status, color = "DESTRAVADO", (250, 200, 60)
        self.text(status, (x, y), self.big, color)
        y += 46
        bat = "?" if tel.battery is None else str(tel.battery)
        rows = [
            ("Bateria", bat),
            ("Satélites", f"{tel.satellites} {'(GPS ok)' if tel.gps_fix else '(sem GPS)'}"),
            ("Altura", f"{tel.height:.1f} m"),
            ("Distância", f"{tel.distance:.1f} m"),
            ("Vel. horiz.", f"{tel.h_speed:.1f} m/s"),
            ("Vel. vert.", f"{tel.v_speed:.1f} m/s"),
            ("Roll / Pitch", f"{tel.roll:+.1f}° / {tel.pitch:+.1f}°"),
            ("Yaw", f"{tel.yaw:.1f}°"),
            ("Estado/modo", f"{tel.state} / {tel.mode}"),
            ("Lat", f"{tel.lat:.6f}"),
            ("Lon", f"{tel.lon:.6f}"),
            ("Vídeo", f"{self.video.fps:.1f} fps"),
        ]
        for label, value in rows:
            self.text(label, (x, y), self.small, (150, 150, 160))
            self.text(value, (x + 110, y - 2))
            y += 26
        s = drone.sticks
        self.text(f"manche R{s['roll']} P{s['pitch']} Y{s['yaw']} A{s['throttle']}", (x, y + 4), self.small,
                  (150, 150, 160))
        y += 30
        for m in self.messages:
            line = ""
            for word in m.split(" "):
                if self.small.size(line + word)[0] > PANEL_W - 28:
                    self.text(line, (x, y), self.small, (200, 200, 120))
                    y, line = y + 18, "  "
                line += word + " "
            self.text(line, (x, y), self.small, (200, 200, 120))
            y += 18

        self.draw_buttons()
        y = VIDEO_H + BUTTONS_H + 6
        for line in AJUDA:
            self.text(line, (16, y), self.small)
            y += 22
        if self.read_only:
            self.text("MODO SOMENTE LEITURA", (16, VIDEO_H - 28), self.small, (120, 180, 250))
        pygame.display.flip()

    # --- laço principal ---
    def run(self, auto_quit_s=None, capture_path=None):
        clock = pygame.time.Clock()
        start = time.time()
        try:
            while not self.should_exit():
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.request_exit()
                    elif event.type == pygame.KEYDOWN:
                        self.on_key(event.key)
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        self.on_mouse_down(event.pos)
                    elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                        self.held_button = None
                if (self.flying and self.drone.link_ok and not self.drone.armed
                        and time.time() - self.takeoff_at > 3):
                    self.flying = False
                    self.say("drone travou (pousou)")
                self.update_sticks()
                self.draw()
                if auto_quit_s and time.time() - start > auto_quit_s:
                    if capture_path:
                        pygame.image.save(self.screen, capture_path)
                    break
                clock.tick(30)
        finally:
            if not self.read_only and self.drone.armed:
                self.drone.command("pousar" if self.flying else "travar")
                time.sleep(0.5)
            self.drone.stop()
            self.video.stop()
            pygame.quit()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--somente-leitura", action="store_true", help="não envia nenhum comando de voo")
    p.add_argument("--tela-cheia", action="store_true", help="abre em tela cheia (F11 alterna)")
    p.add_argument("--auto-sair", type=float, help="(teste) fecha sozinho após N segundos")
    p.add_argument("--captura-tela", help="(teste) salva a janela em PNG antes de fechar")
    a = p.parse_args()
    App(a.somente_leitura, a.tela_cheia).run(a.auto_sair, a.captura_tela)


if __name__ == "__main__":
    main()
