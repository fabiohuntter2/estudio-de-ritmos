"""Sintetizador interno: deixa o programa tocar sem nenhum VST instalado.

Recebe mensagens MIDI (mido) e mistura vozes pré-geradas. Serve para:
  - tocar ao vivo pela placa de som (sounddevice), e
  - renderizar offline para WAV (mesmo motor).
Os timbres são simples — o som de verdade vem do Kontakt/VST.
"""
from __future__ import annotations

import threading
from functools import lru_cache

import numpy as np

SR = 44100
_rng = np.random.default_rng(3)


def _env(n, decay):
    return np.exp(-np.arange(n) / SR / decay)


def _ruido(n):
    return _rng.standard_normal(n)


def _passa_alta(x, fc):
    from scipy.signal import butter, sosfilt
    return sosfilt(butter(2, fc, "hp", fs=SR, output="sos"), x)


def _passa_banda(x, lo, hi):
    from scipy.signal import butter, sosfilt
    return sosfilt(butter(2, [lo, hi], "bp", fs=SR, output="sos"), x)


# ------------------------------------------------------------------ bateria (General MIDI)
@lru_cache(maxsize=128)
def som_bateria(nota: int) -> np.ndarray:
    def seg(s):
        return int(s * SR)

    if nota in (35, 36):                                     # bumbo
        n = seg(0.45); t = np.arange(n) / SR
        f = 48 + 90 * np.exp(-t / 0.03)
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.16)
        x += _passa_alta(_ruido(n), 2000) * _env(n, 0.004) * 0.25
    elif nota in (38, 40):                                   # caixa
        n = seg(0.3); t = np.arange(n) / SR
        x = np.sin(2 * np.pi * 190 * t) * _env(n, 0.05) * 0.5
        x += _passa_banda(_ruido(n), 1200, 7000) * _env(n, 0.09) * 0.9
    elif nota == 37:                                         # aro
        n = seg(0.12); t = np.arange(n) / SR
        x = (np.sin(2 * np.pi * 820 * t) + _passa_banda(_ruido(n), 1500, 5000) * 0.6) * _env(n, 0.02)
    elif nota == 39:                                         # palmas
        n = seg(0.3)
        base = _passa_banda(_ruido(n), 900, 3500)
        e = np.zeros(n)
        for k, d in enumerate((0, 0.011, 0.022)):
            i = seg(d); e[i:] += _env(n - i, 0.012 if k < 2 else 0.08)
        x = base * e * 0.8
    elif nota in (42, 44):                                   # chimbal fechado / pedal
        n = seg(0.12)
        x = _passa_alta(_ruido(n), 7000) * _env(n, 0.025 if nota == 42 else 0.015) * 0.6
    elif nota == 46:                                         # chimbal aberto
        n = seg(0.6)
        x = _passa_alta(_ruido(n), 6500) * _env(n, 0.25) * 0.55
    elif nota in (41, 43, 45, 47, 48, 50):                   # tons
        base = {41: 80, 43: 95, 45: 110, 47: 135, 48: 160, 50: 190}[nota]
        n = seg(0.5); t = np.arange(n) / SR
        f = base + base * 0.4 * np.exp(-t / 0.02)
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.18)
    elif nota in (49, 57, 52, 55):                           # pratos de ataque
        n = seg(1.8)
        x = _passa_alta(_ruido(n), 4000) * _env(n, 0.6) * 0.45
    elif nota in (51, 59, 53):                               # condução
        n = seg(0.9); t = np.arange(n) / SR
        x = (_passa_alta(_ruido(n), 5000) * 0.3 + np.sin(2 * np.pi * 5200 * t) * 0.1) * _env(n, 0.35)
    elif nota == 54:                                         # pandeiro (platinelas)
        n = seg(0.25)
        x = _passa_banda(_ruido(n), 5000, 12000) * _env(n, 0.06) * 0.7
    elif nota in (69, 70, 82):                               # shaker / cabasa
        n = seg(0.09)
        a = np.minimum(1, np.arange(n) / (0.008 * SR))
        x = _passa_alta(_ruido(n), 5000) * a * _env(n, 0.025) * 0.5
    elif nota in (80, 81):                                   # triângulo
        n = seg(1.2 if nota == 81 else 0.15); t = np.arange(n) / SR
        x = sum(np.sin(2 * np.pi * f * t) * a for f, a in ((4100, .5), (5650, .3), (7900, .2)))
        x *= _env(n, 0.5 if nota == 81 else 0.04) * 0.4
    elif nota in (56, 67, 68):                               # cowbell / agogô
        n = seg(0.3); t = np.arange(n) / SR
        f1, f2 = (800, 540) if nota != 68 else (650, 440)
        x = (np.sign(np.sin(2 * np.pi * f1 * t)) * .4 + np.sign(np.sin(2 * np.pi * f2 * t)) * .4)
        x = _passa_banda(x, 400, 4000) * _env(n, 0.07)
    elif nota in (60, 61, 62, 63, 64):                       # bongô / conga
        base = {60: 400, 61: 300, 62: 330, 63: 260, 64: 180}[nota]
        n = seg(0.35); t = np.arange(n) / SR
        x = np.sin(2 * np.pi * base * (1 + 0.15 * np.exp(-t / 0.01)) * t) * _env(n, 0.09)
    else:                                                    # qualquer outra peça: clique curto
        n = seg(0.15)
        x = _passa_banda(_ruido(n), 800, 6000) * _env(n, 0.03) * 0.6
    return (x / (np.max(np.abs(x)) + 1e-9)).astype(np.float32)


# ------------------------------------------------------------------ timbres tonais
SUSTENTADOS = {"pad", "sanfona", "metais", "orgao"}


@lru_cache(maxsize=512)
def som_tonal(tipo: str, nota: int) -> np.ndarray:
    f0 = 440.0 * 2 ** ((nota - 69) / 12)
    dur = 4.0 if tipo in SUSTENTADOS else 2.5
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    limite = SR / 2 - 500

    def harm(k, amp, decay=None, det=0.0):
        f = f0 * k + det
        if f >= limite:
            return
        h = np.sin(2 * np.pi * f * t + k)
        x[:] += h * amp * (np.exp(-t / decay) if decay else 1)

    if tipo == "baixo":
        for k, a in enumerate((1, .55, .3, .15, .08), 1):
            harm(k, a, 1.4 / k ** 0.5)
        x *= np.minimum(1, t / 0.004)
    elif tipo == "violao":
        for k in range(1, 12):
            harm(k, 1 / k, 1.6 / k ** 0.6)
        x *= np.minimum(1, t / 0.002)
    elif tipo == "piano":
        for k in range(1, 9):
            harm(k * (1 + 0.0004 * k * k), 1 / k ** 1.3, 2.8 / k ** 0.7)
        x *= np.minimum(1, t / 0.003)
    elif tipo == "pad":
        for k in range(1, 10):
            harm(k, 1 / k, det=0.0)
            harm(k, 0.7 / k, det=0.35 * k)
        x *= np.minimum(1, t / 0.35)
    elif tipo == "sanfona":
        vib = 1 + 0.004 * np.sin(2 * np.pi * 5.5 * t)
        for k, a in enumerate((1, .7, .5, .45, .3, .25, .15, .1), 1):
            if f0 * k < limite:
                x += np.sin(2 * np.pi * f0 * k * np.cumsum(vib) / SR) * a
                x += np.sin(2 * np.pi * (f0 * k + 1.8) * np.cumsum(vib) / SR) * a * 0.6
        x *= np.minimum(1, t / 0.03)
    elif tipo == "metais":
        brilho = 0.5 + 0.5 * np.exp(-t / 0.25)
        for k in range(1, 12):
            if f0 * k < limite:
                x += np.sin(2 * np.pi * f0 * k * t) / k * (brilho if k > 3 else 1)
        x *= np.minimum(1, t / 0.04)
    else:  # orgao
        for k, a in ((1, 1), (2, .8), (3, .6), (4, .5), (6, .3), (8, .25)):
            harm(k, a)
        x *= np.minimum(1, t / 0.01)
    x /= np.max(np.abs(x)) + 1e-9
    return x.astype(np.float32)


GANHO_TIPO = {"bateria": 0.9, "baixo": 0.8, "violao": 0.35, "piano": 0.35, "pad": 0.22,
              "sanfona": 0.3, "metais": 0.3, "orgao": 0.3}
RELEASE = {"pad": 0.5, "sanfona": 0.12, "metais": 0.12, "orgao": 0.08}


class _Voz:
    __slots__ = ("buf", "pos", "ganho", "canal", "nota", "solta", "rel_total", "rel_rest")

    def __init__(self, buf, ganho, canal, nota):
        self.buf, self.pos, self.ganho = buf, 0, ganho
        self.canal, self.nota = canal, nota
        self.solta = False
        self.rel_total = self.rel_rest = 0


class Sintetizador:
    """Sintetizador polifônico simples. canais: dict canal -> (tipo, volume)."""

    MAX_VOZES = 96

    def __init__(self, canais: dict | None = None, sr: int = SR):
        self.sr = sr
        self.canais = canais or {}
        self.vozes: list[_Voz] = []
        self.lock = threading.Lock()
        self.stream = None
        self.volume_geral = 0.8
        self.vsts: dict = {}            # canal -> InstrumentoVST (ao vivo, experimental)
        self._fila_vst: dict = {}       # canal -> [mido.Message] desde o último bloco
        self.erros_vst: dict = {}

    def ligar_vst(self, canal: int, instrumento):
        with self.lock:
            self.vsts[canal] = instrumento
            self._fila_vst[canal] = []

    def desligar_vst(self, canal: int):
        with self.lock:
            self.vsts.pop(canal, None)
            self._fila_vst.pop(canal, None)

    def configurar_de_ritmo(self, ritmo):
        c = {p.canal: (p.som_interno, 0.0 if p.mudo else p.volume) for p in ritmo.pistas}
        c.setdefault(0, ("piano", 0.7))                      # mão direita
        self.canais = c

    def enviar(self, msg):
        tipo = msg.type
        if getattr(msg, "channel", None) in self.vsts:
            with self.lock:
                self._fila_vst[msg.channel].append(msg)
            return
        if tipo == "note_on" and msg.velocity > 0:
            som, vol = self.canais.get(msg.channel, ("piano", 0.7))
            if vol <= 0:
                return
            buf = som_bateria(msg.note) if som == "bateria" else som_tonal(som, msg.note)
            g = (msg.velocity / 127) ** 1.5 * vol * GANHO_TIPO.get(som, 0.4)
            with self.lock:
                if som == "bateria" and msg.note in (42, 44):         # chimbal fechado corta o aberto
                    for v in self.vozes:
                        if v.canal == msg.channel and v.nota == 46:
                            self._soltar(v, 0.03)
                self.vozes.append(_Voz(buf, g, msg.channel, msg.note))
                if len(self.vozes) > self.MAX_VOZES:
                    self.vozes.pop(0)
        elif tipo == "note_off" or (tipo == "note_on" and msg.velocity == 0):
            som, _ = self.canais.get(msg.channel, ("piano", 0.7))
            if som == "bateria":
                return                                               # bateria toca até o fim
            with self.lock:
                for v in self.vozes:
                    if v.canal == msg.channel and v.nota == msg.note and not v.solta:
                        self._soltar(v, RELEASE.get(som, 0.18))
        elif tipo == "control_change" and msg.control in (120, 123):
            with self.lock:
                for v in self.vozes:
                    if v.canal == msg.channel:
                        self._soltar(v, 0.05)

    def _soltar(self, v, segundos):
        v.solta = True
        v.rel_total = v.rel_rest = max(1, int(segundos * self.sr))

    def misturar(self, frames: int) -> np.ndarray:
        out = np.zeros(frames, dtype=np.float32)
        with self.lock:
            vivas = []
            for v in self.vozes:
                fim = min(len(v.buf), v.pos + frames)
                n = fim - v.pos
                if n <= 0:
                    continue
                trecho = v.buf[v.pos:fim] * v.ganho
                if v.solta:
                    k = min(n, v.rel_rest)
                    env = np.zeros(n, dtype=np.float32)
                    env[:k] = np.linspace(v.rel_rest, v.rel_rest - k, k, endpoint=False) / v.rel_total
                    trecho = trecho * env
                    v.rel_rest -= k
                out[:n] += trecho
                v.pos = fim
                if v.pos < len(v.buf) and not (v.solta and v.rel_rest <= 0):
                    vivas.append(v)
            self.vozes = vivas
        est = np.stack([out, out], axis=1)
        if self.vsts:
            with self.lock:
                pend = {c: self._fila_vst.get(c, []) for c in self.vsts}
                for c in self.vsts:
                    self._fila_vst[c] = []
                vsts = dict(self.vsts)
            for canal, inst in vsts.items():
                try:
                    msgs = [(bytes(m.bytes()), 0.0) for m in pend[canal]]
                    a = inst.plugin(msgs, duration=frames / self.sr, sample_rate=self.sr,
                                    num_channels=2, buffer_size=frames, reset=False)
                    a = np.asarray(a, dtype=np.float32).T[:frames]
                    vol = self.canais.get(canal, ("", 0.8))[1]
                    est[: len(a)] += a * vol
                except Exception as e:                       # VST com problema: desliga e avisa
                    self.erros_vst[canal] = str(e)
                    self.desligar_vst(canal)
        return np.tanh(est * self.volume_geral)              # limitador suave (estéreo)

    # ------------------------------------------------------------------ placa de som
    def iniciar_audio(self, dispositivo=None, bloco=256):
        import sounddevice as sd

        def cb(outdata, frames, _tempo, _status):
            m = self.misturar(frames)
            outdata[:] = m[:, : outdata.shape[1]]

        self.stream = sd.OutputStream(samplerate=self.sr, channels=2, blocksize=bloco,
                                      dtype="float32", callback=cb, device=dispositivo, latency="low")
        self.stream.start()

    def parar_audio(self):
        if self.stream:
            self.stream.stop(); self.stream.close()
            self.stream = None

    # ------------------------------------------------------------------ offline
    def renderizar(self, eventos_seg: list, duracao: float, bloco: int = 256) -> np.ndarray:
        """eventos_seg: lista de (tempo_em_segundos, mido.Message). Devolve áudio estéreo (n, 2)."""
        eventos = sorted(eventos_seg, key=lambda e: e[0])
        total = int((duracao + 1.0) * self.sr)
        out = np.zeros((total, 2), dtype=np.float32)
        i_ev, pos = 0, 0
        while pos < total:
            t_bloco = (pos + bloco) / self.sr
            while i_ev < len(eventos) and eventos[i_ev][0] < t_bloco:
                self.enviar(eventos[i_ev][1]); i_ev += 1
            n = min(bloco, total - pos)
            out[pos:pos + n] = self.misturar(n)
            pos += n
        return out
