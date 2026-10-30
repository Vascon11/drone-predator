# Scan TCP forçado pela interface do drone (rede de casa usa a mesma faixa 192.168.0.x)
import socket, sys
from concurrent.futures import ThreadPoolExecutor
IFACE, HOST = b"wlp2s0", "192.168.0.1"
def probe(p):
    s = socket.socket(); s.settimeout(0.5)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, IFACE)
    try:
        s.connect((HOST, p)); return p
    except OSError:
        return None
    finally:
        s.close()
with ThreadPoolExecutor(300) as ex:
    print("abertas:", [p for p in ex.map(probe, range(1, 65536)) if p])
