"""Testes offline dos parsers e do ciclo de vida da biblioteca."""
import struct
import time
import unittest

from predator import bt
from predator.link import Drone
from predator.video import HEADER, parse_video_frame


class TestBt(unittest.TestCase):
    def test_filtra_direcao(self):
        resposta = bt.frame(0x88, bytes(7), direction=bt.DRONE_TO_APP)
        pedido = bt.frame(0x88, bytes(7), direction=bt.APP_TO_DRONE)
        self.assertEqual(bt.split(resposta + pedido, direction=bt.DRONE_TO_APP), [resposta])

    def test_descarta_checksum_invalido(self):
        quadro = bytearray(bt.frame(0x88, bytes(7), direction=bt.DRONE_TO_APP))
        quadro[-1] ^= 1
        self.assertEqual(bt.split(quadro), [])


class TestLink(unittest.TestCase):
    def test_telemetria_e_snapshot(self):
        drone = Drone(read_only=True, iface=b"", destination=("127.0.0.1", 9))
        agora = time.monotonic()
        drone._publish(state=2, updated=agora, position_updated=agora)
        snapshot = drone.telemetry
        snapshot.state = 0
        self.assertEqual(drone.telemetry.state, 2)
        self.assertTrue(drone.link_ok)

    def test_start_e_stop_sao_idempotentes(self):
        drone = Drone(read_only=True, iface=b"", destination=("127.0.0.1", 9), telemetry_period=10)
        drone.start()
        threads = tuple(drone._threads)
        self.assertIs(drone.start(), drone)
        self.assertEqual(tuple(drone._threads), threads)
        drone.stop()
        drone.stop()
        self.assertFalse(drone._running)
        self.assertTrue(all(not thread.is_alive() for thread in threads))

    def test_stop_limpa_comandos_e_manche(self):
        drone = Drone(iface=b"", destination=("127.0.0.1", 9), telemetry_period=10)
        with self.assertRaises(RuntimeError):
            drone.command("decolar")
        drone.start()
        drone.command("decolar")
        drone.set_sticks(roll=1800, throttle=1800)
        drone.stop()
        self.assertEqual(drone._queue, [])
        self.assertEqual(drone.sticks, {"roll": 1500, "pitch": 1500, "yaw": 1500, "throttle": 1000})
        with self.assertRaises(RuntimeError):
            drone.command("decolar")


class TestVideo(unittest.TestCase):
    @staticmethod
    def frame(body, declared=None, flag=0):
        header = bytearray(HEADER)
        header[:10] = b"lewei_cmd\0"
        struct.pack_into("<I", header, 10, 0x101)
        struct.pack_into("<I", header, 22, len(body) if declared is None else declared)
        struct.pack_into("<I", header, 26, flag)
        return bytes(header)

    def test_rejeita_corpo_curto(self):
        body = bytes(12)
        with self.assertRaises(ValueError):
            parse_video_frame(self.frame(body), body)

    def test_rejeita_h264_truncado(self):
        body = bytearray(32)
        struct.pack_into("<I", body, 4, 100)
        with self.assertRaises(ValueError):
            parse_video_frame(self.frame(body), body)

    def test_decodifica_corpo_valido(self):
        payload = b"\x00\x00\x00\x01\x65"
        body = bytearray(32) + payload
        struct.pack_into("<I", body, 4, len(payload))
        info, data = parse_video_frame(self.frame(body), body)
        self.assertEqual(info["n"], len(payload))
        self.assertEqual(data, payload)
