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
    updated: float = 0.0  # time.monotonic() do último 0x88
    position_updated: float = 0.0  # time.monotonic() do último 0x89


class Drone:
    def __init__(self, read_only=False, iface=None, destination=None,
                 period=None, telemetry_period=None, link_timeout=None):
        self.read_only = read_only
        self.iface = IFACE if iface is None else iface
        destination = DRONE if destination is None else destination
        self.destination = (socket.gethostbyname(destination[0]), destination[1])
        self.period = PERIOD if period is None else period
        self.telemetry_period = TELEMETRY_PERIOD if telemetry_period is None else telemetry_period
        self.link_timeout = LINK_TIMEOUT if link_timeout is None else link_timeout
        self._telemetry = Telemetry()
        self.sticks = {"roll": 1500, "pitch": 1500, "yaw": 1500, "throttle": 1000}
        self._queue = []
        self._lock = threading.Lock()
        self._telemetry_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._running = False
        self._sock = None
        self._stop_event = None
        self._threads = []

    # --- ciclo de vida ---
    def start(self):
        with self._state_lock:
            if self._running:
                return self
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                if self.iface:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, self.iface)
                sock.bind(("", 0))
            except Exception:
                sock.close()
                raise
            stop_event = threading.Event()
            threads = [
                threading.Thread(target=self._send_loop, args=(sock, stop_event), daemon=True,
                                 name="predator-send"),
                threading.Thread(target=self._recv_loop, args=(sock, stop_event), daemon=True,
                                 name="predator-recv"),
            ]
            self._sock = sock
            self._stop_event = stop_event
            self._threads = threads
            self._running = True
            for thread in threads:
                thread.start()
        return self

    def stop(self):
        with self._state_lock:
            if not self._running:
                return
            self._running = False
            stop_event, sock, threads = self._stop_event, self._sock, self._threads
            self._stop_event, self._sock, self._threads = None, None, []
            with self._lock:
                self._queue.clear()
                self.sticks = {"roll": 1500, "pitch": 1500, "yaw": 1500, "throttle": 1000}
            stop_event.set()
            sock.close()
        for thread in threads:
            if thread is not threading.current_thread():
                thread.join(timeout=1.0)

    # --- estado ---
    @property
    def telemetry(self):
        """Snapshot consistente; alterações internas nunca aparecem pela metade."""
        with self._telemetry_lock:
            return dataclasses.replace(self._telemetry)

    @property
    def telemetry_age(self):
        updated = self.telemetry.updated
        return float("inf") if not updated else time.monotonic() - updated

    @property
    def position_age(self):
        updated = self.telemetry.position_updated
        return float("inf") if not updated else time.monotonic() - updated

    @property
    def link_ok(self):
        return max(self.telemetry_age, self.position_age) < self.link_timeout

    def gps_ok(self, min_satellites=8, max_age=None):
        tel = self.telemetry
        max_age = self.link_timeout if max_age is None else max_age
        return tel.gps_fix and tel.satellites >= min_satellites and self.position_age < max_age

    @property
    def armed(self):
        return self.telemetry.state not in (0, None)

    # --- comandos ---
    def command(self, name, repeat=3):
        """Enfileira um comando (veja COMMANDS). Repetido algumas vezes porque UDP pode perder pacotes."""
        if self.read_only:
            raise RuntimeError("link em modo somente-leitura")
        frame = COMMANDS[name]()
        with self._state_lock:
            if not self._running:
                raise RuntimeError("link não iniciado")
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
    def _send(self, sock, data):
        try:
            sock.sendto(data, self.destination)
        except OSError:
            pass  # Wi-Fi caiu; o recv_loop vai acusar link perdido

    def _send_loop(self, sock, stop_event):
        last_tele = 0.0
        while not stop_event.is_set():
            t = time.monotonic()
            if t - last_tele >= self.telemetry_period:
                self._send(sock, bt.request_telemetry())
                last_tele = t
            if not self.read_only:
                with self._lock:
                    frame = self._queue.pop(0) if self._queue else bt.joystick(**self.sticks)
                self._send(sock, frame)
            stop_event.wait(max(0.0, self.period - (time.monotonic() - t)))

    def _recv_loop(self, sock, stop_event):
        while not stop_event.is_set():
            try:
                ready = select.select([sock], [], [], 0.2)[0]
            except (OSError, ValueError):
                break
            if not ready:
                continue
            try:
                pkt, source = sock.recvfrom(2048)
            except OSError:
                break
            if source != self.destination:
                continue
            for f in bt.split(pkt, direction=bt.DRONE_TO_APP):
                info = bt.parse(f)
                if info["cmd"] == "0x88":
                    self._publish(roll=info["roll"], pitch=info["pitch"], yaw=info["yaw"],
                                  state=info["state"], mode=info["mode"], updated=time.monotonic())
                elif info["cmd"] == "0x89":
                    fields = {k: info[k] for k in ("height", "distance", "v_speed", "h_speed", "satellites",
                                                           "gps_fix", "lat", "lon", "battery")}
                    self._publish(**fields, position_updated=time.monotonic())

    def _publish(self, **changes):
        with self._telemetry_lock:
            self._telemetry = dataclasses.replace(self._telemetry, **changes)
