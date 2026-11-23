"""Roteiro de música -> eventos MIDI -> arquivo .mid ou .wav (som interno ou VST por pista).

Roteiro (uma linha por trecho):
    Intro A: C
    Var A: C Am F G7
    Fill A: G7
    Var B: C Am Dm G7 | C Am F G
    Final A: C
Cada palavra é um compasso. Dois acordes no mesmo compasso: "C,Am" (metade cada).
"|" é só para organizar (ignorado).
"""
from __future__ import annotations

import mido
import numpy as np

from .acordes import ACORDE, FUNDAMENTAL, MELODIA, ACORDE_PADRAO, parse_acorde, transpor_nota
from .ritmo import PPQ, Ritmo, SECOES


def parse_roteiro(texto: str) -> list[tuple[str, list[list]]]:
    trechos = []
    for nlinha, linha in enumerate(texto.splitlines(), 1):
        linha = linha.split("#")[0].strip()
        if not linha:
            continue
        if ":" not in linha:
            raise ValueError(f"Linha {nlinha}: use 'Seção: acordes' (ex.: 'Var A: C Am F G').")
        sec, acs = linha.split(":", 1)
        sec = " ".join(sec.split()).title().replace("Var ", "Var ")
        sec = {s.lower(): s for s in SECOES}.get(sec.lower())
        if not sec:
            raise ValueError(f"Linha {nlinha}: seção desconhecida. Use: {', '.join(SECOES)}")
        compassos = []
        for tok in acs.replace("|", " ").split():
            compassos.append([parse_acorde(a) for a in tok.split(",") if a])
        trechos.append((sec, compassos))
    if not trechos:
        raise ValueError("Roteiro vazio.")
    return trechos


def gerar_eventos(ritmo: Ritmo, roteiro) -> tuple[list, int]:
    """Devolve ([(tick, mido.Message)], total_de_ticks)."""
    tc = ritmo.ticks_compasso
    eventos = []
    t0 = 0
    for nome, compassos_acordes in roteiro:
        sec = ritmo.secoes[nome]
        if sec.vazia:
            continue
        n_comp = max(sec.compassos, len(compassos_acordes))
        if nome.startswith(("Fill", "Break", "Intro", "Final")):
            n_comp = sec.compassos
        mudancas = []
        ultimo = ACORDE_PADRAO
        for c in range(n_comp):
            acs = compassos_acordes[c] if c < len(compassos_acordes) else [None]
            for k, ac in enumerate(acs):
                ultimo = ac or ultimo
                mudancas.append((c * tc + k * tc // len(acs), ultimo))

        def acorde_em(t):
            atual = mudancas[0][1]
            for tm, ac in mudancas:
                if tm <= t:
                    atual = ac
            return atual

        limites = sorted({tm for tm, _ in mudancas}) + [n_comp * tc]
        fontes = [(i, notas, None) for i, notas in sec.pistas.items()] + \
                 [(cam.pista, cam.notas, cam) for cam in sec.camadas]
        for c in range(n_comp):
            base = c * tc
            loop_ini = (c % sec.compassos) * tc
            for i, notas, cam in fontes:
                cfg = ritmo.pistas[i]
                if cfg.mudo:
                    continue
                regra = cam.regra if cam else cfg.regra
                faixa = tuple(cam.faixa if cam else cfg.faixa)
                for n in notas:
                    if not (loop_ini <= n.ini < loop_ini + tc):
                        continue
                    ini = base + n.ini - loop_ini
                    fim = min(ini + n.dur, n_comp * tc)
                    pedacos = [(ini, fim)]
                    if regra in (ACORDE, FUNDAMENTAL) or cam is not None:   # corta na troca de acorde
                        pedacos, a = [], ini
                        for lim in limites:
                            if a < lim < fim:
                                pedacos.append((a, lim)); a = lim
                        pedacos.append((a, fim))
                        if regra == FUNDAMENTAL:
                            pedacos = pedacos[:1]
                        elif regra != ACORDE:                                 # melodia/bypass: não retoca
                            pedacos = [(pedacos[0][0], fim)] if cam is None or sec.camada_toca(cam, acorde_em(ini)) else []
                    for k, (a, b) in enumerate(pedacos):
                        ac = acorde_em(a)
                        if cam is not None and not sec.camada_toca(cam, ac):
                            if k == 0 or regra == ACORDE:
                                break
                            continue
                        if cam is None:
                            nota = transpor_nota(n.nota, regra, faixa, ac)
                        else:
                            nota = transpor_nota(n.nota, regra, faixa, ac, cam.acorde_fonte(), cam.tecla_alta)
                        nota = max(0, min(127, cfg.nota_saida(nota)))
                        vel = n.vel if k == 0 else max(1, int(n.vel * 0.85))
                        eventos.append((t0 + a, mido.Message("note_on", channel=cfg.canal, note=nota, velocity=vel)))
                        eventos.append((t0 + max(a + 1, b - 2),
                                        mido.Message("note_off", channel=cfg.canal, note=nota, velocity=0)))
        t0 += n_comp * tc
    eventos.sort(key=lambda e: (e[0], 0 if e[1].type == "note_off" else 1))
    return eventos, t0


def salvar_midi(ritmo: Ritmo, eventos: list, caminho: str, bpm: float | None = None):
    bpm = bpm or ritmo.bpm
    mid = mido.MidiFile(type=1, ticks_per_beat=PPQ)
    guia = mido.MidiTrack()
    guia.append(mido.MetaMessage("track_name", name=ritmo.nome, time=0))
    guia.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
    guia.append(mido.MetaMessage("time_signature", numerator=ritmo.compasso[0], denominator=ritmo.compasso[1], time=0))
    mid.tracks.append(guia)
    for cfg in ritmo.pistas:
        evs = [(t, m) for t, m in eventos if m.channel == cfg.canal]
        if not evs:
            continue
        trk = mido.MidiTrack()
        trk.append(mido.MetaMessage("track_name", name=cfg.nome, time=0))
        if cfg.programa is not None:
            trk.append(mido.Message("program_change", channel=cfg.canal, program=cfg.programa, time=0))
        trk.append(mido.Message("control_change", channel=cfg.canal, control=7, value=int(cfg.volume * 127), time=0))
        agora = 0
        for t, m in evs:
            trk.append(m.copy(time=t - agora)); agora = t
        mid.tracks.append(trk)
    mid.save(caminho)


def gravacao_para_midi(ritmo: Ritmo, gravacao: list, caminho: str, bpm: float):
    """Salva o que foi tocado ao vivo (lista de (tick, msg) do Tocador)."""
    evs = [(t, m) for t, m in gravacao if m.type in ("note_on", "note_off")]
    if evs:
        t0 = evs[0][0]
        evs = [(t - t0, m) for t, m in evs]
    salvar_midi(ritmo, evs, caminho, bpm)


def renderizar(ritmo: Ritmo, eventos: list, total_ticks: int, caminho_wav: str,
               bpm: float | None = None, usar_vst: bool = True, progresso=None, sr: int = 44100) -> dict:
    """Mistura as 8 pistas em WAV. Pista com VST usa o plugin; as outras, o som interno."""
    import soundfile as sf
    from .sintetizador import Sintetizador

    bpm = bpm or ritmo.bpm
    seg = lambda tick: tick / PPQ * 60 / bpm
    duracao = seg(total_ticks)
    n_total = int((duracao + 2.0) * sr)
    mix = np.zeros((n_total, 2), dtype=np.float32)
    usados = {}
    pistas_com_notas = [p for p in ritmo.pistas if any(m.channel == p.canal for _, m in eventos)]
    for k, cfg in enumerate(pistas_com_notas):
        if progresso:
            progresso(k / max(1, len(pistas_com_notas)), cfg.nome)
        evs = [(seg(t), m) for t, m in eventos if m.channel == cfg.canal]
        audio = None
        if usar_vst and cfg.vst:
            try:
                from .vst import InstrumentoVST
                inst = InstrumentoVST(cfg.vst, cfg.vst_estado)
                audio = inst.renderizar(evs, duracao, sr) * cfg.volume
                usados[cfg.nome] = "VST: " + cfg.vst
            except Exception as e:
                usados[cfg.nome] = f"som interno (VST falhou: {e})"
        if audio is None:
            s = Sintetizador({cfg.canal: (cfg.som_interno, cfg.volume)}, sr)
            s.volume_geral = 1.0
            audio = s.renderizar(evs, duracao)
            usados.setdefault(cfg.nome, "som interno: " + cfg.som_interno)
        n = min(len(audio), n_total)
        mix[:n] += audio[:n].astype(np.float32)
    pico = float(np.max(np.abs(mix))) or 1.0
    mix = mix / pico * 0.89
    corte = int((duracao + 1.2) * sr)
    sf.write(caminho_wav, mix[:corte], sr)
    if progresso:
        progresso(1.0, "pronto")
    return {"arquivo": caminho_wav, "duracao_s": round(duracao, 2), "pistas": usados}
