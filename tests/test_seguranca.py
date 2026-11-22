"""Testes offline das barreiras de segurança e confirmação de estado."""
import time
import unittest

from predator import armar, bt
from predator.controle import PD, Vigia


class LinkFalso:
    def __init__(self, state=0, mudar_depois=None, confirmar_todo_ciclo=False):
        self.t = {"state": state, "battery": 80}
        self.recebido = 1.0
        self.mudar_depois = mudar_depois
        self.confirmar_todo_ciclo = confirmar_todo_ciclo
        self.ciclos = 0

    @property
    def idade(self):
        return 0.0

    def ciclo(self, _manche, comando=None):
        self.ciclos += 1
        if comando == bt.unlock() and self.mudar_depois == self.ciclos:
            self.t["state"] = 2
            self.recebido += 1
        if self.confirmar_todo_ciclo:
            self.recebido += 1
        time.sleep(0.001)


class TestArmar(unittest.TestCase):
    def test_nao_aceita_estado_armado_antigo(self):
        link = LinkFalso(state=2)
        ok, _ = armar.destravar(link, b"minimo", max_s=0.01, log=lambda _msg: None)
        self.assertFalse(ok)

    def test_aceita_transicao_confirmada_por_telemetria_nova(self):
        link = LinkFalso(state=0, mudar_depois=1)
        ok, segundos = armar.destravar(link, b"minimo", max_s=0.1, log=lambda _msg: None)
        self.assertTrue(ok)
        self.assertIsNotNone(segundos)

    def test_travar_exige_telemetria_posterior(self):
        antigo = LinkFalso(state=0)
        self.assertFalse(armar.travar(antigo, b"minimo", max_s=0.01, log=lambda _msg: None))
        novo = LinkFalso(state=0, confirmar_todo_ciclo=True)
        self.assertTrue(armar.travar(novo, b"minimo", max_s=0.1, log=lambda _msg: None))


class TestControle(unittest.TestCase):
    def test_pd_rejeita_nan(self):
        with self.assertRaises(ValueError):
            PD().comando(float("nan"), 0, 0, 0)

    def test_vigia_pousa_com_telemetria_invalida(self):
        self.assertEqual(Vigia().verifica(1, 0, 0, float("nan")), "telemetria inválida")
