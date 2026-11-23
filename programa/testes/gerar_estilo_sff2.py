"""Gera um estilo Yamaha SFF2 sintético (sem material de terceiros) para os testes.

Cobre: divisão 1920, marcadores SFF2/SInt, timbres na SInt, dois CSEG com regras diferentes,
Ctb2 com 3 zonas, Ctab + Cntt, camadas maior/menor no mesmo destino (Chord Mute), Note Mute,
canal de origem diferente do destino e canal sem regra no segundo CSEG (não toca).

Uso: python gerar_estilo_sff2.py <saida.sty>
"""
import os
import struct
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from nucleo.estilo_yamaha import _bloco, _meta, _vl   # noqa: E402

DIV = 1920
Q = DIV            # semínima
BAR = 4 * Q

MAIORES = [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B,
           0x1C, 0x1D, 0x1E, 0x1F, 0x20, 0x21]
MENORES = [0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x12]


def chord_mute(tocam):
    cm = [0x04, 0, 0, 0, 0]                 # byte 13 bit 2 = autostart
    for c in tocam:
        cm[4 - c // 8] |= 1 << (c % 8)
    return cm


def note_mute(raizes_tocam):
    b11 = sum(1 << (r - 8) for r in range(8, 12) if r in raizes_tocam)
    b12 = sum(1 << r for r in range(8) if r in raizes_tocam)
    return [b11, b12]


def parte1(origem, nome, destino, tocam=None, raizes=None, fonte_raiz=0, fonte_tipo=0x02):
    nome8 = nome.encode()[:8].ljust(8, b" ")
    return (bytes([origem]) + nome8 + bytes([destino, 0]) + bytes(note_mute(raizes if raizes is not None else range(12)))
            + bytes(chord_mute(tocam if tocam is not None else MAIORES + MENORES)) + bytes([fonte_raiz, fonte_tipo]))


def ctab(origem, nome, destino, ntr, ntt, hk=6, lo=0, hi=127, **kw):
    return _bloco(b"Ctab", parte1(origem, nome, destino, **kw) + bytes([ntr, ntt, hk, lo, hi, 3, 0]))


def ctb2(origem, nome, destino, mid_lo, mid_hi, zonas, **kw):
    corpo = parte1(origem, nome, destino, **kw) + bytes([mid_lo, mid_hi])
    for (ntr, ntt, hk, lo, hi) in zonas:
        corpo += bytes([ntr, ntt, hk, lo, hi, 3])
    corpo += bytes([0, 0, 0, 0, 0x80, 0, 0])
    return _bloco(b"Ctb2", corpo)


def gerar(caminho):
    ev = []

    def nota(t, ch, n, v, d):
        ev.append((t, 3, bytes([0x90 | ch, n, v])))
        ev.append((t + d, 2, bytes([0x80 | ch, n, 0])))

    ev.append((0, 0, _meta(0x03, b"TesteSFF2")))
    ev.append((0, 0, _meta(0x58, bytes([4, 2, 24, 8]))))
    ev.append((0, 0, _meta(0x51, (600000).to_bytes(3, "big"))))          # 100 BPM
    ev.append((0, 0, _meta(0x06, b"SFF2")))
    ev.append((0, 0, _meta(0x06, b"SInt")))
    for ch, prog, vol in ((8, 0, 90), (9, 0, 100), (10, 33, 105), (11, 25, 80), (13, 48, 60), (14, 21, 85)):
        ev.append((0, 1, bytes([0xC0 | ch, prog])))
        ev.append((0, 1, bytes([0xB0 | ch, 7, vol])))
    t = BAR
    secoes = [("Intro A", 1), ("Main A", 2), ("Main B", 2), ("Fill In AA", 1), ("Fill In BA", 1), ("Ending A", 2)]
    for nome, bars in secoes:
        ev.append((t, 0, _meta(0x06, nome.encode())))
        for b in range(bars):
            base = t + b * BAR
            for k in range(8):                                             # chimbal + bumbo/caixa
                nota(base + k * Q // 2, 9, 42, 80 + 10 * (k % 2 == 0), Q // 4)
            for k, n in ((0, 36), (1, 38), (2, 36), (3, 38)):
                nota(base + k * Q, 9, n, 110, Q // 4)
            nota(base + 2 * Q, 8, 54, 90, Q // 4)                          # pandeiro
            if nome.startswith(("Main", "Intro", "Ending", "Fill")):
                for k, n in enumerate((36, 43, 40, 43)):                   # baixo maior (origem 10)
                    nota(base + k * Q, 10, n, 105, Q - 20)
                for k, n in enumerate((36, 43, 39, 43)):                   # baixo menor (origem 1, fonte Cm7)
                    nota(base + k * Q, 1, n, 105, Q - 20)
                for k in (1, 3):                                           # acorde com 3 zonas (origem 11)
                    for n in (40, 52, 55, 59, 64, 72):
                        nota(base + k * Q, 11, n, 85, Q // 2)
                for n in (60, 64, 67, 71):                                 # pad (origem 13): Note Mute em C#/F#
                    nota(base, 13, n, 60, BAR - 30)
                for k, n in enumerate((67, 69, 71, 72)):                   # frase (origem 14, Ctab + Cntt)
                    nota(base + 2 * Q + k * Q // 2, 14, n, 90, Q // 2 - 10)
        t += bars * BAR
    ev.append((t, 9, _meta(0x2F, b"")))
    ev.sort(key=lambda e: (e[0], e[1]))
    trilha, agora = bytearray(), 0
    for tick, _o, b in ev:
        trilha += _vl(tick - agora) + b
        agora = tick

    regras_comuns = (ctab(8, "Perc", 8, 0, 0) + ctab(9, "Drums", 9, 0, 0) +
                     ctab(10, "BassMaj", 10, 0, 0x03, lo=28, hi=48, tocam=MAIORES) +
                     ctab(1, "BassMin", 10, 0, 0x03, hk=4, lo=28, hi=48, tocam=MENORES, fonte_tipo=0x0A) +
                     ctab(13, "Pad", 13, 1, 0x02, lo=50, hi=80, raizes=[r for r in range(12) if r not in (1, 6)]))
    cseg1 = _bloco(b"CSEG", _bloco(b"Sdec", b"Intro A,Main A,Fill In AA,Ending A") + regras_comuns +
                   ctb2(11, "Guitar", 11, 48, 70, [(0, 0x81, 6, 28, 50), (1, 0x02, 6, 50, 76), (0, 0x01, 7, 60, 90)]) +
                   ctab(14, "Phrase", 14, 0, 0x02, lo=60, hi=88) + _bloco(b"Cntt", bytes([14, 0x01])))
    cseg2 = _bloco(b"CSEG", _bloco(b"Sdec", b"Main B,Fill In BA") + regras_comuns +
                   ctb2(11, "GuitarB", 11, 40, 100, [(0, 0x01, 6, 28, 50), (0, 0x01, 6, 50, 80), (0, 0x01, 6, 60, 90)]))
    # (no segundo CSEG não há regra para a origem 14: a frase não toca em Main B / Fill In BA)
    dados = (_bloco(b"MThd", struct.pack(">HHH", 0, 1, DIV)) + _bloco(b"MTrk", bytes(trilha)) +
             _bloco(b"CASM", cseg1 + cseg2) + _bloco(b"OTSc", b"\x00" * 16))
    with open(caminho, "wb") as f:
        f.write(dados)
    return caminho


if __name__ == "__main__":
    print(gerar(sys.argv[1] if len(sys.argv) > 1 else "TesteSFF2.sty"))
