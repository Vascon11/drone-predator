"""Primeiro voo: decola, manda pousar ao subir 0,8 m (ou após 6 s no ar) e espera travar.

Só ao ar livre, com hélices presas, chão plano, ninguém a menos de 5 m e alguém olhando o drone.
Lista fechada de pacotes. No ar nunca trava nem corta motor, salvo se capotar.
Ctrl+C, erro ou SIGTERM durante o voo: manda pousar. Registra tudo em capturas/voo1m_*.csv.
Uso: python3 -P scripts/voo_1m.py --confirmo-voo
     python3 -P scripts/voo_1m.py --simular PORTA --confirmo-voo   (drone falso em 127.0.0.1)
"""
import argparse
import csv
import math
import os
import select
import signal
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from predator import armar, bt  # noqa: E402
from predator.voz import falar  # noqa: E402  (só toca áudio, nunca envia ao drone)

IFACE = b"wlp2s0"
DRONE = ("192.168.0.1", 50000)

SUBIDA_ALVO = 0.8     # m acima do chão: manda pousar
SUBIDA_NO_AR = 0.25   # m: considera que saiu do chão
MAX_NO_AR = 6.0       # s no ar antes de pousar de qualquer jeito
MAX_ESPERA_SUBIR = 10.0  # s depois de decolar; sem subir, trava no chão
MAX_DESTRAVAR = 3.0
MAX_POUSO = 60.0      # s até avisar que não travou (continua mandando pousar)
LIMITE_LINK = 1.0     # s sem telemetria
LIMITE_DIST = 5.0     # m do ponto de partida
LIMITE_VEL = 2.0      # m/s horizontal
LIMITE_TILT = 25.0    # graus: pousa
TILT_CAPOTOU = 60.0   # graus por 0,3 s: corta motores
SUBIDA_POUSADO = 0.3  # m do chão, parado por 2 s e 3 s após pousar: trava
ACEL_DESCIDA = 1300   # manche se o pouso for ignorado (5 s sem descer 0,2 m)
MIN_SATS = 8
MIN_BATERIA = 30

NEUTRO = bt.joystick(throttle=1500)
MINIMO = bt.joystick(throttle=1000)
DESCER = bt.joystick(throttle=ACEL_DESCIDA)
PULSO = bt.joystick(throttle=1625)  # modo --pulso: acelerador por 1 s (20/11: 1650 subiu a 3 m/s e capotou; 1600 sem vento andou ~20 cm; 1550 não saiu)
USAR_PULSO = [False]
EMERGENCIA = bt.frame(0x94, [2])
PERMITIDOS = {bt.request_telemetry(), bt.unlock(), bt.lock(), bt.takeoff(), bt.land(), EMERGENCIA, NEUTRO, MINIMO, DESCER, PULSO}


class Encerrar(Exception):
    pass


def log(msg):
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def metros(a, b):
    dn = (a[0] - b[0]) * 111320
    de = (a[1] - b[1]) * 111320 * math.cos(math.radians(a[0]))
    return math.hypot(dn, de)


class Link:
    def __init__(self, destino, iface, caminho):
        self.destino = destino
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if iface:
            self.s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, iface)
        self.s.bind(("", 0))
        self.t = {}
        self.recebido = 0.0
        self.ultimo_pedido = 0.0
        self.ultima_linha = 0.0
        self.f = open(caminho, "w", newline="")
        self.w = csv.writer(self.f)
        self.campos = ["state", "mode", "height", "v_speed", "h_speed", "distance", "satellites", "gps_fix",
                       "lat", "lon", "battery", "roll", "pitch", "yaw"]
        self.w.writerow(["t", "fase"] + self.campos)
        self.fase = "checagem"

    def enviar(self, dados):
        if dados not in PERMITIDOS:
            raise RuntimeError(f"bloqueado: {dados.hex(' ')}")
        try:
            self.s.sendto(dados, self.destino)
        except OSError:
            pass  # Wi-Fi caiu; a idade da telemetria acusa

    def ciclo(self, manche, comando=None):
        """Um ciclo de 50 ms: comando ou manche, como o app, mais o pedido de telemetria."""
        self.enviar(comando or manche)
        agora = time.time()
        if agora - self.ultimo_pedido >= 0.1:
            self.enviar(bt.request_telemetry())
            self.ultimo_pedido = agora
        fim = agora + 0.05
        while (resta := fim - time.time()) > 0:
            if not select.select([self.s], [], [], resta)[0]:
                continue
            try:
                pacote = self.s.recvfrom(2048)[0]
            except OSError:
                continue
            for q in bt.split(pacote):
                i = bt.parse(q)
                if i["cmd"] in ("0x88", "0x89"):
                    self.t.update(i)
                    self.recebido = time.time()
        if time.time() - self.ultima_linha >= 0.1:
            self.w.writerow([round(time.time(), 2), self.fase] + [self.t.get(c, "") for c in self.campos])
            self.f.flush()
            self.ultima_linha = time.time()

    @property
    def idade(self):
        return time.time() - self.recebido

    def completo(self):
        return all(c in self.t for c in ("state", "height", "battery", "lat"))

    def posicao(self):
        return self.t["lat"], self.t["lon"]


def checagem(link):
    """Junta 3 s de telemetria parado; devolve (altura do chão, posição) ou encerra sem destravar."""
    alturas, baterias, inicio = [], [], time.time()
    while time.time() - inicio < 3:
        link.ciclo(MINIMO)
        if link.completo() and link.idade < LIMITE_LINK:
            alturas.append(link.t["height"])
            baterias.append(link.t["battery"])
    if len(alturas) < 20:
        raise Encerrar("sem telemetria suficiente")
    t = link.t
    log(f"estado={t['state']} satélites={t['satellites']} gps_ok={t['gps_fix']} bateria={min(baterias)}–{max(baterias)} "
        f"altura={sum(alturas) / len(alturas):.1f} roll={t['roll']} pitch={t['pitch']} vel={t['h_speed']}")
    problemas = []
    if t["state"] != 0:
        problemas.append("não está travado")
    if not t["gps_fix"] or t["satellites"] < MIN_SATS:
        problemas.append("GPS fraco")
    if sum(baterias) / len(baterias) < MIN_BATERIA:
        problemas.append("bateria baixa")
    if abs(t["roll"]) > 10 or abs(t["pitch"]) > 10:
        problemas.append("drone inclinado")
    if abs(t["h_speed"]) > 0.5 or abs(t["v_speed"]) > 0.5:
        problemas.append("drone em movimento")
    if problemas:
        falar("bateria_baixa" if "bateria baixa" in problemas else "gps_fraco" if "GPS fraco" in problemas
              else "inclinado" if "drone inclinado" in problemas else "pare", esperar=True)
        raise Encerrar("checagem reprovada: " + ", ".join(problemas))
    return sum(alturas) / len(alturas), link.posicao()


def destravar(link):
    link.fase = "destravar"
    log("DESTRAVANDO")
    falar("destravando")
    ok, _ = armar.destravar(link, MINIMO, max_s=MAX_DESTRAVAR, tentativas=2, log=log)
    if not ok:
        raise Encerrar("não destravou")


def recalibrar_chao(link, chao):
    """Ao destravar, o drone zera a altura (visto em 2026-11-01: 3,3 -> 0,0). Mede de novo o chão."""
    link.fase = "recalibrar"
    amostras, inicio = [], time.time()
    while time.time() - inicio < 1.0:
        link.ciclo(MINIMO)
        if link.idade < LIMITE_LINK:
            amostras.append(link.t["height"])
    novo = sum(amostras) / len(amostras) if amostras else chao
    log(f"altura do chão depois de destravar: {novo:.1f} (antes {chao:.1f})")
    return novo


def travar(link):
    link.fase = "travar"
    return armar.travar(link, MINIMO, log=log)


def motivo_para_pousar(link, chao, partida):
    t = link.t
    subida = t["height"] - chao
    if link.idade > LIMITE_LINK:
        return "telemetria parada"
    if metros(link.posicao(), partida) > LIMITE_DIST:
        return "afastou demais"
    if abs(t["h_speed"]) > LIMITE_VEL:
        return "velocidade horizontal alta"
    if max(abs(t["roll"]), abs(t["pitch"])) > LIMITE_TILT:
        return "inclinação alta"
    return "chegou na altura" if subida >= SUBIDA_ALVO else None


def voar(link, chao, partida, chegou_no_ar):
    """Devolve (motivo do pouso, False) ou (None, True) se nunca saiu do chão."""
    link.fase = "decolar"
    log("DECOLANDO")
    falar("decolando")
    inicio = time.time()
    no_ar_desde = None
    while True:
        passou = time.time() - inicio
        if USAR_PULSO[0]:
            link.ciclo(PULSO if passou < 1.0 else NEUTRO)
        else:
            # 1º sinal só destrava/prepara; o 2º, depois de uma pausa, decola (relato do usuário sobre o app)
            comando = bt.takeoff() if (passou < 1.0 or 2.5 <= passou < 3.5) else None
            link.ciclo(NEUTRO, comando)
        subida = link.t["height"] - chao
        if no_ar_desde is None and subida >= SUBIDA_NO_AR:
            no_ar_desde = time.time()
            chegou_no_ar[0] = True
            log(f"saiu do chão em {passou:.1f} s")
            falar("subindo")
        # a altura da telemetria subestima muito (20/11: ficou em 0,0 com o drone andando de lado):
        # velocidade vertical ou inclinação também contam como "saiu do chão", e então pousa em vez de travar
        if no_ar_desde is None and (abs(link.t["v_speed"]) > 0.5
                                    or max(abs(link.t["roll"]), abs(link.t["pitch"])) > 15):
            no_ar_desde = time.time()
            chegou_no_ar[0] = True
            log(f"saiu do chão (v_speed={link.t['v_speed']}, roll={link.t['roll']}, pitch={link.t['pitch']}) em {passou:.1f} s")
            falar("subindo")
        motivo = motivo_para_pousar(link, chao, partida)
        if motivo:
            chegou_no_ar[0] = True  # sem certeza de estar no chão, trata como no ar
            return motivo, False
        if USAR_PULSO[0] and passou >= 1.5:
            if no_ar_desde or link.t["v_speed"] > 0.2 or subida > 0.1:
                chegou_no_ar[0] = True
                return "fim do pulso", False
            return None, True
        if no_ar_desde and time.time() - no_ar_desde > MAX_NO_AR:
            return "tempo no ar", False
        if no_ar_desde is None and passou > MAX_ESPERA_SUBIR:
            if link.t["v_speed"] > 0.2:  # subindo devagar: não dá para travar
                chegou_no_ar[0] = True
                return "subiu devagar", False
            return None, True


def pousar(link, motivo, chao):
    link.fase = "pousar"
    log(f"POUSANDO ({motivo}); altura {link.t['height'] - chao:.1f} m acima do chão")
    falar("pousando")
    inicio, ultimo, avisou, capotou_desde = time.time(), 0.0, False, None
    altura_inicial, manche, parado_desde = link.t["height"], NEUTRO, None
    while True:
        passou = time.time() - inicio
        comando = None
        if time.time() - ultimo >= 1.0:
            comando = bt.land()
            ultimo = time.time()
        link.ciclo(manche, comando)
        if link.t["state"] == 0 and link.idade < LIMITE_LINK:
            log(f"motores travados, {passou:.1f} s depois de mandar pousar")
            falar("pousou")
            return
        if manche is NEUTRO and passou > 5 and link.t["height"] > altura_inicial - 0.2 \
                and link.t["height"] - chao > SUBIDA_POUSADO:
            log("pouso ignorado: reduzindo o manche para descer")
            manche = DESCER
        perto = link.t["height"] - chao <= SUBIDA_POUSADO and abs(link.t["v_speed"]) <= 0.1 and link.idade < LIMITE_LINK
        parado_desde = (parado_desde or time.time()) if perto else None
        if parado_desde and passou >= 3 and time.time() - parado_desde >= 2:
            log("pousado e parado: travando")
            if travar(link):
                return
            parado_desde = None
        if max(abs(link.t["roll"]), abs(link.t["pitch"])) > TILT_CAPOTOU and link.idade < LIMITE_LINK:
            capotou_desde = capotou_desde or time.time()
            if time.time() - capotou_desde > 0.3:
                log("CAPOTOU: cortando motores")
                for _ in range(10):
                    link.ciclo(NEUTRO, EMERGENCIA)
                    link.ciclo(NEUTRO, bt.lock())
                return
        else:
            capotou_desde = None
        if passou > MAX_POUSO and not avisou:
            log("AVISO: ainda não travou; continuo mandando pousar. Use o controle físico se ele estiver no ar")
            avisou = True
        if passou > MAX_POUSO + 30:
            log("AVISO: encerrando sem confirmação de travado; o drone pode continuar ligado")
            return


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--confirmo-voo", action="store_true")
    p.add_argument("--pulso", action="store_true", help="sobe o acelerador 1 s em vez de usar o comando decolar")
    p.add_argument("--simular", type=int, help="porta do drone falso em 127.0.0.1")
    a = p.parse_args()
    USAR_PULSO[0] = a.pulso
    if not a.confirmo_voo:
        sys.exit("falta --confirmo-voo")

    def sinal(_n, _f):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, sinal)

    raiz = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "capturas")
    if a.simular:
        caminho = f"/tmp/voo1m_sim_{os.getpid()}.csv"
        link = Link(("127.0.0.1", a.simular), None, caminho)
    else:
        caminho = os.path.join(raiz, f"voo1m_{time.strftime('%Y%m%d_%H%M%S')}.csv")
        link = Link(DRONE, IFACE, caminho)
    log(f"registrando em {caminho}")

    no_ar, destravado, estado_chao = [False], False, [None]
    try:
        chao, partida = checagem(link)
        estado_chao[0] = chao
        destravar(link)
        destravado = True
        chao = recalibrar_chao(link, chao)
        estado_chao[0] = chao
        motivo, ficou_no_chao = voar(link, chao, partida, no_ar)
        if ficou_no_chao:
            log("NÃO SAIU DO CHÃO: travando")
            falar("nao_saiu")
            travar(link)
        else:
            pousar(link, motivo, chao)
    except Encerrar as e:
        log(f"ABORTADO: {e}")
        if link.t.get("state") not in (0, None):
            travar(link)
    except BaseException as e:
        log(f"INTERROMPIDO: {type(e).__name__}: {e}")
        if no_ar[0] or link.fase == "decolar":
            while True:
                try:
                    pousar(link, "interrupção", estado_chao[0])
                    break
                except KeyboardInterrupt:
                    log("continua pousando")
        elif destravado or link.t.get("state") not in (0, None):
            travar(link)
    finally:
        link.f.close()
    log(f"estado final: {link.t.get('state')} (0 = travado)")


if __name__ == "__main__":
    main()
