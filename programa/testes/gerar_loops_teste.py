"""Gera loops de bateria sintéticos com o gabarito de cada batida (para medir o acerto do detector).

Saída: teste_<nome>.wav + teste_<nome>.json  (lista de {tempo_s, peca, vel})
"""
import json
import sys

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt, fftconvolve

SR = 44100
rng = np.random.default_rng(7)


def _env(n, decay):
    t = np.arange(n) / SR
    return np.exp(-t / decay)


def bumbo(vel):
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    f = 45 + 85 * np.exp(-t / 0.03)
    fase = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(fase) * _env(n, 0.12)
    clique = sosfilt(butter(2, 2000, "hp", fs=SR, output="sos"), rng.standard_normal(n)) * _env(n, 0.004) * 0.3
    return (s + clique) * vel


def caixa(vel):
    n = int(0.3 * SR)
    t = np.arange(n) / SR
    corpo = np.sin(2 * np.pi * 190 * t) * _env(n, 0.05) * 0.6
    ruido = sosfilt(butter(2, [1200, 7000], "bp", fs=SR, output="sos"), rng.standard_normal(n)) * _env(n, 0.09)
    return (corpo + ruido * 0.9) * vel


def chimbal(vel, aberto=False):
    n = int((0.5 if aberto else 0.12) * SR)
    s = sosfilt(butter(4, 7000, "hp", fs=SR, output="sos"), rng.standard_normal(n))
    return s * _env(n, 0.25 if aberto else 0.025) * vel * 0.55


SONS = {"bumbo": bumbo, "caixa": caixa, "chimbal": lambda v: chimbal(v),
        "chimbal_aberto": lambda v: chimbal(v, True)}


def render(eventos, dur, ruido=0.0, reverb=0.0):
    out = np.zeros(int(dur * SR) + SR)
    for e in eventos:
        s = SONS[e["peca"]](e["vel"] / 127)
        i = int(e["tempo_s"] * SR)
        out[i:i + len(s)] += s
    if reverb:
        ir_n = int(0.8 * SR)
        cauda = rng.standard_normal(ir_n) * _env(ir_n, 0.18)
        cauda *= reverb / np.sqrt(np.sum(cauda ** 2))      # energia da cauda = `reverb` x som direto
        cauda[0] = 1.0
        out = fftconvolve(out, cauda)[: len(out)]
    if ruido:
        out += rng.standard_normal(len(out)) * ruido
    out = out[: int(dur * SR)]
    return out / np.max(np.abs(out)) * 0.9


def padrao(bpm, compassos, grade, swing=0.0, humano_ms=0.0):
    """grade: dict peca -> lista de posições em semicolcheias (0..15) com velocity."""
    seg = 60 / bpm / 4
    ev = []
    for c in range(compassos):
        for peca, hits in grade.items():
            for pos, vel in hits:
                t = (c * 16 + pos) * seg
                if pos % 2 == 1:
                    t += swing * seg
                t += rng.normal(0, humano_ms / 1000) if humano_ms else 0
                ev.append({"tempo_s": max(0.0, t), "peca": peca,
                           "vel": int(np.clip(vel + rng.integers(-8, 9), 30, 127))})
    return sorted(ev, key=lambda e: e["tempo_s"]), compassos * 16 * seg


CASOS = {
    # Pop / arrocha, limpo
    "pop_100bpm": dict(bpm=100, compassos=2, grade={
        "bumbo": [(0, 115), (6, 100), (8, 110)],
        "caixa": [(4, 110), (12, 110)],
        "chimbal": [(p, 90 if p % 4 == 0 else 70) for p in range(0, 14, 2)],
        "chimbal_aberto": [(14, 95)],
    }),
    # Forró-pé-de-serra estilizado, semicolcheias, com swing, humanizado, ruído e reverb
    "forro_120bpm_humano": dict(bpm=120, compassos=2, swing=0.12, humano=6, ruido=0.004, reverb=0.25, grade={
        "bumbo": [(0, 115), (3, 90), (8, 115), (11, 90)],
        "caixa": [(4, 100), (12, 105), (14, 70)],
        "chimbal": [(p, 85 if p % 2 == 0 else 60) for p in range(16)],
    }),
}

if __name__ == "__main__":
    pasta = sys.argv[1] if len(sys.argv) > 1 else "."
    for nome, c in CASOS.items():
        ev, dur = padrao(c["bpm"], c["compassos"], c["grade"], c.get("swing", 0), c.get("humano", 0))
        # bumbo e chimbal no mesmo tempo: comum, e o detector precisa achar os dois
        audio = render(ev, dur, c.get("ruido", 0), c.get("reverb", 0))
        sf.write(f"{pasta}/teste_{nome}.wav", audio, SR)
        with open(f"{pasta}/teste_{nome}.json", "w") as f:
            json.dump({"bpm": c["bpm"], "eventos": ev}, f, indent=1)
        print(f"teste_{nome}.wav  {dur:.2f}s  {len(ev)} batidas")
