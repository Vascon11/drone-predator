"""Protocolo BTGPS do módulo Lewei — o que o drone "Predator" realmente fala (UDP 192.168.0.1:50000).

Quadro: 42 54 <dir> <len> <cmd> <payload[len]> <xor de len..payload>; dir 3C app→drone, 3E drone→app.
Fontes (liblewei_uartprotol.so): GetBTGPSTxData 0x107dfc, GetBTVirtulRockerControlData 0x106e74,
ParseBTInfoData 0x108650, Get_BTChecksum 0x110ff8. Só monta/decodifica; não abre sockets.
"""
import struct
from functools import reduce

APP_TO_DRONE = 0x3C
DRONE_TO_APP = 0x3E


def frame(cmd, payload=b'', direction=APP_TO_DRONE):
    body = bytes([len(payload), cmd]) + bytes(payload)
    return b'BT' + bytes([direction]) + body + bytes([reduce(lambda a, b: a ^ b, body, 0)])


def request_telemetry():
    """O que o app envia a cada 1 s: pede atitude (0x88) e posição (0x89)."""
    return frame(0x88, [1]) + frame(0x89, [1])


# Comandos de voo (NÃO usados no teste de leitura)
def unlock(): return frame(0x79, [0])
def lock(): return frame(0x79, [1])
def takeoff(): return frame(0x94, [0])
def land(): return frame(0x94, [1])
def return_home(): return frame(0x95, [1])
def hover(): return frame(0xB6, [1])


def joystick(roll=1500, pitch=1500, yaw=1500, throttle=1500, ptz1=1500, ptz2=1500):
    """Manche virtual 0xB5: seis u16 LE em microssegundos RC (1000..2000)."""
    return frame(0xB5, struct.pack('<6H', roll, pitch, yaw, throttle, ptz1, ptz2))


def split(data):
    """Separa um datagrama em quadros BT válidos."""
    out, i = [], 0
    while (i := data.find(b'BT', i)) >= 0 and i + 6 <= len(data):
        n = data[i + 3]
        end = i + n + 6
        if end <= len(data) and reduce(lambda a, b: a ^ b, data[i + 3:end - 1], 0) == data[end - 1]:
            out.append(data[i:end])
            i = end
        else:
            i += 2
    return out


def parse(f):
    n, cmd, p = f[3], f[4], f[5:-1]
    out = {'cmd': hex(cmd), 'len': n}
    if cmd == 0x88 and n >= 7:
        r, pt, y = struct.unpack_from('<hhh', p)
        out.update(roll=r / 10, pitch=pt / 10, yaw=y / 10, state=p[6] & 0xF, mode=p[6] >> 4)
    elif cmd == 0x89 and n >= 19:
        d, vz, h, vh = struct.unpack_from('<hhhh', p)
        lat, lon = struct.unpack_from('<ii', p, 10)
        out.update(distance=d / 10, v_speed=vz / 10, height=h / 10, h_speed=vh / 10,
                   satellites=p[8] & 0x1F, gps_fix=bool(p[9] & 1),
                   lat=lat / 1e7, lon=lon / 1e7, battery=p[18])
    elif cmd == 0x04 and n >= 6:  # não tratado pela lib; layout parecido com 0x88 (hipótese)
        r, pt, y = struct.unpack_from('<hhh', p)
        out.update(roll_hip=r / 10, pitch_hip=pt / 10, yaw_hip=y / 10, raw=p.hex(' '))
    else:
        out['raw'] = p.hex(' ')
    return out
