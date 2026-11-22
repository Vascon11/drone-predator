"""Testes do movimento suave (predator/suave.py). Sem rede nem drone."""
import math
import time
import unittest

from predator import suave as s
from predator.movimento import MovimentoConfig


class TestSuave(unittest.TestCase):
    def test_perfil_acelera_aos_poucos_e_freia_perto_do_alvo(self):
        p = s.Perfil(vmax=1.0, amax=0.5, afreio=0.5)
        v1 = p.passo(0.0, 10.0, 0.1)
        self.assertLessEqual(v1, 0.05 + 1e-9)
        self.assertGreater(v1, 0)
        for _ in range(100):
            p.passo(0.0, 10.0, 0.1)
        self.assertAlmostEqual(p.v, 1.0)
        self.assertLess(p.passo(9.9, 10.0, 0.1), 1.0)

    def test_perfil_desce_com_sinal_negativo(self):
        p = s.Perfil(vmax=0.25, amax=0.6)
        for _ in range(50):
            v = p.passo(2.0, 0.4, 0.1)
        self.assertLess(v, 0)
        self.assertGreaterEqual(v, -0.25 - 1e-9)

    def test_velocidade_pela_altura(self):
        m = s.Velocidade()
        for i in range(10):
            v = m.medir(i * 0.1, 1.0 - 0.3 * i * 0.1)
        self.assertAlmostEqual(v, -0.3)

    def test_velocidade_descarta_relogio_regressivo(self):
        m = s.Velocidade()
        m.medir(2.0, 1.0)
        m.medir(1.0, 2.0)
        self.assertEqual(len(m.pts), 1)

    def test_controle_altura_usa_ganhos_medidos_e_limite_de_variacao(self):
        c = s.ControleAltura(kp_us=0.0, taxa=1e9)
        self.assertAlmostEqual(c.passo(1.17, 1.17, 0.05), 250)
        self.assertAlmostEqual(c.passo(-0.13, -0.13, 0.05), -125)
        c2 = s.ControleAltura(taxa=500.0)
        self.assertLessEqual(abs(c2.passo(1.0, 0.0, 0.05)), 25 + 1e-9)

    def test_rejeita_dt_invalido(self):
        with self.assertRaises(ValueError):
            s.Perfil(1.0, 1.0).passo(0.0, 1.0, float("nan"))
        with self.assertRaises(ValueError):
            s.ControleAltura().passo(0.0, 0.0, 0.0)

    def test_frente_vira_norte_ou_leste_conforme_o_nariz(self):
        n, e = s.para_mundo(3.0, 0.0, 90.0)
        self.assertAlmostEqual(n, 0.0)
        self.assertAlmostEqual(e, 3.0)
        f, d = s.para_corpo(n, e, 90.0)
        self.assertAlmostEqual(f, 3.0)
        self.assertAlmostEqual(d, 0.0)

    def test_mover_para_frente_manda_pitch_positivo_e_limitado(self):
        class T:
            lat, lon, yaw, height = 10.0, 20.0, 37.0, 2.0
        m = s.MoverPara(T, frente=5.0)
        for i in range(40):
            out = m.passo(i * 0.05, T, 0.05)
        self.assertGreater(out["pitch"], 0)
        self.assertAlmostEqual(out["roll"], 0.0)
        self.assertLessEqual(out["pitch"], s.DESVIO_MAX_HORIZ)
        self.assertFalse(out["chegou"])

    def test_mover_para_rejeita_gps_invalido_ou_velho(self):
        class T:
            lat, lon, yaw, height = 10.0, 20.0, 0.0, 0.0
            gps_fix, satellites = False, 12
            position_updated = time.monotonic()
        with self.assertRaises(ValueError):
            s.MoverPara(T, norte=1.0)
        T.gps_fix = True
        T.position_updated = 0.0
        with self.assertRaises(ValueError):
            s.MoverPara(T, norte=1.0)
        T.position_updated = time.monotonic() - 5
        with self.assertRaises(ValueError):
            s.MoverPara(T, norte=1.0)
        T.position_updated = time.monotonic()
        T.lat = float("nan")
        with self.assertRaises(ValueError):
            s.MoverPara(T, norte=1.0)

    def test_mover_para_respeita_config_de_forca(self):
        class T:
            lat, lon, yaw, height = 10.0, 20.0, 0.0, 0.0
        config = MovimentoConfig(forca_horizontal=12, forca_vertical_sobe=18,
                                 forca_vertical_desce=25, forca_giro=7)
        mover = s.MoverPara(T, frente=50, altura=10, config=config)
        for i in range(100):
            out = mover.passo(i * 0.1, T, 0.1)
        self.assertLessEqual(abs(out["roll"]), 12)
        self.assertLessEqual(abs(out["pitch"]), 12)
        self.assertLessEqual(out["acel"], 18)
