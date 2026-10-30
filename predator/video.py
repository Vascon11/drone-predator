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


def frames(quality=0):
    """Gera (cabeçalho_info, h264_bytes) já desofuscados."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, IFACE)
    s.settimeout(5)
    s.connect((DRONE, PORT))
    s.sendall(stream_cmd(CMD_START, quality))
    last_hb = time.time()
    try:
        while True:
            if time.time() - last_hb > 1:
                s.sendall(stream_cmd(CMD_HEARTBEAT))
                last_hb = time.time()
            h = recv_exact(s, HEADER)
            if not h.startswith(b"lewei_cmd"):
                raise ValueError(f"cabeçalho inesperado: {h[:16].hex(' ')}")
            cmd = struct.unpack_from("<I", h, 10)[0]
            length = struct.unpack_from("<I", h, 22)[0]
            flag = struct.unpack_from("<I", h, 26)[0]
            a, b, c = struct.unpack_from("<hhh", h, 30)
            body = bytearray(recv_exact(s, length)) if length else bytearray()
            if cmd & ~2 != 0x101:
                yield {"cmd": hex(cmd), "len": length}, None
                continue
            n = struct.unpack_from("<I", body, 4)[0]
            ts = struct.unpack_from("<Q", body, 8)[0]
            data = body[32:32 + n]
            if body[16] == 1 or (flag & 0x7F) == 1:
                if flag == 0x81:
                    lw_decode_new(data, n // 2, a, b, c)
                elif n:
                    data[encode_index(ts, n)] ^= 0xFF
            yield {"cmd": hex(cmd), "len": length, "flag": hex(flag), "key": body[16],
                   "n": n, "ts": ts}, bytes(data)
    finally:
        try:
            s.sendall(stream_cmd(CMD_STOP))
        except OSError:
            pass
        s.close()


class VideoStream:
    """Recebe o vídeo numa thread e decodifica com ffmpeg; `latest` guarda o último quadro RGB."""

    WIDTH, HEIGHT = 1280, 720

    def __init__(self, quality=0):
        self.quality = quality
        self.latest = None  # bytes RGB (WIDTH * HEIGHT * 3)
        self.latest_time = 0.0
        self.fps = 0.0
        self.recording = None
        self._running = False
        self._ff = None

    def start(self):
        self._running = True
        self._ff = subprocess.Popen(
            ["ffmpeg", "-loglevel", "error", "-fflags", "nobuffer", "-flags", "low_delay",
             "-probesize", "32", "-analyzeduration", "0", "-f", "h264", "-i", "pipe:0",
             "-vf", f"scale={self.WIDTH}:{self.HEIGHT}", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        threading.Thread(target=self._receive, daemon=True).start()
        threading.Thread(target=self._decode, daemon=True).start()
        return self

    def _receive(self):
        while self._running:
            try:
                for _, data in frames(self.quality):
                    if not self._running:
                        break
                    if data:
                        self._ff.stdin.write(data)
                        self._ff.stdin.flush()
                        if self.recording:
                            self.recording.write(data)
            except (OSError, ConnectionError, ValueError):
                time.sleep(1)  # drone fora do ar: tenta reconectar

    def _decode(self):
        size = self.WIDTH * self.HEIGHT * 3
        count, t0 = 0, time.time()
        while self._running:
            buf = self._ff.stdout.read(size)
            if len(buf) < size:
                break
            self.latest, self.latest_time = buf, time.time()
            count += 1
            if (now := time.time()) - t0 >= 1:
                self.fps, count, t0 = count / (now - t0), 0, now

    def toggle_recording(self, path):
        """Liga/desliga a gravação do H.264 cru. Retorna o caminho se ligou, None se desligou."""
        if self.recording:
            self.recording.close()
            self.recording = None
            return None
        self.recording = open(path, "wb")
        return path

    def stop(self):
        self._running = False
        if self.recording:
            self.recording.close()
            self.recording = None
        if self._ff:
            self._ff.kill()


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
