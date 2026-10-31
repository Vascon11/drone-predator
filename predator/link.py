"""Link de controle com o drone (UDP 192.168.0.1:50000, protocolo BT).

Uma thread envia a cada 50 ms (como o app LW-FPV): um comando pendente da fila OU o manche;
a cada 0,5 s pede telemetria. Outra thread lê as respostas e atualiza `telemetry`.
"""
import dataclasses
import select
import socket
import threading
import time

from . import bt

IFACE = b"wlp2s0"  # a rede de casa (cabo) também é 192.168.0.x
DRONE = ("192.168.0.1", 50000)
PERIOD = 0.05
TELEMETRY_PERIOD = 0.5
LINK_TIMEOUT = 1.5

COMMANDS = {
    "destravar": bt.unlock,
    "travar": bt.lock,
    "decolar": bt.takeoff,
    "pousar": bt.land,
    "emergencia": lambda: bt.frame(0x94, [2]),
    "casa": bt.return_home,
    "pairar": bt.hover,
}


@dataclasses.dataclass
class Telemetry:
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    state: int | None = None  # 0 = travado
    mode: int | None = None
    height: float = 0.0
    distance: float = 0.0
    v_speed: float = 0.0
    h_speed: float = 0.0
    satellites: int = 0
    gps_fix: bool = False
    lat: float = 0.0
    lon: float = 0.0
    battery: int | None = None
    updated: float = 0.0  # time.time() do último 0x88


class Drone:
    def __init__(self, read_only=False):
        self.read_only = read_only
        self.telemetry = Telemetry()
        self.sticks = {"roll": 1500, "pitch": 1500, "yaw": 1500, "throttle": 1000}
        self._queue = []
        self._lock = threading.Lock()
        self._running = False
        self._sock = None

    # --- ciclo de vida ---
    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, IFACE)
        self._sock.bind(("", 0))
        self._running = True
        threading.Thread(target=self._send_loop, daemon=True).start()
        threading.Thread(target=self._recv_loop, daemon=True).start()
        return self

    def stop(self):
        self._running = False

    # --- estado ---
    @property
    def link_ok(self):
        return time.time() - self.telemetry.updated < LINK_TIMEOUT

    @property
    def armed(self):
        return self.telemetry.state not in (0, None)

    # --- comandos ---
    def command(self, name, repeat=3):
        """Enfileira um comando (veja COMMANDS). Repetido algumas vezes porque UDP pode perder pacotes."""
        if self.read_only:
            raise RuntimeError("link em modo somente-leitura")
        frame = COMMANDS[name]()
        with self._lock:
            if name == "emergencia":
                self._queue = [frame] * repeat + self._queue  # fura a fila
            else:
                self._queue += [frame] * repeat

    def set_sticks(self, roll=1500, pitch=1500, yaw=1500, throttle=1500, ptz2=1500):
        clamp = lambda v: max(1000, min(2000, int(v)))  # noqa: E731
        with self._lock:
            self.sticks = {"roll": clamp(roll), "pitch": clamp(pitch),
                           "yaw": clamp(yaw), "throttle": clamp(throttle), "ptz2": clamp(ptz2)}

    # --- threads ---
    def _send(self, data):
        try:
            self._sock.sendto(data, DRONE)
        except OSError:
            pass  # Wi-Fi caiu; o recv_loop vai acusar link perdido

    def _send_loop(self):
        last_tele = 0.0
        while self._running:
            t = time.time()
            if t - last_tele >= TELEMETRY_PERIOD:
                self._send(bt.request_telemetry())
                last_tele = t
            if not self.read_only:
                with self._lock:
                    frame = self._queue.pop(0) if self._queue else bt.joystick(**self.sticks)
                self._send(frame)
            time.sleep(max(0.0, PERIOD - (time.time() - t)))

    def _recv_loop(self):
        while self._running:
            if not select.select([self._sock], [], [], 0.2)[0]:
                continue
            try:
                pkt, _ = self._sock.recvfrom(2048)
            except OSError:
                continue
            for f in bt.split(pkt):
                info = bt.parse(f)
                tel = self.telemetry
                if info["cmd"] == "0x88":
                    tel.roll, tel.pitch, tel.yaw = info["roll"], info["pitch"], info["yaw"]
                    tel.state, tel.mode = info["state"], info["mode"]
                    tel.updated = time.time()
                elif info["cmd"] == "0x89":
                    for k in ("height", "distance", "v_speed", "h_speed", "satellites",
                              "gps_fix", "lat", "lon", "battery"):
                        setattr(tel, k, info[k])
