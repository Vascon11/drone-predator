"""Cliente de vídeo do módulo Lewei (LW93) — TCP 192.168.0.1:7060, protocolo "lewei_cmd".

Recuperado de liblewei-3.2.2.so: avc_read_buffer_thread 0x11c370, send_stream_cmd 0x11c0fc,
encode_index 0x11af08, LW_Decode_New 0x11fb0c. Só envolve a câmera (iniciar/heartbeat/parar vídeo).

Uso:
  python3 -m predator.video gravar saida.h264 [segundos]   # grava H.264 cru
  python3 -m predator.video | ffplay -f h264 -             # (h264 em stdout se nenhum arquivo)
"""
import socket
import struct
import subprocess
import sys
import threading
import time

from .mdata import MDATA1, MDATA2, MDATA3

IFACE = b"wlp2s0"  # a rede de casa (cabo) também é 192.168.0.x
DRONE = "192.168.0.1"
PORT = 7060
HEADER = 46
MAX_BODY = 4 * 1024 * 1024
CMD_HEARTBEAT, CMD_START, CMD_STOP = 1, 2, 3


def stream_cmd(cmd, param=0):
    h = bytearray(HEADER)
    h[0:10] = b"lewei_cmd\0"
    struct.pack_into("<I", h, 10, cmd)
    if cmd == CMD_START:
        struct.pack_into("<I", h, 14, param)
    return bytes(h)


def encode_index(ts, n):
    if n % 2 == 0:
        v = ((n + 1 + (n ^ ts)) ^ n) & 0xFFFFFFFFFFFFFFFF
    else:
        v = (((n ^ ts) + n) ^ n) & 0xFFFFFFFFFFFFFFFF
    return v % n


def lw_decode_new(buf, pos, a, b, c):
    def find(table, v):
        return table.index(v) if v in table else None
    i1, i2, i3 = find(MDATA1, a), find(MDATA2, b), find(MDATA3, c)
    if i1 is not None:
        buf[pos] = i1
    if i2 is not None:
        buf[pos + 1] = i2 ^ buf[pos]
    if i3 is not None:
        buf[pos + 2] = buf[pos + 1] ^ buf[pos] ^ i3


def recv_exact(sock, n):
    data = bytearray()
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("conexão fechada pelo drone")
        data += chunk
    return bytes(data)


def parse_video_frame(header, body):
    """Valida e decodifica um quadro já recebido, sem acessar rede."""
    if len(header) != HEADER or not header.startswith(b"lewei_cmd"):
        raise ValueError(f"cabeçalho inesperado: {header[:16].hex(' ')}")
    cmd = struct.unpack_from("<I", header, 10)[0]
    length = struct.unpack_from("<I", header, 22)[0]
    flag = struct.unpack_from("<I", header, 26)[0]
    a, b, c = struct.unpack_from("<hhh", header, 30)
    if length != len(body):
        raise ValueError(f"corpo truncado: esperado {length}, recebido {len(body)}")
    if cmd & ~2 != 0x101:
        return {"cmd": hex(cmd), "len": length}, None
    if len(body) < 32:
        raise ValueError(f"corpo de vídeo curto: {len(body)}")
    n = struct.unpack_from("<I", body, 4)[0]
    if n > len(body) - 32:
        raise ValueError(f"H.264 truncado: declarado {n}, disponível {len(body) - 32}")
    ts = struct.unpack_from("<Q", body, 8)[0]
    data = bytearray(body[32:32 + n])
    key = body[16]
    if key == 1 or (flag & 0x7F) == 1:
        if flag == 0x81:
            if n // 2 + 2 >= n:
                raise ValueError(f"quadro ofuscado curto: {n}")
            lw_decode_new(data, n // 2, a, b, c)
        elif n:
            data[encode_index(ts, n)] ^= 0xFF
    return {"cmd": hex(cmd), "len": length, "flag": hex(flag), "key": key,
            "n": n, "ts": ts}, bytes(data)


def frames(quality=0, iface=IFACE, drone=DRONE, port=PORT, max_body=MAX_BODY):
    """Gera (cabeçalho_info, h264_bytes) já desofuscados."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if iface:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, iface)
    s.settimeout(5)
    s.connect((drone, port))
    s.sendall(stream_cmd(CMD_START, quality))
    last_hb = time.time()
    try:
        while True:
            if time.time() - last_hb > 1:
                s.sendall(stream_cmd(CMD_HEARTBEAT))
                last_hb = time.time()
            h = recv_exact(s, HEADER)
            length = struct.unpack_from("<I", h, 22)[0]
            if length > max_body:
                raise ValueError(f"corpo de vídeo excede o limite: {length} > {max_body}")
            body = bytearray(recv_exact(s, length)) if length else bytearray()
            yield parse_video_frame(h, body)
    finally:
        try:
            s.sendall(stream_cmd(CMD_STOP))
        except OSError:
            pass
        s.close()


class VideoStream:
    """Recebe o vídeo numa thread e decodifica com ffmpeg; `latest` guarda o último quadro RGB."""

    WIDTH, HEIGHT = 1280, 720

    def __init__(self, quality=0, iface=IFACE, drone=DRONE, port=PORT):
        self.quality = quality
        self.iface, self.drone, self.port = iface, drone, port
        self.latest = None  # bytes RGB (WIDTH * HEIGHT * 3)
        self.latest_time = 0.0
        self.fps = 0.0
        self.last_error = None
        self._recording = None
        self._record_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._running = False
        self._ff = None
        self._stop_event = None
        self._thread = None

    def start(self):
        with self._state_lock:
            if self._running:
                return self
            self._running = True
            self._stop_event = threading.Event()
            self._thread = threading.Thread(target=self._worker, args=(self._stop_event,), daemon=True,
                                            name="predator-video")
            self._thread.start()
        return self

    @property
    def recording(self):
        with self._record_lock:
            return self._recording

    def _spawn_ffmpeg(self):
        return subprocess.Popen(
            ["ffmpeg", "-loglevel", "error", "-fflags", "nobuffer", "-flags", "low_delay",
             "-probesize", "32", "-analyzeduration", "0", "-f", "h264", "-i", "pipe:0",
             "-vf", f"scale={self.WIDTH}:{self.HEIGHT}", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def _worker(self, stop_event):
        while not stop_event.is_set():
            try:
                ff = self._spawn_ffmpeg()
            except OSError as error:
                self.last_error = str(error)
                stop_event.wait(1.0)
                continue
            with self._state_lock:
                if stop_event.is_set():
                    ff.kill()
                    ff.wait()
                    break
                self._ff = ff
            decoder = threading.Thread(target=self._decode, args=(ff, stop_event), daemon=True,
                                       name="predator-decode")
            decoder.start()
            try:
                for _, data in frames(self.quality, self.iface, self.drone, self.port):
                    if stop_event.is_set() or ff.poll() is not None:
                        break
                    if data:
                        ff.stdin.write(data)
                        ff.stdin.flush()
                        with self._record_lock:
                            if self._recording:
                                self._recording.write(data)
            except (OSError, ConnectionError, ValueError) as error:
                self.last_error = str(error)
            finally:
                self._close_ffmpeg(ff)
                decoder.join(timeout=1.0)
                with self._state_lock:
                    if self._ff is ff:
                        self._ff = None
            if not stop_event.is_set():
                stop_event.wait(1.0)  # câmera/decoder caiu: recria tudo e reconecta

    def _decode(self, ff, stop_event):
        size = self.WIDTH * self.HEIGHT * 3
        count, t0 = 0, time.monotonic()
        while not stop_event.is_set():
            buf = ff.stdout.read(size)
            if len(buf) < size:
                break
            self.latest, self.latest_time = buf, time.time()
            count += 1
            if (now := time.monotonic()) - t0 >= 1:
                self.fps, count, t0 = count / (now - t0), 0, now

    def toggle_recording(self, path):
        """Liga/desliga a gravação do H.264 cru. Retorna o caminho se ligou, None se desligou."""
        with self._record_lock:
            if self._recording:
                self._recording.close()
                self._recording = None
                return None
            self._recording = open(path, "wb")
            return path

    def stop(self):
        with self._state_lock:
            if not self._running:
                return
            self._running = False
            stop_event, thread, ff = self._stop_event, self._thread, self._ff
            self._stop_event, self._thread = None, None
            stop_event.set()
        if ff:
            self._close_ffmpeg(ff)
        if thread is not threading.current_thread():
            thread.join(timeout=6.0)
        with self._state_lock:
            if self._ff is ff:
                self._ff = None
        with self._record_lock:
            if self._recording:
                self._recording.close()
                self._recording = None

    @staticmethod
    def _close_ffmpeg(ff):
        try:
            if ff.poll() is None:
                ff.kill()
            ff.wait(timeout=1.0)
        except (OSError, subprocess.TimeoutExpired):
            pass
        for pipe in (ff.stdin, ff.stdout):
            try:
                pipe.close()
            except (AttributeError, OSError, ValueError):
                pass


def main():
    out = open(sys.argv[2], "wb") if len(sys.argv) > 2 and sys.argv[1] == "gravar" else sys.stdout.buffer
    duration = float(sys.argv[3]) if len(sys.argv) > 3 else float("inf")
    end, count, total = time.time() + duration, 0, 0
    for info, data in frames():
        if count < 5:
            print(info, (data or b"")[:8].hex(" "), file=sys.stderr)
        if data:
            out.write(data)
            count += 1
            total += len(data)
        if time.time() > end:
            break
    print(f"{count} quadros, {total} bytes", file=sys.stderr)


if __name__ == "__main__":
    main()
