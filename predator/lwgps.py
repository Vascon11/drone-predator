"""Protocolo LWGPS do módulo Lewei (LW-FPV), recuperado por RE estático.

Só monta e decodifica quadros; não abre sockets. Ver NOTAS.md para as fontes.
"""
import struct

APP_TO_DRONE = 0x3C
DRONE_TO_APP = 0x3E


def checksum(cmd, payload):
    ck = cmd
    for b in struct.pack('<H', len(payload)) + bytes(payload):
        ck ^= b
    return ck


def frame(cmd, payload=b'', direction=APP_TO_DRONE):
    payload = bytes(payload)
    return (bytes([0x46, 0x48, direction, cmd]) + struct.pack('<H', len(payload))
            + payload + bytes([checksum(cmd, payload)]))


def rc_to_byte(rc, centered=True):
    """Converte valor RC 1000..2000 para o byte do app (mesma conta da lib)."""
    if centered:
        return 0x80 if rc == 1500 else ((rc * 255 - 382500) // 1000) & 0xFF ^ 0x80
    return 0x80 if rc == 1500 else ((rc * 255 - 255000) // 1000) & 0xFF


def request_telemetry():
    return frame(0x65, [1])


def takeoff():
    return frame(0x68, [1])


def land():
    return frame(0x68, [2])


def stop():
    return frame(0x68, [4])


def return_home():
    return frame(0x68, [8])


def hover():
    return frame(0x69, [1])


def joystick(pitch=0x80, roll=0x80, throttle=0x80, yaw=0x80):
    return frame(0x6A, [pitch, roll, throttle, yaw])


FLY_MODES = [2, 4, 5, 3, 6, 7, 8, 15, 9, 10, 11, 12, 13, 14]


def parse(data):
    """Decodifica um quadro recebido. Retorna dict ou None se inválido."""
    if len(data) < 7 or data[0] != 0x46 or data[1] != 0x48:
        return None
    n = struct.unpack_from('<H', data, 4)[0]
    if len(data) < n + 7:
        return None
    cmd, payload = data[3], data[6:6 + n]
    if data[6 + n] != checksum(cmd, payload):
        return None
    out = {'cmd': cmd, 'payload': bytes(payload)}
    if cmd == 0x65 and n >= 24:
        roll, pitch, yaw = struct.unpack_from('<hhh', data, 6)
        mode = data[12] >> 4
        out.update(
            roll=roll / 10, pitch=pitch / 10, yaw=yaw / 10,
            fly_mode=FLY_MODES[mode - 1] if 1 <= mode <= 14 else None,
            state=data[12] & 0x0F,
            distance=struct.unpack_from('<H', data, 13)[0] / 10,
            v_speed=struct.unpack_from('<b', data, 15)[0] / 10,
            height=struct.unpack_from('<h', data, 16)[0] / 10,
            h_speed=struct.unpack_from('<b', data, 18)[0] / 10,
            satellites=data[19] & 0x1F,
            gps_fix=bool(data[20] & 1),
            rc_signal=(data[20] >> 1) & 0x3F,
            lat=struct.unpack_from('<i', data, 21)[0] / 1e7,
            lon=struct.unpack_from('<i', data, 25)[0] / 1e7,
            battery=data[29],
        )
    return out


if __name__ == '__main__':
    for name, f in [('telemetria', request_telemetry()), ('decolar', takeoff()),
                    ('pousar', land()), ('manche neutro', joystick())]:
        print(f'{name:14s} {f.hex(" ")}')
    fake = frame(0x65, struct.pack('<hhhBHbhbBBiiB', 15, -20, 900, 0x10, 123, 0, 52, 3, 9, 1,
                                   -235505000, -466333000, 87), DRONE_TO_APP)
    print(parse(fake))
