"""Testes locais, sem rede, drone ou janela."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from modelo import MLP, np
from ambiente import ROOT, Mundo, MODELOS, PROFESSOR, episodio


class OfflineTests(unittest.TestCase):
    def test_entrada_e_rotulo_dagger(self):
        def constante(x):
            self.assertEqual(x.shape, (22,))
            return np.array([12.5, -7.25])

        _, xs, ys = episodio("medido", 17000, constante, coletar=True)
        w = Mundo("medido", 17000)
        w.medir(0.)
        expected = np.tile([w.sx, w.sy, w.vsx, w.vsy], 5)
        np.testing.assert_allclose(xs[0][:20], expected)
        np.testing.assert_allclose(xs[0][-2:], 0)
        np.testing.assert_allclose(xs[1][-2:], [12.5, -7.25])
        for x, y in zip(xs, ys):
            np.testing.assert_allclose(y, PROFESSOR.comando(*x[16:20]))
        self.assertTrue(any(not np.allclose(y, [12.5, -7.25]) for y in ys))

    def test_mundo_original_e_atraso_local(self):
        baseline = episodio("antigo", 17001)[0]
        episodio("antigo", 17001, atraso=.05)
        self.assertEqual(baseline, episodio("antigo", 17001)[0])
        for nome in MODELOS:
            self.assertEqual(Mundo(nome, 1).m["atraso"], .4 if nome == "antigo" else .15)

    def test_pesos_saida_e_aprendizado(self):
        model = MLP()
        rng = np.random.default_rng(1)
        x = rng.normal(size=(1024, 22))
        y = np.tanh(x[:, :2]) * 60
        before = np.mean((model(x) - y) ** 2)
        stats = model.fit(x[:800], y[:800], x[800:], y[800:], epochs=30)
        self.assertLess(stats["validation_mse_percent2"], before)
        self.assertLessEqual(np.max(np.abs(model(x * 1000))), 100)
        with tempfile.TemporaryDirectory(dir=ROOT / "ia") as tmp:
            path = Path(tmp) / "teste.npz"
            model.save(path)
            np.testing.assert_array_equal(model(x), MLP.load(path)(x))

    def test_simulacao_sem_rede(self):
        with patch("socket.socket", side_effect=AssertionError("Rede proibida")):
            a = episodio("velocidade", 17002, MLP())[0]
            b = episodio("velocidade", 17002, MLP())[0]
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
