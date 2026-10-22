"""English handwriting as pen strokes, from a Graves recurrent network.

The weights are the public-domain conversion of the synthesis model in
Alex Graves' paper, shipped as ``assets/stroke/weights.npz``. Inference is
NumPy on one CPU thread: an 8 GB Mac can run it next to the browser. The
network only saw Latin handwriting, so other scripts stay on the font renderer.

A line is a sequence of pen offsets ``(dx, dy, pen-up)``. Sampling the mixture
with a seed gives a new variation of the same words. The same seed repeats.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

from qalam.registry import BACKEND_ROOT

WEIGHTS = BACKEND_ROOT / "assets" / "stroke" / "weights.npz"
HIDDEN = 400
MIXTURES = 20
ATTENTION = 10
ALPHABET = [
    "\x00", " ", "!", '"', "#", "'", "(", ")", ",", "-", ".",
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", ":", ";",
    "?", "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K",
    "L", "M", "N", "O", "P", "R", "S", "T", "U", "V", "W", "Y",
    "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l",
    "m", "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x",
    "y", "z",
]
_INDEX = {char: index for index, char in enumerate(ALPHABET)}


def model_available() -> bool:
    return WEIGHTS.is_file()


def _sigmoid(value: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(value, -40, 40)))


def _softplus(value: np.ndarray) -> np.ndarray:
    return np.logaddexp(value, 0)


class StrokeModel:
    def __init__(self, path: Path | None = None) -> None:
        raw = np.load(path or WEIGHTS)
        self.lstm1_k = raw["lstm1_kernel"]
        self.lstm1_b = raw["lstm1_bias"]
        self.lstm2_k = raw["lstm2_kernel"]
        self.lstm2_b = raw["lstm2_bias"]
        self.lstm3_k = raw["lstm3_kernel"]
        self.lstm3_b = raw["lstm3_bias"]
        self.attn_w = raw["attention_weights"]
        self.attn_b = raw["attention_biases"]
        self.gmm_w = raw["gmm_weights"]
        self.gmm_b = raw["gmm_biases"]

    def write_line(self, text: str, seed: int = 1, bias: float = 0.55) -> np.ndarray:
        """Return ``[T, 3]`` offsets for one line of Latin text."""

        cleaned = "".join(char if char in _INDEX and char != "\x00" else " " for char in text).strip()
        if not cleaned:
            return np.zeros((0, 3), np.float32)
        encoded = np.array([_INDEX[char] for char in cleaned] + [0], dtype=np.int32)
        length = int(encoded.shape[0])
        eye = np.eye(len(ALPHABET), dtype=np.float32)
        onehot = eye[encoded][None, :, :]
        positions = np.arange(length, dtype=np.float32).reshape(1, 1, length)
        mask = np.ones((1, length, 1), np.float32)
        rng = np.random.default_rng(seed & 0xFFFFFFFF)
        h1 = np.zeros((1, HIDDEN), np.float32)
        c1 = np.zeros((1, HIDDEN), np.float32)
        h2 = np.zeros((1, HIDDEN), np.float32)
        c2 = np.zeros((1, HIDDEN), np.float32)
        h3 = np.zeros((1, HIDDEN), np.float32)
        c3 = np.zeros((1, HIDDEN), np.float32)
        kappa = np.zeros((1, ATTENTION), np.float32)
        window = np.zeros((1, len(ALPHABET)), np.float32)
        pen = np.array([[0.0, 0.0, 1.0]], np.float32)
        sharpness = np.array([bias], np.float32)
        max_steps = 36 * length
        strokes = []
        for _ in range(max_steps):
            h1, c1, h2, c2, h3, c3, kappa, window, phi = _step(
                self, h1, c1, h2, c2, h3, c3, kappa, window, pen, onehot, positions, mask
            )
            pen = _sample(self, h3, sharpness, rng)
            strokes.append(pen[0].copy())
            focus = int(np.argmax(phi[0]))
            if focus >= length or (focus >= length - 1 and pen[0, 2] > 0.5):
                break
        if not strokes:
            return np.zeros((0, 3), np.float32)
        return np.stack(strokes).astype(np.float32)


def _lstm(kernel: np.ndarray, bias: np.ndarray, inputs: np.ndarray, hidden: np.ndarray, cell: np.ndarray):
    gates = np.concatenate([inputs, hidden], axis=-1) @ kernel + bias
    chunks = np.split(gates, 4, axis=-1)
    forget = _sigmoid(chunks[2]) * cell + _sigmoid(chunks[0]) * np.tanh(chunks[1])
    hidden = _sigmoid(chunks[3]) * np.tanh(forget)
    return hidden.astype(np.float32), forget.astype(np.float32)


def _step(model: StrokeModel, h1, c1, h2, c2, h3, c3, kappa, window, pen, onehot, positions, mask):
    h1, c1 = _lstm(model.lstm1_k, model.lstm1_b, np.concatenate([window, pen], axis=-1), h1, c1)
    attn_in = np.concatenate([window, pen, h1], axis=-1)
    raw = _softplus(attn_in @ model.attn_w + model.attn_b)
    alpha, beta, kappa_step = np.split(raw, 3, axis=-1)
    kappa = kappa + kappa_step / 25.0
    beta = np.maximum(beta, 0.01)
    diff = kappa[:, :, None] - positions
    phi = np.sum(alpha[:, :, None] * np.exp(-(diff * diff) / beta[:, :, None]), axis=1)
    window = np.sum(phi[:, :, None] * mask * onehot, axis=1).astype(np.float32)
    h2, c2 = _lstm(model.lstm2_k, model.lstm2_b, np.concatenate([pen, h1, window], axis=-1), h2, c2)
    h3, c3 = _lstm(model.lstm3_k, model.lstm3_b, np.concatenate([pen, h2, window], axis=-1), h3, c3)
    return h1, c1, h2, c2, h3, c3, kappa.astype(np.float32), window, phi


def _sample(model: StrokeModel, hidden: np.ndarray, sharpness: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    raw = hidden @ model.gmm_w + model.gmm_b
    pi_logits, sigmas, rhos, mus, eos = np.split(raw, [MIXTURES, 3 * MIXTURES, 4 * MIXTURES, 6 * MIXTURES], axis=-1)
    column = sharpness[:, None]
    pi_logits = pi_logits * (1.0 + column)
    sigmas = np.exp(sigmas - column)
    pi = np.exp(pi_logits - pi_logits.max(axis=-1, keepdims=True))
    pi = pi / pi.sum(axis=-1, keepdims=True)
    pi = np.where(pi < 0.01, 0, pi)
    pi = pi / np.maximum(pi.sum(axis=-1, keepdims=True), 1e-8)
    sigmas = np.maximum(sigmas, 1e-4)
    rhos = np.clip(np.tanh(rhos), -0.999, 0.999)
    eos = np.clip(_sigmoid(eos), 1e-4, 1 - 1e-4)
    choice = int(rng.choice(MIXTURES, p=pi[0]))
    mu_x, mu_y = np.split(mus, 2, axis=-1)
    sigma_x, sigma_y = np.split(sigmas, 2, axis=-1)
    z1 = float(rng.normal())
    z2 = float(rng.normal())
    rho = float(rhos[0, choice])
    dx = float(mu_x[0, choice] + sigma_x[0, choice] * z1)
    dy = float(mu_y[0, choice] + sigma_y[0, choice] * (rho * z1 + np.sqrt(max(1 - rho * rho, 0)) * z2))
    up = 1.0 if float(rng.random()) < float(eos[0, 0]) else 0.0
    return np.array([[dx, dy, up]], np.float32)


@lru_cache(maxsize=1)
def get_model() -> StrokeModel:
    return StrokeModel()


@lru_cache(maxsize=64)
def cached_line(text: str, seed: int, bias_milli: int) -> tuple:
    strokes = get_model().write_line(text, seed=seed, bias=bias_milli / 1000)
    return tuple(map(tuple, strokes.tolist()))


def polylines(offsets: np.ndarray) -> list[np.ndarray]:
    """Absolute strokes. Y grows downward. A pen-up ends the current stroke."""

    if len(offsets) == 0:
        return []
    coords = np.cumsum(offsets[:, :2], axis=0)
    coords[:, 1] *= -1
    parts: list[list[list[float]]] = []
    current: list[list[float]] = []
    previous_up = True
    for (x, y), up in zip(coords, offsets[:, 2]):
        if previous_up:
            if len(current) >= 2:
                parts.append(current)
            current = [[float(x), float(y)]]
        else:
            current.append([float(x), float(y)])
        previous_up = bool(up > 0.5)
    if len(current) >= 2:
        parts.append(current)
    return [np.array(part, np.float32) for part in parts if len(part) >= 2]
