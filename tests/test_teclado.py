"""Testes do mapa de teclas do Predator (sem drone): python3 -P tests/test_teclado.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from predator import teclado as t  # noqa: E402
from predator.movimento import MovimentoConfig  # noqa: E402


class TestTeclado(unittest.TestCase):
    def test_neutro(self):
        self.assertEqual(t.comando_teclas(set(), 30, 40, 50), (0, 0, 0, 0))

    def test_direcoes(self):
        self.assertEqual(t.comando_teclas({"d"}, 30, 40, 50)[0], 30)
        self.assertEqual(t.comando_teclas({"a"}, 30, 40, 50)[0], -30)
        self.assertEqual(t.comando_teclas({"w"}, 30, 40, 50)[1], 30)
        self.assertEqual(t.comando_teclas({"s"}, 30, 40, 50)[1], -30)
        self.assertEqual(t.comando_teclas({"c"}, 30, 40, 50)[2], 40)
        self.assertEqual(t.comando_teclas({"z"}, 30, 40, 50)[2], -40)
        self.assertEqual(t.comando_teclas({"e"}, 30, 40, 50)[3], 50)
        self.assertEqual(t.comando_teclas({"q"}, 30, 40, 50)[3], -50)

    def test_opostas_se_anulam(self):
        self.assertEqual(t.comando_teclas({"w", "s", "a", "d"}, 30, 40, 50), (0, 0, 0, 0))

    def test_limites(self):
        comando = t.comando_teclas({"d", "w", "c", "e"}, 999, 999, 999)
        self.assertEqual(comando, (t.MAX_RP, t.MAX_RP, t.MAX_YAW, t.MAX_ACEL_SOBE))
        self.assertEqual(t.comando_teclas({"q"}, 30, 40, 999)[3], -t.MAX_ACEL_DESCE)

    def test_sinais_invertem(self):
        self.assertEqual(t.comando_teclas({"w"}, 30, 40, 50, sinais=(-1, 1, 1, 1))[1], -30)
        self.assertEqual(t.comando_teclas({"d"}, 30, 40, 50, sinais=(1, -1, 1, 1))[0], -30)
        self.assertEqual(t.comando_teclas({"e"}, 30, 40, 50, sinais=(1, 1, 1, -1))[3], -50)

    def test_para_manche(self):
        self.assertEqual(t.para_manche((0, 0, 0, 0)),
                         {"roll": 1500, "pitch": 1500, "yaw": 1500, "throttle": 1500})
        self.assertEqual(t.para_manche((60, -60, 80, 100)),
                         {"roll": 1560, "pitch": 1440, "yaw": 1580, "throttle": 1600})
        self.assertEqual(t.para_manche((9999, -9999, 0, 0))["roll"], 2000)

    def test_config_unifica_forcas(self):
        config = MovimentoConfig(forca_horizontal=30, forca_vertical_sobe=40,
                                 forca_vertical_desce=70, forca_giro=20)
        self.assertEqual(t.comando_teclas({"d", "w", "c", "e"}, config=config), (30, 30, 20, 40))
        self.assertEqual(t.comando_teclas({"a", "s", "z", "q"}, config=config), (-30, -30, -20, -70))
        self.assertEqual(t.para_manche((100, -100, 100, -100), config),
                         {"roll": 1530, "pitch": 1470, "yaw": 1520, "throttle": 1430})

    def test_config_rejeita_forca_invalida(self):
        with self.assertRaises(ValueError):
            MovimentoConfig(forca_horizontal=501)
