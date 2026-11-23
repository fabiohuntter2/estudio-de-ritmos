"""
Estúdio de Ritmos — Protótipo Loop de Bateria -> MIDI
=====================================================

Etapas (Módulo 1 da especificação):
  1. Carrega o loop (WAV, MP3, AIFF...) e remove o silêncio do início.
  2. Analisa a energia em 4 faixas de frequência a cada ~6 ms:
        grave  (30–150 Hz)   -> bumbo
        corpo  (150–350 Hz)  -> corpo da caixa
        médio  (1–5 kHz)     -> esteira da caixa
        agudo  (8–16 kHz)    -> chimbal
  3. Procura ataques (subidas bruscas de energia) em cada faixa e decide a peça.
     Bumbo e chimbal no mesmo instante são detectados separadamente.
  4. Diferencia chimbal fechado de aberto pelo tempo de decaimento.
  5. Descobre o BPM usando o tamanho do loop (um loop tem um número inteiro de tempos).
  6. Quantiza (opcional, 0–100%) e grava o MIDI no mapa General MIDI.

Este é um detector por regras, para validar o fluxo. A versão do produto troca a
etapa 3 por um modelo treinado (ex.: ADTOF), mantendo as outras etapas.

Uso:
  python loop_para_midi.py meu_loop.wav                       -> meu_loop.mid
  python loop_para_midi.py meu_loop.wav --quantizar 70 --bpm 128 --saida bateria.mid
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict

import librosa
import mido
import numpy as np

SR = 44100
HOP = 256                      # ~5,8 ms
NFFT = 2048
PPQ = 480

GM = {"bumbo": 36, "caixa": 38, "tom": 45, "chimbal": 42, "chimbal_aberto": 46}

FAIXAS = {"grave": (30, 150), "corpo": (150, 350), "medio": (1000, 5000), "agudo": (8000, 16000)}


@dataclass
class Batida:
    tempo_s: float
    peca: str
    vel: int


def _energias(y: np.ndarray) -> tuple[dict[str, np.ndarray], np.ndarray]:
    S = np.abs(librosa.stft(y, n_fft=NFFT, hop_length=HOP)) ** 2
    freqs = librosa.fft_frequencies(sr=SR, n_fft=NFFT)
    db = {}
    for nome, (lo, hi) in FAIXAS.items():
        e = S[(freqs >= lo) & (freqs < hi)].sum(axis=0)
        db[nome] = 10 * np.log10(e + 1e-10)
    tempos = librosa.frames_to_time(np.arange(S.shape[1]), sr=SR, hop_length=HOP)
    return db, tempos


def _subida(db: np.ndarray, atras: int = 3) -> np.ndarray:
    """Quanto a energia subiu (em dB) em relação ao menor valor dos quadros anteriores."""
    ant = np.full_like(db, np.inf)
    for k in range(1, atras + 1):
        ant = np.minimum(ant, np.concatenate([np.full(k, db[0]), db[:-k]]))
    return np.clip(db - ant, 0, None)


def _picos(sinal: np.ndarray, limiar: float, distancia: int) -> list[int]:
    """Máximos locais acima do limiar, separados por pelo menos `distancia` quadros."""
    idx = [i for i in range(1, len(sinal) - 1)
           if sinal[i] >= limiar and sinal[i] >= sinal[i - 1] and sinal[i] > sinal[i + 1]]
    escolhidos: list[int] = []
    for i in sorted(idx, key=lambda i: -sinal[i]):
        if all(abs(i - j) >= distancia for j in escolhidos):
            escolhidos.append(i)
    return sorted(escolhidos)


def _velocity(nivel_db: float, maximo_db: float) -> int:
    # 0 dB abaixo do máximo -> 127; 24 dB abaixo -> 40
    return int(np.clip(127 - (maximo_db - nivel_db) * (87 / 24), 40, 127))


PAD_S = 0.05   # silêncio colocado antes do áudio, para a primeira batida ter um "antes"


def detectar(y: np.ndarray, sensibilidade: float = 1.0) -> list[Batida]:
    y = np.concatenate([np.zeros(int(PAD_S * SR)), y])
    db, tempos = _energias(y)
    tempos = tempos - PAD_S
    n = len(tempos)
    q = lambda ms: max(1, int(ms / 1000 * SR / HOP))
    # Teto de cada faixa (percentil alto, para não depender de um único pico)
    teto = {k: np.percentile(v, 99.5) for k, v in db.items()}
    s = sensibilidade

    def subida(f, i):
        """Subida em dB: pico logo após o ataque menos o mínimo logo antes."""
        antes = db[f][max(0, i - q(25)): i].min() if i > 0 else db[f][0]
        return db[f][i: i + 3].max() - antes

    def nivel(f, i):
        return db[f][i: i + 3].max()

    def forte(f, i, faixa_db):
        """O ataque é alto o bastante em relação ao teto da faixa (descarta vazamento e ruído)."""
        return nivel(f, i) >= teto[f] - faixa_db * s

    def decaimento(f, i, ms):
        j = min(i + q(ms), n - 1)
        return nivel(f, i) - db[f][j]

    # 1) Ataques candidatos: união dos picos de subida de cada faixa (cobre batidas simultâneas)
    candidatos = set()
    for f in FAIXAS:
        sub = _subida(db[f])
        candidatos.update(_picos(sub, 6.0 / s, q(30)))
    candidatos = sorted(candidatos)
    # junta candidatos a menos de 20 ms (o mesmo golpe visto por faixas diferentes)
    grupos: list[int] = []
    for i in candidatos:
        if grupos and i - grupos[-1] < q(20):
            continue
        grupos.append(i)

    # 2) Classificação de cada ataque (pode ter mais de uma peça)
    # O grave (bumbo 808, zabumba) cresce devagar: mede o nível dele numa janela de 40 ms
    jan = {"grave": q(40), "corpo": q(25), "medio": 3, "agudo": 3}

    def nivel_j(f, i):
        return db[f][i: i + jan[f]].max()

    teto_j = {f: np.percentile([nivel_j(f, i) for i in range(n)], 99.5) for f in FAIXAS}
    rel = lambda f, i: nivel_j(f, i) - teto_j[f]          # 0 dB = o mais forte do loop nessa faixa

    batidas: list[Batida] = []
    chimbais: list[tuple[float, int, float]] = []
    candidatos_caixa: list[tuple[float, float, bool]] = []
    for i in grupos:
        t = float(tempos[i])
        if t < -0.01:
            continue
        t = max(t, 0.0)
        g_sub, c_sub, m_sub, a_sub = (subida(f, i) for f in ("grave", "corpo", "medio", "agudo"))
        g, c, m, a = (rel(f, i) for f in ("grave", "corpo", "medio", "agudo"))

        bumbo = g_sub >= 12 and g >= -24 / s and g >= c - 6
        if bumbo:
            batidas.append(Batida(t, "bumbo", _velocity(g, 0)))

        # Tom / marcação: corpo (150–350 Hz) forte e sustentado, sem grave
        tom = (not bumbo and c_sub >= 10 and c >= -10 / s and g < -26
               and db["corpo"][i: i + 3].max() - db["corpo"][min(i + q(60), n - 1)] < 12)
        if tom:
            batidas.append(Batida(t, "tom", _velocity(c, 0)))

        caixa = (not tom and m_sub >= 8 and m >= -14 / s and decaimento("medio", i, 40) < 20
                 and (c_sub >= 6 or nivel("medio", i) > nivel("agudo", i) + 3))
        if caixa:
            candidatos_caixa.append((t, m, bumbo))

        if a_sub >= 6 and a >= -24 / s:
            # Sob uma caixa, o agudo só conta como chimbal se estiver acima do que a esteira explica
            if not caixa or nivel("agudo", i) > nivel("medio", i) - 2:
                chimbais.append((t, _velocity(a, 0), decaimento("agudo", i, 60)))

    # Caixa junto com bumbo: muitos bumbos têm uma camada de médios (ataque, palma).
    # Só conta como caixa se o médio estiver bem acima do típico dos bumbos deste loop.
    if candidatos_caixa:
        so_caixa = [m for _, m, b in candidatos_caixa if not b]
        com_bumbo = [m for _, m, b in candidatos_caixa if b]
        tipico_bumbo = float(np.median(com_bumbo)) if com_bumbo else -99
        for t, m, b in candidatos_caixa:
            if not b or (so_caixa and m > tipico_bumbo + 6) or (not so_caixa and m > -3):
                batidas.append(Batida(t, "caixa", _velocity(m, 0)))

    # Aberto x fechado, relativo ao próprio loop: aberto = decai bem mais devagar que o típico
    if chimbais:
        tipico = float(np.median([d for _, _, d in chimbais]))
        for t, v, d in chimbais:
            aberto = d < 8 and d < tipico - 6
            batidas.append(Batida(t, "chimbal_aberto" if aberto else "chimbal", v))

    return _sem_repeticoes(sorted(batidas, key=lambda b: (b.tempo_s, b.peca)))


def _sem_repeticoes(batidas: list[Batida], janela: float = 0.04) -> list[Batida]:
    """O mesmo golpe visto duas vezes (a menos de 40 ms, mesma peça): fica o mais forte."""
    saida: list[Batida] = []
    for b in batidas:
        rep = next((x for x in reversed(saida) if x.peca == b.peca and b.tempo_s - x.tempo_s < janela), None)
        if rep is None:
            saida.append(b)
        elif b.vel > rep.vel:
            saida[saida.index(rep)] = Batida(rep.tempo_s, b.peca, b.vel)
    return saida


def estimar_bpm(y: np.ndarray, duracao: float) -> float:
    """BPM pelo tamanho do loop: escolhe o número de tempos (múltiplo de 4, de preferência)
    que dá um BPM entre 70 e 180 e fica mais perto da estimativa do librosa."""
    env = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
    est = float(np.atleast_1d(librosa.feature.tempo(onset_envelope=env, sr=SR, hop_length=HOP))[0])
    candidatos = []
    for n in range(2, 129):
        bpm = 60 * n / duracao
        if 70 <= bpm <= 180:
            dist = abs(np.log2(bpm / est))
            dist = min(dist, abs(np.log2(bpm / est) - 1), abs(np.log2(bpm / est) + 1))  # meio/dobro
            candidatos.append((dist + (0 if n % 4 == 0 else 0.15), bpm))
    return round(min(candidatos)[1] if candidatos else est, 2)


def quantizar(batidas: list[Batida], bpm: float, forca: float, divisao: int = 4) -> list[Batida]:
    passo = 60 / bpm / divisao
    out = []
    for b in batidas:
        alvo = round(b.tempo_s / passo) * passo
        out.append(Batida(b.tempo_s + (alvo - b.tempo_s) * forca, b.peca, b.vel))
    return out


def salvar_midi(batidas: list[Batida], bpm: float, duracao: float, caminho: str,
                bpm_arquivo: float | None = None) -> None:
    mid = mido.MidiFile(type=1, ticks_per_beat=PPQ)
    trk = mido.MidiTrack()
    trk.append(mido.MetaMessage("track_name", name="Bateria (do loop)", time=0))
    trk.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm_arquivo or bpm), time=0))
    trk.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    tick = lambda s: int(round(s * bpm / 60 * PPQ))
    ev = []
    for b in batidas:
        t = tick(b.tempo_s)
        ev += [(t, 1, GM[b.peca], b.vel), (t + PPQ // 8, 0, GM[b.peca], 0)]
    ev.sort(key=lambda e: (e[0], e[1]))
    agora = 0
    for t, liga, n, v in ev:
        trk.append(mido.Message("note_on" if liga else "note_off", channel=9, note=n, velocity=v,
                                time=t - agora))
        agora = t
    trk.append(mido.MetaMessage("end_of_track", time=max(0, tick(duracao) - agora)))
    mid.tracks.append(trk)
    mid.save(caminho)


def analisar(caminho: str, bpm: float | None = None, forca_quant: float = 0.0,
             sensibilidade: float = 1.0) -> dict:
    """Analisa o loop e devolve BPM, duração e batidas (sem gravar arquivo)."""
    y, _ = librosa.load(caminho, sr=SR, mono=True)
    inicio = librosa.effects.trim(y, top_db=40)[1][0]
    y = y[inicio:]
    duracao = len(y) / SR
    bpm = bpm or estimar_bpm(y, duracao)
    batidas = detectar(y, sensibilidade)
    if forca_quant > 0:
        batidas = _sem_repeticoes(quantizar(batidas, bpm, forca_quant), janela=0.01)
    bpm_arquivo = float(round(bpm)) if abs(bpm - round(bpm)) < 0.6 else bpm
    return {"bpm": bpm, "bpm_arquivo": bpm_arquivo, "duracao_s": round(duracao, 3),
            "inicio_cortado_s": round(inicio / SR, 4), "batidas": [asdict(b) for b in batidas]}


def converter(caminho: str, saida: str | None = None, bpm: float | None = None,
              forca_quant: float = 0.0, sensibilidade: float = 1.0) -> dict:
    y, _ = librosa.load(caminho, sr=SR, mono=True)
    inicio = librosa.effects.trim(y, top_db=40)[1][0]
    y = y[inicio:]
    duracao = len(y) / SR
    bpm = bpm or estimar_bpm(y, duracao)
    batidas = detectar(y, sensibilidade)
    if forca_quant > 0:
        batidas = quantizar(batidas, bpm, forca_quant)
    saida = saida or caminho.rsplit(".", 1)[0] + ".mid"
    # As notas ficam na posição musical certa (em tempos); o arquivo leva o BPM redondo
    bpm_arquivo = float(round(bpm)) if abs(bpm - round(bpm)) < 0.6 else bpm
    salvar_midi(batidas, bpm, duracao, saida, bpm_arquivo)
    return {"arquivo_midi": saida, "bpm": bpm, "bpm_arquivo": bpm_arquivo, "duracao_s": round(duracao, 3),
            "inicio_cortado_s": round(inicio / SR, 4), "batidas": [asdict(b) for b in batidas]}


def main() -> None:
    ap = argparse.ArgumentParser(description="Converte um loop de bateria em MIDI (General MIDI, canal 10)")
    ap.add_argument("audio")
    ap.add_argument("--saida")
    ap.add_argument("--bpm", type=float, help="força o BPM (senão é detectado)")
    ap.add_argument("--quantizar", type=float, default=0, help="0 a 100 (%%) para a grade de semicolcheias")
    ap.add_argument("--sensibilidade", type=float, default=1.0, help="maior = detecta batidas mais fracas")
    ap.add_argument("--json", action="store_true", help="imprime todas as batidas em JSON")
    a = ap.parse_args()
    r = converter(a.audio, a.saida, a.bpm, a.quantizar / 100, a.sensibilidade)
    if a.json:
        print(json.dumps(r, indent=1, ensure_ascii=False))
        return
    contagem = {}
    for b in r["batidas"]:
        contagem[b["peca"]] = contagem.get(b["peca"], 0) + 1
    print(f"{r['arquivo_midi']}: {r['bpm']} BPM, {r['duracao_s']} s, " +
          ", ".join(f"{v} {k}" for k, v in sorted(contagem.items())))


if __name__ == "__main__":
    main()
