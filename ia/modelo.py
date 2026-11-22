"""Politica numpy offline: 5 observacoes (x,y,vx,vy) e comando anterior."""
import os
import sys

sys.dont_write_bytecode = True
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
import numpy as np


class MLP:
    def __init__(self, seed=42):
        rng = np.random.default_rng(seed)
        self.mean = np.zeros(22)
        self.std = np.ones(22)
        self.params = {}
        for i, (a, b) in enumerate(zip((22, 32, 32), (32, 32, 2))):
            self.params[f"w{i}"] = rng.normal(0, np.sqrt(1 / a), (a, b))
            self.params[f"b{i}"] = np.zeros(b)

    def forward(self, x):
        a = (np.asarray(x) - self.mean) / self.std
        cache = [a]
        for i in range(3):
            a = np.tanh(a @ self.params[f"w{i}"] + self.params[f"b{i}"])
            cache.append(a)
        return a, cache

    def __call__(self, x):
        return self.forward(x)[0] * 100.0

    def fit(self, x, y, xv, yv, epochs=100, patience=10, seed=42):
        rng = np.random.default_rng(seed)
        # Normalizacao fica fixa depois da clonagem, inclusive no DAgger.
        y, yv = y / 100.0, yv / 100.0
        moment = {k: np.zeros_like(v) for k, v in self.params.items()}
        square = {k: np.zeros_like(v) for k, v in self.params.items()}
        best, wait, step = float("inf"), 0, 0
        saved, trace = {}, []
        for epoch in range(epochs):
            order = rng.permutation(len(x))
            for start in range(0, len(x), 512):
                ids = order[start:start + 512]
                pred, acts = self.forward(x[ids])
                grad = (pred - y[ids]) / len(ids)
                grads = {}
                for i in reversed(range(3)):
                    dz = grad * (1 - acts[i + 1] ** 2)
                    grads[f"w{i}"] = acts[i].T @ dz
                    grads[f"b{i}"] = dz.sum(axis=0)
                    grad = dz @ self.params[f"w{i}"].T
                step += 1
                for k in self.params:
                    moment[k] = .9 * moment[k] + .1 * grads[k]
                    square[k] = .999 * square[k] + .001 * grads[k] ** 2
                    self.params[k] -= .001 * (moment[k] / (1 - .9 ** step)) / (
                        np.sqrt(square[k] / (1 - .999 ** step)) + 1e-8)
            loss = float(np.mean((self.forward(xv)[0] - yv) ** 2))
            trace.append(loss)
            if loss < best - 1e-7:
                best, wait = loss, 0
                saved = {k: v.copy() for k, v in self.params.items()}
            else:
                wait += 1
            if wait >= patience:
                break
        self.params = saved
        return {"epochs": epoch + 1, "validation_mse_percent2": best * 10000,
                "trace": trace}

    def save(self, path):
        np.savez(path, mean=self.mean, std=self.std, **self.params)

    @classmethod
    def load(cls, path):
        model = cls()
        with np.load(path, allow_pickle=False) as z:
            model.mean, model.std = z["mean"], z["std"]
            model.params = {k: z[k] for k in model.params}
        return model
