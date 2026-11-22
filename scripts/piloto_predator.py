"""Piloto do Predator pelo TECLADO, com a câmera numa janela e gravação de tudo (para treinar a IA por imitação).

Teclas:
  W frente  S trás  D direita  A esquerda   C girar à direita  Z girar à esquerda
  E SOBE (segurar: o acelerador sobe aos poucos acima de 1500)   Q DESCE (segurar: desce aos poucos)   soltou = volta a 1500
  T DESTRAVA os motores (só isso: não decola; a subida é toda sua, com E)   L pousar   X EMERGÊNCIA (corta e trava; depois dela o drone
  recusa destravar até desligar e ligar — por isso só use o X de verdade, e prefira o L)
  G manobra automática no ar (frente, trás, direita, esquerda; qualquer tecla cancela)
  H segura a posição e a altura de agora (GPS + altura; qualquer tecla de movimento solta)
  Esc pousa e sai   1 a 5 amplitude de roll/pitch (15, 20, 30, 40, 60; --forte libera 6 e 7 = 80 e 100)   F1 inverte pitch  F2 inverte roll  F3 inverte yaw  F4 inverte E/Q
SECO por padrão: sem --voar a janela, a telemetria e a gravação funcionam, mas NENHUM comando de voo ou de motor é enviado.
Com --voar --confirmo-voo manda comandos: só depois de o usuário autorizar ESTE voo, com bateria carregada, 5 m livres e o
controle físico de 2,4 GHz na mão (a prioridade dele sobre o Wi-Fi nunca foi testada).
O controle roda numa thread própria a 20 Hz; o vídeo e a gravação não atrasam as teclas.
--teclado-global lê o teclado direto de /dev/input (funciona com outra janela em foco, no Wayland), MAS aí qualquer letra digitada em
qualquer lugar vira comando de voo. Por isso começa DESLIGADO e só liga com F12 (F12 de novo desliga; desliga sozinho ao pousar).
Precisa de permissão de leitura em /dev/input: `sudo usermod -aG input $USER` e entrar de novo na sessão.
Segurança embutida: link perdido > 1 s, inclinação > 40° ou distância > 8 m mandam pousar. E/Q só mexem no acelerador de 1350 a 1650.
Teclas = manche analógico: segurar leva a força a 100 % da amplitude em ~0,25 s, soltar volta a 0 (100 unidades = 100 %).
Grava com --gravar em capturas/piloto_<hora>/: dados.csv (tecla, comando, fase, telemetria, força em %) e um jpg a cada 0,2 s.
--app = sensibilidade do aplicativo no modo de velocidade baixa: WASD e C/Z vão direto ao manche cheio do app (±250 µs), sem rampa.
  As teclas 1–5 continuam reduzindo a amplitude se precisar. E/Q (acelerador) não mudam.
Uso (venv do OpenCV): ~/.local/share/aruco-venv/bin/python -P scripts/piloto_predator.py [--gravar] [--voar --confirmo-voo] [--teclado-global]
"""
import argparse
import collections
import base64
import csv
import glob
import math
import os
import queue
import struct
import sys
import threading
import time
import tkinter as tk

import cv2
import numpy as np

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, RAIZ)
from predator import suave, teclado  # noqa: E402
import predator.link as _link  # noqa: E402
from predator.link import Drone  # noqa: E402
_link.TELEMETRY_PERIOD = 0.1  # como os scripts que destravam em 0,2 s (Link de voo_1m.py pede telemetria a cada 0,1 s; o Drone pedia a cada 0,5 s)
from predator.video import VideoStream  # noqa: E402
from predator.voz import falar  # noqa: E402

PRESETS_TODOS = (15, 20, 30, 40, 60, 80, 100)
AMP_APP = 250  # manche cheio do app no modo lento (desvio 500 × 0,5)
PRESETS = PRESETS_TODOS[:5]  # 80 e 100 só com --forte
MIN_SATS = 8
LIMITE_TILT, LIMITE_DIST, LIMITE_LINK = 40.0, 8.0, 1.0
DESCER_US = 1300
ACEL_SOBE_MAX, ACEL_DESCE_MAX, ACEL_TAXA = 150, 200, 50  # µs acima/abaixo de 1500; µs por segundo com a tecla segurada
# --app, depois de sair do chão: E/Q como o manche cheio do app no modo lento (±250), chegando lá em ~0,4 s.
# Na decolagem continua a rampa lenta acima (21/11 decolou bem assim; 20/11 um pulso de 1650 direto capotou).
ACEL_APP_MAX, ACEL_APP_TAXA = 250, 600
# G = manobra automática (só no ar): cada passo é (segundos, teclas). Qualquer tecla de movimento sua cancela na hora.
MANOBRA = [(1.0, ""), (1.5, "w"), (3.0, ""), (1.5, "s"), (3.0, ""), (1.5, "d"), (3.0, ""), (1.5, "a"), (3.0, "")]
NOMES = {"w": "frente", "s": "trás", "d": "direita", "a": "esquerda", "": "pairando"}
CICLO_S = 0.05
# pouso: "no chão" = 2 s com a atitude quase imóvel, sem velocidade vertical e altura perto de 0 (21/11: no ar o roll variou ±3°,
# no chão 0,0–0,4°). Então acelerador no MÍNIMO e travar a cada 0,1 s, como armar.travar (com 1300 o drone ignorou o travar por 35 s
# e acabou tombando). Se não travar em 3 s no chão, corta (emergência).
CHAO_JANELA_S, CHAO_VAR_GRAUS, CHAO_VV, CHAO_ALTURA, TRAVAR_MAX_S = 2.0, 0.8, 0.15, 0.5, 3.0


def no_chao(hist, agora):
    """hist: (t, roll, pitch, v_vert, altura) dos últimos segundos. True se os últimos CHAO_JANELA_S parecem drone parado no chão."""
    if not hist or agora - hist[0][0] < CHAO_JANELA_S:
        return False
    w = [h for h in hist if agora - h[0] <= CHAO_JANELA_S]
    if len(w) < 10:
        return False
    rs, ps = [h[1] for h in w], [h[2] for h in w]
    return (max(rs) - min(rs) <= CHAO_VAR_GRAUS and max(ps) - min(ps) <= CHAO_VAR_GRAUS
            and all(abs(h[3]) <= CHAO_VV for h in w) and all(h[4] <= CHAO_ALTURA for h in w))


def no_chao_tremendo(hist, agora, janela=3.0, var=6.0, faixa_h=0.5):
    """Estado 5 (21/11): no chão os motores seguem girando e o drone treme 1–5°, e o no_chao() demorou 28 s.
    Aqui: 3 s com altura parada (faixa ≤ 0,5 m) e baixa, e inclinação variando no máximo 6°. Nos voos gravados de 21/11
    não disparou com o drone no ar acima de 0,5 m (o balanço de 37° a ~1 m do 4º voo ficou de fora)."""
    if not hist or agora - hist[0][0] < janela:
        return False
    w = [h for h in hist if agora - h[0] <= janela]
    if len(w) < 15:
        return False
    rs, ps, hs = [h[1] for h in w], [h[2] for h in w], [h[4] for h in w]
    return (max(rs) - min(rs) <= var and max(ps) - min(ps) <= var
            and max(hs) - min(hs) <= faixa_h and max(hs) <= CHAO_ALTURA)
SOBE_PCT, DESCE_PCT = 4.0, 6.0  # frações do preset por segundo (manche analógico: segurar sobe a força, soltar desce)

ap = argparse.ArgumentParser()
ap.add_argument("--voar", action="store_true", help="sem isso nunca manda comando de voo ou de motor")
ap.add_argument("--confirmo-voo", action="store_true", help="junto com --voar: o usuário autorizou ESTE voo")
ap.add_argument("--gravar", action="store_true")
ap.add_argument("--amp", type=int, default=40, choices=PRESETS_TODOS + (AMP_APP,))
ap.add_argument("--forte", action="store_true", help="libera as amplitudes 80 e 100 (teclas 6 e 7); o padrão vai até 60")
ap.add_argument("--amp-yaw", type=int, default=40)
ap.add_argument("--roteiro-foto", action="store_true", help="voo automático: destrava, sobe, tira foto lá de cima, desce com Q e perto do chão aciona o pouso; qualquer tecla sua cancela e você assume")
ap.add_argument("--web", action="store_true", help="painel no navegador (http://127.0.0.1:8777) no lugar da janela simples")
ap.add_argument("--porta", type=int, default=8777)
ap.add_argument("--sem-navegador", action="store_true", help="com --web: não abre o navegador (o app do GNOME mostra o painel)")
ap.add_argument("--gestos", action="store_true", help="gestos de braço pela câmera do drone: braço esticado = aproximar, Cristo = afastar, casinha = segurar (rodar com o Python de gestos/.venv)")
ap.add_argument("--manobra", action="store_true", help="com --roteiro-foto: depois de subir, faz a manobra G (frente, trás, direita, esquerda) e desce")
ap.add_argument("--pairar", type=float, default=0.0, help="com --roteiro-foto: depois de subir, segura posição e altura por N s (testa o modo H)")
ap.add_argument("--ida-volta", type=float, default=0.0, help="com --roteiro-foto: depois da foto, mover_para(frente=N m), pausa, volta à origem (GPS) e desce")
ap.add_argument("--alvo-altura", type=float, default=3.0, help="altura (telemetria, m) em que o roteiro para de subir")
ap.add_argument("--basico", action="store_true", help="só W/A/S/D e E/Q mexem no drone (mais T, L, X, Esc); C/Z, 1–7 e F1–F4 ficam desligados")
ap.add_argument("--app", action="store_true", help="WASD/C/Z = manche cheio do app no modo lento (±250), sem rampa")
ap.add_argument("--min-bateria", type=int, default=30)
ap.add_argument("--teclado-global", action="store_true", help="lê o teclado de /dev/input; começa desligado, liga com F12")
ap.add_argument("--auto-sair", type=float, default=0, help="TESTE: fecha sozinho depois de N segundos")
a = ap.parse_args()
if a.forte:
    PRESETS = PRESETS_TODOS
if a.app:
    PRESETS = PRESETS[:5] + (AMP_APP,)
    a.amp, a.amp_yaw = AMP_APP, AMP_APP
    SOBE_PCT = DESCE_PCT = 1.0 / CICLO_S  # tecla = manche cheio no ciclo seguinte, como o dedo no app
if a.amp not in PRESETS:
    sys.exit("--amp acima de 60 exige --forte (ou use --app)")
if a.roteiro_foto and not a.gravar:
    a.gravar = True  # as fotos vão para a pasta da gravação
if a.voar and not a.confirmo_voo:
    sys.exit("--voar exige --confirmo-voo (só depois de o usuário autorizar este voo)")
VOAR = a.voar and a.confirmo_voo

# códigos de tecla do Linux (input-event-codes.h) → nome
CODIGOS = {17: "w", 30: "a", 31: "s", 32: "d", 18: "e", 16: "q", 46: "c", 44: "z", 20: "t", 34: "g", 35: "h", 38: "l", 45: "x", 1: "escape",
           2: "1", 3: "2", 4: "3", 5: "4", 6: "5", 7: "6", 8: "7", 59: "f1", 60: "f2", 61: "f3", 62: "f4", 88: "f12"}


def _metros(a_, b_):
    dn = (a_[0] - b_[0]) * 111320
    de = (a_[1] - b_[1]) * 111320 * math.cos(math.radians(a_[0]))
    return math.hypot(dn, de)


# --- gestos (projeto ../gestos): braço levantado = aproximar, braços abertos = afastar, casinha (triângulo) = segurar ---
GESTOS_DIR = os.path.abspath(os.path.join(RAIZ, "..", "gestos"))
ACOES_GESTO = {"braco_levantado": ("aproximar", 3.0), "bracos_abertos": ("afastar", -3.0), "triangulo": ("segurar", None)}
GESTO_INTERVALO_S = 4.0  # entre dois comandos por gesto


class Piloto:
    def __init__(self):
        self.drone = Drone(read_only=not VOAR).start()
        self.video = VideoStream().start()
        self.fase, self.t_fase = "chao", time.time()
        self._teclas_lock = threading.RLock()
        self.teclas = set()
        self.preset = PRESETS.index(a.amp)
        self.sinais = [1, 1, 1, 1]  # pitch, roll, yaw, acelerador
        self.acel_dev = 0.0         # µs acima/abaixo de 1500, sobe aos poucos enquanto E/Q está segurada
        self.forca = [0.0, 0.0, 0.0]  # roll, pitch, yaw suavizados em [-1, 1] (fração da amplitude escolhida)
        self.cmd = {"roll": 1500, "pitch": 1500, "yaw": 1500, "throttle": 1000}
        self.aviso = ""
        self.partida = None
        self.ultimo_comando = 0.0
        self.sair = False
        self.global_ativo = False
        self.global_msg = ""
        self.bloqueio_emerg = False  # depois do X o drone recusou destravar até ser desligado e ligado (20/11)
        self.png = None
        self.hist = collections.deque(maxlen=400)  # 3 s a 20 Hz cabem com folga
        self.t_travando = None
        self.no_ar = False
        self.t_auto = None
        self.roteiro = False
        self.fotos = []
        self.auto_manche = None   # desvios (roll, pitch, acel) mandados pelo roteiro/mover_para; teclas suas têm prioridade
        self.t_tombo = None
        self.pessoa = None
        self.tronco_perto = 0.16
        self.acel_pouso = None    # desvio do acelerador na fase de pouso (roteiro: descida lenta até tocar)
        self.fila = queue.Queue(maxsize=80)
        self.n_quadro, self.t_quadro = 0, 0.0
        self.csv = self.pasta = None
        if a.gravar:
            self.pasta = os.path.join(RAIZ, "capturas", time.strftime("piloto_%m%d_%H%M%S"))
            os.makedirs(self.pasta)
            self._arq = open(os.path.join(self.pasta, "dados.csv"), "w", newline="")
            self.csv = csv.writer(self._arq)
            self.csv.writerow(["t", "fase", "teclas", "roll_us", "pitch_us", "yaw_us", "acel_us", "estado", "modo", "roll", "pitch",
                               "yaw", "altura", "v_vert", "v_hor", "distancia", "satelites", "bateria", "lat", "lon", "quadro", "aviso", "roll_pct", "pitch_pct", "yaw_pct", "acel_pct"])
            threading.Thread(target=self._escritor, daemon=True).start()
        threading.Thread(target=self._laco_controle, daemon=True).start()
        threading.Thread(target=self._laco_imagem, daemon=True).start()
        self.gesto_txt, self.t_ult_gesto = "", 0.0
        if a.gestos:
            threading.Thread(target=self._laco_gestos, daemon=True).start()

    # --- imagem e gravação em threads próprias (não atrasam o controle) ---
    def _quadro_rgb(self):
        buf = self.video.latest
        return None if buf is None else np.frombuffer(buf, np.uint8).reshape(self.video.HEIGHT, self.video.WIDTH, 3)

    def _laco_imagem(self):
        while True:
            rgb = self._quadro_rgb()
            if rgb is not None:
                pequeno = cv2.resize(rgb, (960, 540), interpolation=cv2.INTER_AREA)
                ok, png = cv2.imencode(".png", cv2.cvtColor(pequeno, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_PNG_COMPRESSION, 1])
                if ok:
                    self.png = base64.b64encode(png.tobytes())
            time.sleep(0.08)

    def _laco_gestos(self):
        """Lê a pose no quadro mais recente (~18 q/s no notebook), classifica e confirma pelo tempo (projeto gestos)."""
        try:
            if GESTOS_DIR not in sys.path:
                sys.path.append(GESTOS_DIR)
            import joblib
            from gestos import config as GC
            from gestos.deteccao import Detector
            from gestos.logica import Confirmador, classificar
            det, clf, conf = Detector(mao=False, corpo=True), joblib.load(GC.CLASSIFICADOR_CORPO), Confirmador()
        except Exception as e:  # sem MediaPipe: rode com gestos/.venv/bin/python
            self.gesto_txt = f"gestos DESLIGADOS: {e}"
            return
        self.tronco_perto = GC.TRONCO_PERTO
        ultimo = None
        while True:
            buf = self.video.latest
            if buf is None or buf is ultimo:
                time.sleep(0.01)
                continue
            ultimo = buf
            rgb = np.frombuffer(buf, np.uint8).reshape(self.video.HEIGHT, self.video.WIDTH, 3)
            t = time.time()
            feat, _, pessoa = det.corpo_em(rgb)
            gesto, prob = classificar(clf, feat)
            confirmado = conf.atualizar(gesto, prob, t)
            self.pessoa = pessoa
            self.gesto_txt = ("sem pessoa" if pessoa is None else
                              f"{gesto} {prob:.2f}  tronco {pessoa['tronco']:.3f}  x {pessoa['cx']:.2f}")
            if confirmado in ACOES_GESTO:
                self.acao_gesto(confirmado)

    def acao_gesto(self, gesto):
        acao, frente = ACOES_GESTO[gesto]
        agora = time.time()
        if agora - self.t_ult_gesto < GESTO_INTERVALO_S:
            return
        self.t_ult_gesto = agora
        pronto = VOAR and self.fase == "voando" and self.no_ar and not self.roteiro and not self.teclas_atuais()
        if not pronto:
            self.aviso = f"GESTO {gesto} → {acao} (só mostrando: {'seco' if not VOAR else 'drone no chão ou ocupado'})"
            return
        if acao == "aproximar" and self.pessoa and self.pessoa["tronco"] > self.tronco_perto:
            self.aviso = "GESTO aproximar RECUSADO: a pessoa já está perto"
            return
        if acao == "segurar":
            self.iniciar_segurar()
            return

        def mover():
            self.roteiro = True
            try:
                log = lambda m: (setattr(self, "aviso", "GESTO: " + m), print(time.strftime("%H:%M:%S"), m, flush=True))  # noqa: E731
                log(f"{gesto} → {acao}: mover_para(frente={frente:+.0f})")
                r = mover_para(self, log, 15.0, frente=frente, altura=self.drone.telemetry.height)
                log(f"{acao}: {'chegou' if r is True else r}; pairando")
            finally:
                self.roteiro = False
                self.auto_manche = None
        threading.Thread(target=mover, daemon=True).start()

    def _escritor(self):
        while True:
            nome, rgb = self.fila.get()
            ok, jpg = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                with open(os.path.join(self.pasta, nome), "wb") as f:
                    f.write(jpg.tobytes())

    # --- teclas (da janela ou do teclado global) ---
    def teclas_atuais(self):
        with self._teclas_lock:
            return set(self.teclas)

    def adicionar_tecla(self, k):
        with self._teclas_lock:
            self.teclas.add(k)

    def remover_tecla(self, k):
        with self._teclas_lock:
            self.teclas.discard(k)

    def limpar_teclas(self):
        with self._teclas_lock:
            self.teclas.clear()

    def tecla_baixo(self, k, auto=False):
        estava_auto = self.roteiro
        if not auto and self.roteiro:
            self.roteiro = False
            self.auto_manche = None
            self.acel_pouso = None
            self.remover_tecla("e")
            self.remover_tecla("q")
            self.aviso = "ROTEIRO CANCELADO pela sua tecla: você pilota"
        if a.basico and k in {"c", "z", "1", "2", "3", "4", "5", "6", "7", "f1", "f2", "f3", "f4"}:
            return
        if k in {"w", "a", "s", "d", "e", "q", "c", "z"} and self.t_auto is not None:
            self.t_auto = None
            self.aviso = "manobra automática CANCELADA: você pilota"
        if k == "g":
            self.iniciar_manobra()
            return
        if k == "h":
            if not estava_auto:  # H de novo (com o segurar ligado) só solta
                self.iniciar_segurar()
            return
        if k in {"w", "a", "s", "d", "e", "q", "c", "z"}:
            if self.fase == "pousando" and self.t_travando is None and k != "q":
                self.mudar_fase("voando", "pouso CANCELADO pela tecla: você pilota de novo")
            self.adicionar_tecla(k)
        elif k == "t":
            self.decolar()
        elif k == "l":
            self.pousar()
        elif k == "x":
            self.emergencia()
        elif k in {"1", "2", "3", "4", "5", "6", "7"} and int(k) - 1 < len(PRESETS):
            self.preset = int(k) - 1
        elif k in ("f1", "f2", "f3", "f4"):
            i = {"f1": 0, "f2": 1, "f3": 2, "f4": 3}[k]
            self.sinais[i] = -self.sinais[i]
        elif k == "escape":
            self.sair = True
            self.pousar("saindo")

    def tecla_cima(self, k):
        self.remover_tecla(k)

    def foto(self, nome):
        rgb = self._quadro_rgb()
        if rgb is None or not self.pasta:
            return None
        caminho = os.path.join(self.pasta, nome)
        cv2.imwrite(caminho, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 95])
        self.fotos.append(caminho)
        return caminho

    # --- fases ---
    def iniciar_manobra(self):
        if self.fase != "voando" or not self.no_ar:
            self.aviso = "G só funciona com o drone no ar (decole e solte as teclas)"
            return
        if self.teclas_atuais():
            self.aviso = "G: solte as teclas primeiro"
            return
        self.t_auto = time.time()
        self.aviso = "MANOBRA AUTOMÁTICA: frente, trás, direita, esquerda (qualquer tecla cancela)"

    def iniciar_segurar(self):
        """H: segura a coordenada e a altura de agora (mover_para para o próprio lugar), até uma tecla sua ou o pouso."""
        if self.fase != "voando" or not self.no_ar:
            self.aviso = "H só funciona com o drone no ar"
            return
        if self.roteiro:
            return
        self.limpar_teclas()
        threading.Thread(target=segurar_posicao, args=(self,), daemon=True).start()

    def teclas_auto(self, agora):
        """Teclas da manobra neste instante, ou None quando acabou."""
        dt = agora - self.t_auto
        for dur, k in MANOBRA:
            if dt < dur:
                return k
            dt -= dur
        return None

    def mudar_fase(self, f, aviso=""):
        self.fase, self.t_fase = f, time.time()
        self.t_auto = None
        if f != "voando":
            self.auto_manche = None
        if f != "pousando":
            self.acel_pouso = None
        if f in ("armando", "chao"):
            self.no_ar = False
        self.hist.clear()
        self.t_travando = None
        if aviso:
            self.aviso = aviso
        if VOAR and f in ("armando", "pousando", "chao"):
            falar({"armando": "destravando", "pousando": "pousando", "chao": "pousou"}[f])
        if f == "chao":
            self.global_ativo = False

    def checagem(self):
        t = self.drone.telemetry
        p = []
        if not self.drone.link_ok:
            p.append("sem telemetria")
        if t.state != 0:
            p.append("não está travado")
        if not t.gps_fix or t.satellites < MIN_SATS:
            p.append("GPS fraco")
        if t.battery is None or t.battery < a.min_bateria:
            p.append("bateria baixa")
        if max(abs(t.roll), abs(t.pitch)) > 10:
            p.append("drone inclinado")
        return p

    def decolar(self):
        """T: SÓ destrava. Quem sobe é você, com E."""
        if self.fase != "chao":
            return
        if not VOAR:
            self.aviso = "SECO: T não envia nada (use --voar --confirmo-voo)"
            return
        if self.bloqueio_emerg and self.drone.telemetry.mode != 1:
            self.aviso = "T recusado: depois da EMERGÊNCIA o drone não destrava; DESLIGUE e LIGUE o drone (modo deve voltar a 1)"
            return
        self.bloqueio_emerg = False
        problemas = self.checagem()
        if problemas:
            self.aviso = "T recusado: " + ", ".join(problemas)
            return
        self.partida = (self.drone.telemetry.lat, self.drone.telemetry.lon)
        self.mudar_fase("armando", "destravando...")

    def pousar(self, motivo="pedido"):
        if self.fase in ("voando", "armando"):
            self.mudar_fase("pousando", f"pousando ({motivo})")

    def emergencia(self):
        if VOAR:
            self.drone.command("emergencia", repeat=5)
            self.drone.command("travar", repeat=3)
        self.bloqueio_emerg = VOAR
        self.mudar_fase("chao", "EMERGÊNCIA: o drone só destrava de novo depois de desligar e ligar")

    def seguranca(self):
        t = self.drone.telemetry
        if self.fase != "voando":
            return
        if not self.drone.link_ok:
            self.pousar("telemetria parada")
        elif max(abs(t.roll), abs(t.pitch)) > LIMITE_TILT:
            self.pousar("inclinação alta")
        elif self.partida and _metros((t.lat, t.lon), self.partida) > LIMITE_DIST:
            self.pousar("afastou demais")

    # --- controle: thread própria a 20 Hz ---
    def _laco_controle(self):
        ant = time.time()
        while True:
            t0 = time.time()
            try:
                self.ciclo(t0, t0 - ant)
            except Exception as e:  # nunca deixa a thread morrer com o drone armado
                self.aviso = f"erro no ciclo: {e}"
            ant = t0
            time.sleep(max(0.0, CICLO_S - (time.time() - t0)))

    def ciclo(self, agora, dt_ciclo):
        t, dt = self.drone.telemetry, agora - self.t_fase
        self.seguranca()
        sticks = {"roll": 1500, "pitch": 1500, "yaw": 1500, "throttle": 1000}
        teclas = self.teclas_atuais()
        if self.fase == "armando":
            # como nos scripts que destravam em 0,2 s (voo_1m/destravar.py): comando a cada 0,1 s, alternando com o manche mínimo
            if agora - self.ultimo_comando > 0.1:
                self.drone.command("destravar", repeat=1)
                self.ultimo_comando = agora
            if self.drone.armed:
                self.acel_dev = 0.0
                self.mudar_fase("voando", "DESTRAVADO: você pilota (E sobe devagar, 50 µs/s)")
            elif dt > 4:
                self.mudar_fase("chao", f"não destravou em 4 s (estado {t.state}, bateria {t.battery}); tente T de novo")
        elif self.fase == "voando":
            if not self.no_ar and (t.v_speed > 0.3 or t.height > 0.4 or max(abs(t.roll), abs(t.pitch)) > 8):
                self.no_ar = True
                self.aviso = "NO AR" + (": E/Q agora rápidos (±250)" if a.app else "")
            if self.t_auto is not None:
                k = self.teclas_auto(agora)
                if k is None:
                    self.t_auto = None
                    self.aviso = "manobra automática terminou: você pilota"
                else:
                    teclas = set(k)
                    self.aviso = f"AUTO: {NOMES[k]} (qualquer tecla cancela)"
            amp = PRESETS[self.preset]
            alvo = teclado.comando_teclas(teclas, amp, a.amp_yaw, 0, tuple(self.sinais))
            ref = (amp, amp, a.amp_yaw)
            for i in range(3):
                meta = alvo[i] / ref[i] if ref[i] else 0.0
                f = self.forca[i]
                taxa = (SOBE_PCT if abs(meta) > abs(f) or meta * f < 0 else DESCE_PCT) * dt_ciclo
                self.forca[i] = f + max(-taxa, min(taxa, meta - f))
            dev = (self.forca[0] * ref[0], self.forca[1] * ref[1], self.forca[2] * ref[2], 0)
            sobe = ("e" in teclas) - ("q" in teclas)
            if sobe:
                rapido = a.app and self.no_ar
                taxa, sobe_max, desce_max = (ACEL_APP_TAXA, ACEL_APP_MAX, ACEL_APP_MAX) if rapido else (ACEL_TAXA, ACEL_SOBE_MAX, ACEL_DESCE_MAX)
                self.acel_dev += self.sinais[3] * sobe * taxa * dt_ciclo
                self.acel_dev = max(-desce_max, min(sobe_max, self.acel_dev))
            else:
                self.acel_dev = 0.0  # soltou: volta a 1500 (o drone mantém a altura)
            sticks = teclado.para_manche((dev[0], dev[1], dev[2], self.acel_dev))
            am = self.auto_manche
            if am is not None and not teclas:
                sticks = teclado.para_manche((am["roll"], am["pitch"], 0, am["acel"]))
        elif self.fase == "pousando":
            self.acel_dev = 0.0
            self.forca = [0.0, 0.0, 0.0]
            sticks = {"roll": 1500, "pitch": 1500, "yaw": 1500, "throttle": DESCER_US if dt > 5 else 1500}
            if self.acel_pouso is not None:
                sticks["throttle"] = int(1500 + self.acel_pouso)
            if self.drone.link_ok:
                self.hist.append((agora, t.roll, t.pitch, t.v_speed, t.height))
                # capotando no pouso (21/11: balançou a 37° no estado 5): > 60° por 0,3 s corta, como o voo_1m
                if max(abs(t.roll), abs(t.pitch)) > 60:
                    self.t_tombo = self.t_tombo or agora
                    if agora - self.t_tombo > 0.3:
                        self.emergencia()
                        self.aviso = "CAPOTANDO no pouso: motores CORTADOS (desligue e ligue o drone antes do próximo voo)"
                        return
                else:
                    self.t_tombo = None
            if self.t_travando is None and dt > 1 and (no_chao(self.hist, agora) or no_chao_tremendo(self.hist, agora)):
                self.t_travando = agora
                self.aviso = "no chão: acelerador no mínimo e travando"
            if self.t_travando is not None:
                sticks["throttle"] = 1000
                if agora - self.ultimo_comando > 0.1:
                    self.drone.command("travar", repeat=1)
                    self.ultimo_comando = agora
                if agora - self.t_travando > TRAVAR_MAX_S and t.state != 0:
                    self.emergencia()
                    self.aviso = "no chão e não travou em 3 s: motores CORTADOS (desligue e ligue o drone antes do próximo voo)"
            elif self.acel_pouso is None and agora - self.ultimo_comando > 1.0:  # descida do roteiro: velocidade é nossa
                self.drone.command("pousar", repeat=1)
                self.ultimo_comando = agora
            if t.state == 0 and self.drone.link_ok and dt > 1:
                self.mudar_fase("chao", "pousou e travou")
        self.cmd = sticks
        if VOAR:
            self.drone.set_sticks(**sticks)
        self.gravar(agora, sticks, teclas)

    def gravar(self, agora, s, teclas):
        if not self.csv:
            return
        t = self.drone.telemetry
        quadro = ""
        if agora - self.t_quadro >= 0.2 and not self.fila.full():
            rgb = self._quadro_rgb()
            if rgb is not None:
                self.n_quadro += 1
                self.t_quadro = agora
                quadro = f"quadro_{self.n_quadro:06d}.jpg"
                self.fila.put((quadro, rgb.copy()))
        self.csv.writerow([f"{agora:.3f}", self.fase, "".join(sorted(teclas)), s["roll"], s["pitch"], s["yaw"], s["throttle"],
                           t.state, t.mode, t.roll, t.pitch, t.yaw, t.height, t.v_speed, t.h_speed, t.distance, t.satellites,
                           t.battery, t.lat, t.lon, quadro, self.aviso,
                           s['roll'] - 1500, s['pitch'] - 1500, s['yaw'] - 1500, s['throttle'] - 1500])
        self._arq.flush()

    def encerrar(self):
        self.video.stop()
        self.drone.stop()
        if self.csv:
            self._arq.close()


ALTURA_FINAL = 0.4     # m (telemetria): mover_para desce suave até aqui; daí encosta a TOQUE_M_S até o detector de chão travar
TOQUE_M_S = 0.12       # m/s na encostada final (≈ −115 µs pelo ganho medido de descida)


def mover_para(P, log, timeout, **alvo):
    """Comando da biblioteca (predator.suave.MoverPara) rodando no piloto: da posição atual ao alvo, suave.
    Devolve True (chegou), False (tempo esgotado), None (roteiro cancelado ou segurança mandou pousar) ou "estado5"."""
    tel = P.drone.telemetry
    try:
        m = suave.MoverPara(tel, **alvo)
    except ValueError as error:
        log(f"mover_para recusado: {error}; pousando")
        P.auto_manche = None
        P.pousar("GPS inválido")
        return None
    t_ant, t_ini, t_chegou = time.time(), time.time(), None
    while True:
        tel = P.drone.telemetry
        if not P.roteiro or P.fase != "voando":
            P.auto_manche = None
            return None
        if tel.state == 5:
            return "estado5"
        agora = time.time()
        out = m.passo(agora, tel, agora - t_ant)
        t_ant = agora
        if not out["gps_ok"]:
            log("GPS perdido durante mover_para; pousando")
            P.auto_manche = None
            P.pousar("GPS perdido")
            return None
        P.auto_manche = out
        if out["chegou"]:
            t_chegou = t_chegou or agora
            if agora - t_chegou >= 0.5:
                P.auto_manche = {"roll": 0.0, "pitch": 0.0, "acel": 0.0}
                return True
        else:
            t_chegou = None
        if agora - t_ini > timeout:
            P.auto_manche = {"roll": 0.0, "pitch": 0.0, "acel": 0.0}
            return False
        time.sleep(0.05)


def segurar_posicao(P, duracao=None, log=None):
    """Fica no mesmo lugar e na mesma altura: mover_para com alvo = onde o drone está agora, sem nunca "chegar".
    Corrige a altura sempre (tolerância 0,1 m) e a posição só se derivar mais de 1,2 m (o GPS erra 0,3–4 m parado).
    Sai com tecla sua, pouso, `duracao` esgotada ou estado 5 (aí o firmware manda: parece retorno por bateria baixa)."""
    log = log or (lambda m: (setattr(P, "aviso", "SEGURAR: " + m), print(time.strftime("%H:%M:%S"), m, flush=True)))
    dono = not P.roteiro
    P.roteiro = True
    tel = P.drone.telemetry
    h0 = tel.height
    try:
        m = suave.MoverPara(tel, altura=h0, norte=0.0, leste=0.0, tol_v=0.1, tol_h=1.2)
    except ValueError as error:
        log(f"não pode segurar posição: {error}; pousando")
        P.auto_manche = None
        if dono:
            P.roteiro = False
        P.pousar("GPS inválido")
        return "GPS inválido"
    log(f"segurando altura {h0:.1f} m e esta coordenada (qualquer tecla de movimento solta)")
    t_ant = t_ini = time.time()
    motivo = "tempo"
    while True:
        tel = P.drone.telemetry
        if not P.roteiro or P.fase != "voando":
            motivo = "tecla ou pouso"
            break
        if tel.state == 5:
            motivo = "estado5"
            log("estado 5: o drone assumiu (bateria baixa); não dá para segurar contra ele")
            break
        agora = time.time()
        out = m.passo(agora, tel, agora - t_ant)
        t_ant = agora
        if not out["gps_ok"]:
            motivo = "GPS perdido"
            log("GPS perdido enquanto segurava posição; pousando")
            P.auto_manche = None
            P.pousar(motivo)
            break
        P.auto_manche = out
        if duracao and agora - t_ini > duracao:
            break
        time.sleep(0.05)
    P.auto_manche = {"roll": 0.0, "pitch": 0.0, "acel": 0.0} if P.fase == "voando" and P.roteiro else None
    if dono:
        P.roteiro = False
        P.auto_manche = None
    return motivo


def roteiro_foto(P):
    """Sobe com mover_para, tira foto lá de cima, desce com mover_para (freando perto do chão), encosta devagar e trava.
    Qualquer tecla sua cancela e você assume; segurança que manda pousar também encerra o roteiro."""
    def esperar(seg, cond=None):
        fim = time.time() + seg
        while time.time() < fim:
            if not P.roteiro:
                return None
            if cond and cond():
                return True
            time.sleep(0.05)
        return False

    def log(msg):
        P.aviso = "ROTEIRO: " + msg
        print(time.strftime("%H:%M:%S"), msg, flush=True)

    def pousar_suave(motivo):
        log(f"{motivo}: encostando a {TOQUE_M_S:.2f} m/s até o chão")
        P.acel_pouso = -TOQUE_M_S / suave.DESCE_M_S_POR_US
        P.pousar("roteiro")
        while P.roteiro and P.fase != "chao":
            time.sleep(0.1)
        P.roteiro = False
        log(f"fim: fase {P.fase}, estado {P.drone.telemetry.state}")

    P.roteiro = True
    if esperar(4.0, lambda: P.drone.link_ok and P.video.latest is not None and P.drone.telemetry.battery is not None) is None:
        return
    P.foto("foto_chao.jpg")
    log("destravando (T)")
    P.tecla_baixo("t", auto=True)
    if not esperar(5.0, lambda: P.fase == "voando"):
        P.roteiro = False
        log(f"não destravou; parado ({P.aviso})")
        return
    log("subindo devagar (E) até sair do chão")
    P.adicionar_tecla("e")
    ok = esperar(8.0, lambda: P.no_ar)
    P.remover_tecla("e")
    if ok is None:
        return
    if not ok:
        log("não saiu do chão em 8 s: pousando")
        P.pousar("roteiro: não decolou")
        P.roteiro = False
        return
    log(f"no ar; mover_para(altura={a.alvo_altura:.1f})")
    r = mover_para(P, log, 10.0, altura=a.alvo_altura)
    if r is None:
        return
    if r == "estado5":
        return pousar_suave("estado 5 na subida (bateria baixa)")
    log(f"{'chegou' if r else 'tempo esgotado'} a {P.drone.telemetry.height:.1f} m; pairando")
    if a.manobra:
        log("manobra: frente, trás, direita, esquerda (1,5 s cada, 3 s parado entre elas)")
        P.auto_manche = None
        P.iniciar_manobra()
        if esperar(25.0, lambda: P.t_auto is None or P.fase != "voando") is None:
            return
        if P.fase != "voando":
            P.roteiro = False
            return
        t = P.drone.telemetry
        log(f"manobra terminou; distância da partida {t.distance:.1f} m; descendo")
    if a.pairar > 0:
        mot = segurar_posicao(P, duracao=a.pairar, log=log)
        if mot == "estado5":
            return pousar_suave("estado 5 segurando a posição")
        if not P.roteiro:
            return
    if esperar(3.0) is None:
        return
    c = P.foto("foto_alto.jpg")
    log(f"foto tirada a {P.drone.telemetry.height:.1f} m ({c}); pairando mais 2 s")
    if esperar(2.0) is None:
        return
    if a.ida_volta > 0:
        h = P.drone.telemetry.height
        log(f"mover_para(frente={a.ida_volta:.1f}) mantendo {h:.1f} m")
        r = mover_para(P, log, 20.0, frente=a.ida_volta, altura=h)
        if r is None:
            return
        if r == "estado5":
            return pousar_suave("estado 5 na ida (bateria baixa)")
        t = P.drone.telemetry
        log(f"ida: {'chegou' if r else 'tempo esgotado'}; distância da origem {t.distance:.1f} m; pairando 3 s")
        P.foto("foto_frente.jpg")
        if esperar(3.0) is None:
            return
        log("mover_para(origem): voltando ao ponto de partida")
        r = mover_para(P, log, 25.0, norte=0.0, leste=0.0, origem=P.partida, altura=h)
        if r is None:
            return
        if r == "estado5":
            return pousar_suave("estado 5 na volta (bateria baixa)")
        t = P.drone.telemetry
        log(f"volta: {'chegou' if r else 'tempo esgotado'}; distância da origem {t.distance:.1f} m; pairando 2 s")
        if esperar(2.0) is None:
            return
    log(f"mover_para(altura={ALTURA_FINAL:.1f}): descida freando perto do chão")
    r = mover_para(P, log, 30.0, altura=ALTURA_FINAL)
    if r is None:
        return
    motivo = {True: f"chegou a {P.drone.telemetry.height:.1f} m", False: "descida demorou 30 s",
              "estado5": "estado 5 na descida (bateria baixa)"}[r]
    pousar_suave(motivo)


def laco_teclado_global(P):
    """Lê /dev/input/event* dos teclados (sem biblioteca). Só age com o teclado global LIGADO (F12)."""
    dispositivos = []
    for nome in glob.glob("/sys/class/input/event*/device/name"):
        try:
            if "keyboard" in open(nome).read().lower():
                dispositivos.append("/dev/input/" + nome.split("/")[4])
        except OSError:
            pass
    arquivos = []
    for d in dispositivos:
        try:
            arquivos.append(open(d, "rb", buffering=0))
        except PermissionError:
            P.global_msg = "sem permissão em /dev/input: rode `sudo usermod -aG input $USER` e entre de novo na sessão"
            return
    if not arquivos:
        P.global_msg = "nenhum teclado encontrado em /dev/input"
        return
    import select
    fmt = "llHHi"
    tam = struct.calcsize(fmt)
    P.global_msg = f"lendo {len(arquivos)} teclado(s); F12 liga/desliga"
    while True:
        prontos = select.select(arquivos, [], [], 1.0)[0]
        for f in prontos:
            dados = f.read(tam)
            if len(dados) < tam:
                continue
            _, _, tipo, codigo, valor = struct.unpack(fmt, dados)
            if tipo != 1 or codigo not in CODIGOS or valor == 2:  # só tecla; ignora repetição automática
                continue
            k = CODIGOS[codigo]
            if k == "f12":
                if valor == 1:
                    P.global_ativo = not P.global_ativo
                    P.limpar_teclas()
                    P.aviso = "TECLADO GLOBAL " + ("LIGADO: letras de qualquer janela viram comandos!" if P.global_ativo else "desligado")
                continue
            if not P.global_ativo:
                continue
            if valor == 1:
                P.tecla_baixo(k)
            else:
                P.tecla_cima(k)


def main():
    P = Piloto()
    raiz = tk.Tk()
    raiz.title("Piloto Predator" + ("  — VOANDO" if VOAR else "  — SECO"))
    tela = tk.Canvas(raiz, width=960, height=540, bg="black", highlightthickness=0)
    tela.pack()
    texto = tk.Label(raiz, justify="left", anchor="w", font=("monospace", 11), bg="#111", fg="#eee", width=120, height=11)
    texto.pack(fill="x")
    img = {"ref": None, "item": None, "ultimo": None}
    t_ini = time.time()
    soltar = {}
    if a.roteiro_foto:
        threading.Thread(target=roteiro_foto, args=(P,), daemon=True).start()
    if a.teclado_global:
        threading.Thread(target=laco_teclado_global, args=(P,), daemon=True).start()

    def ao_pressionar(ev):
        k = ev.keysym.lower()
        if k in soltar:
            raiz.after_cancel(soltar.pop(k))
            return  # repetição automática do X11: já estava apertada
        if not P.global_ativo:  # com o global ligado quem manda é o /dev/input (evita comando em dobro)
            P.tecla_baixo(k)

    def ao_soltar(ev):
        k = ev.keysym.lower()
        if not P.global_ativo:
            soltar[k] = raiz.after(40, lambda: (P.tecla_cima(k), soltar.pop(k, None)))

    raiz.bind("<KeyPress>", ao_pressionar)
    raiz.bind("<KeyRelease>", ao_soltar)
    raiz.bind("<FocusOut>", lambda _e: None if P.global_ativo else P.limpar_teclas())
    raiz.focus_force()

    def atualiza():
        png = P.png
        if png is not None and png is not img["ultimo"]:
            img["ultimo"] = png
            img["ref"] = tk.PhotoImage(data=png)
            if img["item"] is None:
                img["item"] = tela.create_image(0, 0, image=img["ref"], anchor="nw")
            else:
                tela.itemconfig(img["item"], image=img["ref"])
        t = P.drone.telemetry
        texto.config(text=(
            f"{'VOANDO (manda comandos)' if VOAR else 'SECO (não envia nada)'}   fase: {P.fase}   {P.aviso}\n"
            f"teclas: {''.join(sorted(P.teclas_atuais())) or '-'}   amplitude roll/pitch: {PRESETS[P.preset]}   sinais (pitch,roll,yaw,acel): {tuple(P.sinais)}\n"
            f"manche (µs): roll {P.cmd['roll']}  pitch {P.cmd['pitch']}  yaw {P.cmd['yaw']}  ACEL {P.cmd['throttle']}  (E/Q: {P.acel_dev:+.0f})\n"
            f"estado {t.state} modo {t.mode}   roll {t.roll:+.1f}°  pitch {t.pitch:+.1f}°  yaw {t.yaw:.0f}°\n"
            f"v_vert {t.v_speed:.1f}  v_hor {t.h_speed:.1f} m/s   distância {t.distance:.1f} m   satélites {t.satellites}   bateria {t.battery}\n"
            f"link {'ok' if P.drone.link_ok else 'PERDIDO'}   vídeo {P.video.fps:.0f} q/s   {'gravando em ' + P.pasta if P.pasta else 'sem gravar'}\n"
            f"gesto: {P.gesto_txt or ('-' if a.gestos else 'desligado (--gestos)')}\n"
            f"teclado global: {('LIGADO' if P.global_ativo else 'desligado') if a.teclado_global else 'não pedido'}  {P.global_msg}\n"
            f"T DESTRAVA (não decola)  E sobe  Q desce  H segura posição  G manobra automática  L pousar  X EMERGÊNCIA  Esc pousa e sai  WASD  C/Z giram  1–5 amplitude (6 = app com --app; 6–7 com --forte)  F1–F4 inverte"))
        fim_teste = a.auto_sair and time.time() - t_ini > a.auto_sair and P.fase == "chao"  # nunca fecha com o drone no ar
        if (P.sair and P.fase == "chao") or fim_teste:
            P.encerrar()
            raiz.destroy()
            return
        raiz.after(100, atualiza)

    raiz.protocol("WM_DELETE_WINDOW", lambda: (setattr(P, "sair", True), P.pousar("fechando janela")))
    raiz.after(100, atualiza)
    raiz.mainloop()


# ---------------- painel no navegador (--web) ----------------
# Só biblioteca padrão. O navegador manda o conjunto de teclas seguradas a cada 100 ms; se parar de mandar por 0,4 s
# (aba fechada, travou, perdeu o foco), todas as teclas são soltas. Botões de ação vêm como a tecla correspondente,
# então passam pelas mesmas regras e seguranças do teclado (e cancelam roteiro/gesto como uma tecla sua).
TECLAS_MOVIMENTO = {"w", "a", "s", "d", "e", "q", "c", "z"}
ACOES_WEB = {"t", "l", "x", "h", "g", "escape", "1", "2", "3", "4", "5", "6", "7"}
WEB_VALIDADE_S = 0.4


def estado_json(P):
    t = P.drone.telemetry
    return {
        "voar": VOAR, "fase": P.fase, "aviso": P.aviso, "teclas": sorted(P.teclas_atuais()), "cmd": P.cmd,
        "roteiro": P.roteiro, "no_ar": P.no_ar, "amp": PRESETS[P.preset], "basico": a.basico, "app": a.app,
        "link": P.drone.link_ok, "video_fps": round(P.video.fps, 1), "pasta": P.pasta or "", "gesto": P.gesto_txt,
        "gestos": a.gestos, "bloqueio": P.bloqueio_emerg,
        "tel": {"estado": t.state, "modo": t.mode, "roll": t.roll, "pitch": t.pitch, "yaw": t.yaw, "altura": t.height,
                "v_vert": t.v_speed, "v_hor": t.h_speed, "distancia": t.distance, "satelites": t.satellites,
                "gps_fix": bool(t.gps_fix), "bateria": t.battery},
    }


def main_web(P):
    import http.server
    import json
    import socketserver
    import webbrowser

    html = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "painel.html"), encoding="utf-8").read()
    web = {"teclas": set(), "t": 0.0}
    trava = threading.Lock()

    def soltar_tudo():
        for k in list(web["teclas"]):
            P.tecla_cima(k)
        web["teclas"] = set()

    def vigia():
        while True:
            with trava:
                if web["teclas"] and time.time() - web["t"] > WEB_VALIDADE_S:
                    soltar_tudo()
            time.sleep(0.05)
    threading.Thread(target=vigia, daemon=True).start()

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _json(self, obj, code=200):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                b = html.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
            elif self.path == "/estado":
                self._json(estado_json(P))
            elif self.path.startswith("/video.mjpg"):
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=quadro")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                ultimo = None
                try:
                    while True:
                        buf = P.video.latest
                        if buf is None or buf is ultimo:
                            time.sleep(0.02)
                            continue
                        ultimo = buf
                        rgb = np.frombuffer(buf, np.uint8).reshape(P.video.HEIGHT, P.video.WIDTH, 3)
                        peq = cv2.resize(rgb, (960, 540), interpolation=cv2.INTER_AREA)
                        ok, jpg = cv2.imencode(".jpg", cv2.cvtColor(peq, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 75])
                        if not ok:
                            continue
                        self.wfile.write(b"--quadro\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpg)).encode() + b"\r\n\r\n")
                        self.wfile.write(jpg.tobytes())
                        self.wfile.write(b"\r\n")
                        time.sleep(0.05)
                except (BrokenPipeError, ConnectionResetError):
                    return
            else:
                self.send_error(404)

        def do_POST(self):
            origem = self.headers.get("Origin")
            origens_permitidas = {f"http://127.0.0.1:{a.porta}", f"http://localhost:{a.porta}"}
            if origem and origem not in origens_permitidas:
                return self._json({"erro": "origem recusada"}, 403)
            if self.headers.get_content_type() != "application/json":
                return self._json({"erro": "Content-Type deve ser application/json"}, 415)
            n = int(self.headers.get("Content-Length") or 0)
            if n > 4096:
                return self._json({"erro": "corpo grande demais"}, 413)
            try:
                corpo = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._json({"erro": "json"}, 400)
            if self.path == "/teclas":
                novas = {k for k in corpo.get("teclas", []) if k in TECLAS_MOVIMENTO}
                with trava:
                    for k in novas - web["teclas"]:
                        P.tecla_baixo(k)
                    for k in web["teclas"] - novas:
                        P.tecla_cima(k)
                    web["teclas"], web["t"] = novas, time.time()
                return self._json({"ok": True})
            if self.path == "/acao":
                k = corpo.get("k")
                if k not in ACOES_WEB:
                    return self._json({"erro": "ação desconhecida"}, 400)
                P.tecla_baixo(k)
                return self._json({"ok": True})
            self.send_error(404)

    class Servidor(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    srv = Servidor(("127.0.0.1", a.porta), H)  # só nesta máquina
    url = f"http://127.0.0.1:{a.porta}/"
    print(f"painel em {url}", flush=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    if not a.sem_navegador:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    t_ini = time.time()
    try:
        while True:
            fim_teste = a.auto_sair and time.time() - t_ini > a.auto_sair and P.fase == "chao"
            if (P.sair and P.fase == "chao") or fim_teste:
                break
            time.sleep(0.2)
    except KeyboardInterrupt:  # Ctrl+C no terminal: pousa e espera chegar ao chão
        P.sair = True
        P.pousar("Ctrl+C")
        while P.fase != "chao":
            time.sleep(0.2)
    srv.shutdown()
    P.encerrar()


if __name__ == "__main__":
    if a.web:
        main_web(Piloto())
    else:
        main()
    os._exit(0)  # 21/11: a thread do vídeo abortava o Python ao fechar (terminate called); os dados já estão salvos
