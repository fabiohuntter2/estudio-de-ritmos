"""Estilos Yamaha (.sty, .prs, .sst — SFF1 e SFF2): importar para Ritmo e exportar Ritmo para .sty (SFF1).

Estrutura do arquivo: MThd + MTrk (MIDI tipo 0, seções marcadas: SInt, Intro A, Main A, Fill In AA,
Fill In BA, Ending A...) + CASM (regras de transposição por canal: Ctab/Ctb2/Cntt) + OTSc/MDB (ignorados).
Referência: P. Wierzba & M. Bedesem, "Style Files - Introduction and Details".

A mesma lógica existe em C++ (plugin/Source/nucleo/EstiloYamaha.cpp): os testes comparam as duas.
"""
from __future__ import annotations

import struct

from .acordes import ACORDE, BYPASS, FUNDAMENTAL, MELODIA, TECLA_ALTA_PADRAO
from .ritmo import PPQ, Camada, Nota, Ritmo, SECOES, Secao, pistas_padrao, ticks_do_compasso

YAMAHA_PARA_SECAO = {
    "Intro A": "Intro A", "Intro B": "Intro B", "Intro C": "Intro C",
    "Main A": "Var A", "Main B": "Var B", "Main C": "Var C", "Main D": "Var D",
    "Fill In AA": "Fill A", "Fill In BB": "Fill B", "Fill In CC": "Fill C", "Fill In DD": "Fill D",
    "Fill In BA": "Break",
    "Ending A": "Final A", "Ending B": "Final B", "Ending C": "Final C",
}
SECAO_PARA_YAMAHA = {v: k for k, v in YAMAHA_PARA_SECAO.items()}

_LETRAS = {"a": "A", "b": "B", "c": "C", "d": "D", "1": "A", "2": "B", "3": "C", "4": "D"}


def normalizar_secao(marcador: str) -> str | None:
    """Nome de marcador (Yamaha ou Korg) -> nome da nossa seção. Ex.: 'Main B' e 'Variation 2' -> 'Var B'."""
    if marcador in YAMAHA_PARA_SECAO:
        return YAMAHA_PARA_SECAO[marcador]
    m = marcador.strip().lower().replace("_", " ").replace("-", " ")
    m = " ".join(m.split())
    if m in ("break", "fill in ba", "fill ba"):
        return "Break"
    for prefixos, destino, letras in (
            (("intro ", "intro"), "Intro", "abc123"),
            (("main ", "variation ", "var ", "var", "variation"), "Var", "abcd1234"),
            (("fill in ", "fill ", "fill"), "Fill", "abcd1234"),
            (("ending ", "ending", "end ", "final "), "Final", "abc123")):
        for p in prefixos:
            if m.startswith(p):
                resto = m[len(p):].strip()
                if len(resto) == 2 and resto[0] == resto[1]:          # "aa", "bb" (Fill In AA)
                    resto = resto[0]
                if len(resto) == 1 and resto in letras:
                    return f"{destino} {_LETRAS[resto]}"
    return None

# Código Yamaha de tipo de acorde -> tipo do nosso motor
CODIGO_PARA_TIPO = {
    0x00: "", 0x01: "6", 0x02: "maj7", 0x03: "maj7", 0x04: "add9", 0x05: "maj7", 0x06: "6", 0x07: "aug",
    0x08: "m", 0x09: "m6", 0x0A: "m7", 0x0B: "m7b5", 0x0C: "m", 0x0D: "m9", 0x0E: "m7", 0x0F: "mmaj7",
    0x10: "mmaj7", 0x11: "dim", 0x12: "dim7", 0x13: "7", 0x14: "7sus4", 0x15: "7", 0x16: "9", 0x17: "7",
    0x18: "7", 0x19: "7", 0x1A: "7", 0x1B: "7", 0x1C: "maj7", 0x1D: "7", 0x1E: "", 0x1F: "", 0x20: "sus4",
    0x21: "sus2",
}
# Nosso tipo -> código Yamaha que o representa (para mute e para exportar)
TIPO_PARA_CODIGO = {"": 0x00, "6": 0x01, "maj7": 0x02, "add9": 0x04, "aug": 0x07, "m": 0x08, "m6": 0x09,
                    "m7": 0x0A, "m7b5": 0x0B, "m9": 0x0D, "mmaj7": 0x0F, "dim": 0x11, "dim7": 0x12, "7": 0x13,
                    "7sus4": 0x14, "9": 0x16, "sus4": 0x20, "sus2": 0x21}


class ErroEstilo(ValueError):
    pass


# ====================================================================== leitura de baixo nível
def _blocos(dados: bytes) -> list[tuple[bytes, bytes]]:
    blocos, i = [], 0
    while i + 8 <= len(dados):
        tipo, tam = dados[i:i + 4], struct.unpack(">I", dados[i + 4:i + 8])[0]
        blocos.append((tipo, dados[i + 8:i + 8 + tam]))
        i += 8 + tam
    return blocos


def _varlen(d: bytes, i: int) -> tuple[int, int]:
    v = 0
    for _ in range(4):
        if i >= len(d):
            break
        b = d[i]; i += 1
        v = (v << 7) | (b & 0x7F)
        if not b & 0x80:
            break
    return v, i


def ler_trilha(d: bytes) -> list[tuple]:
    """Eventos da trilha: (tick, tipo, canal, a, b). tipo: on/off/pc/cc/marcador/tempo/compasso/nome/fim."""
    ev, i, t, status = [], 0, 0, 0
    while i < len(d):
        delta, i = _varlen(d, i)
        t += delta
        if i >= len(d):
            break
        b = d[i]
        if b & 0x80:
            status = b; i += 1
        if status == 0xFF:
            tipo_meta = d[i]; i += 1
            tam, i = _varlen(d, i)
            corpo = d[i:i + tam]; i += tam
            status = 0
            if tipo_meta == 0x06:
                ev.append((t, "marcador", 0, corpo.decode("latin-1").strip(), 0))
            elif tipo_meta == 0x51 and tam == 3:
                ev.append((t, "tempo", 0, (corpo[0] << 16) | (corpo[1] << 8) | corpo[2], 0))
            elif tipo_meta == 0x58 and tam >= 2:
                ev.append((t, "compasso", 0, corpo[0], 2 ** corpo[1]))
            elif tipo_meta == 0x03:
                ev.append((t, "nome", 0, corpo.decode("latin-1").strip(), 0))
            elif tipo_meta == 0x2F:
                ev.append((t, "fim", 0, 0, 0))
                break
        elif status in (0xF0, 0xF7):
            tam, i = _varlen(d, i)
            i += tam
            status = 0
        else:
            alto, canal = status & 0xF0, status & 0x0F
            if alto in (0xC0, 0xD0):
                a = d[i]; i += 1
                if alto == 0xC0:
                    ev.append((t, "pc", canal, a, 0))
            elif alto in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
                a, b2 = d[i], d[i + 1]; i += 2
                if alto == 0x90 and b2 > 0:
                    ev.append((t, "on", canal, a, b2))
                elif alto in (0x80, 0x90):
                    ev.append((t, "off", canal, a, 0))
                elif alto == 0xB0:
                    ev.append((t, "cc", canal, a, b2))
            else:
                raise ErroEstilo(f"MIDI inválido perto do byte {i}")
    return ev


class Tab:
    """Regras de um canal de origem (Ctab/Ctb2)."""

    def __init__(self):
        self.origem = 0
        self.nome = ""
        self.destino = 0
        self.raizes_tocam = [True] * 12
        self.codigos_mudos: set[int] = set()
        self.fonte_raiz = 0
        self.fonte_codigo = 0x02
        self.zonas: list[tuple] = []       # (nota_min, nota_max, ntr, tabela, baixo_on, tecla_alta, lim_lo, lim_hi)


def _ler_tab(d: bytes, ctb2: bool) -> Tab:
    t = Tab()
    t.origem = d[0] & 0x0F
    t.nome = d[1:9].decode("latin-1").strip()
    t.destino = d[9] & 0x0F
    for r in range(12):
        byte, bit = (d[12], r) if r < 8 else (d[11], r - 8)
        t.raizes_tocam[r] = bool(byte >> bit & 1)
    for c in range(0x22):
        byte, bit = d[17 - c // 8], c % 8
        if not byte >> bit & 1:
            t.codigos_mudos.add(c)
    t.fonte_raiz = d[18] % 12
    t.fonte_codigo = d[19]
    if not ctb2:
        ntr, ntt = d[20], d[21]
        tabela, baixo = {0: (0, False), 1: (1, False), 2: (2, False), 3: (1, True)}.get(ntt, (3, False))
        t.zonas = [(0, 127, ntr, tabela, baixo, d[22] % 12, d[23], d[24])]
    else:
        mid_lo, mid_hi = d[20], d[21]
        faixas = [(0, mid_lo - 1), (mid_lo, mid_hi), (mid_hi + 1, 127)]
        for z, (a, b) in enumerate(faixas):
            if a > b:
                continue
            o = 22 + 6 * z
            ntr, ntt = d[o], d[o + 1]
            t.zonas.append((a, b, ntr, ntt & 0x7F, bool(ntt & 0x80), d[o + 2] % 12, d[o + 3], d[o + 4]))
    return t


def ler_casm(d: bytes) -> list[tuple[list[str], dict]]:
    """Lista de (nomes de seção, {canal_origem: Tab})."""
    segs = []
    for tipo, corpo in _blocos(d):
        if tipo != b"CSEG":
            continue
        nomes, tabs, cntt = [], {}, {}
        for t2, c2 in _blocos(corpo):
            if t2 == b"Sdec":
                nomes = [n.strip() for n in c2.decode("latin-1").split(",")]
            elif t2 in (b"Ctab", b"Ctb2") and len(c2) >= (40 if t2 == b"Ctb2" else 25):
                tab = _ler_tab(c2, t2 == b"Ctb2")
                tabs[tab.origem] = tab
            elif t2 == b"Cntt" and len(c2) >= 2:
                cntt[c2[0] & 0x0F] = c2[1]
        for ch, v in cntt.items():                        # Cntt só refina Ctab (SFF1)
            tab = tabs.get(ch)
            if tab and len(tab.zonas) == 1:
                a, b, ntr, tabela, baixo, hk, lo, hi = tab.zonas[0]
                tab.zonas[0] = (a, b, ntr, v & 0x7F, baixo or bool(v & 0x80), hk, lo, hi)
        segs.append((nomes, tabs))
    return segs


def _regra(ntr: int, tabela: int, baixo: bool, bateria: bool) -> str:
    if bateria:
        return BYPASS
    if ntr == 2:
        return ACORDE                      # NTR Guitar
    if baixo and tabela != 2:
        return FUNDAMENTAL
    if tabela == 0:
        return BYPASS if ntr == 1 else MELODIA
    if tabela == 2:
        return ACORDE
    return MELODIA


# ====================================================================== importar
def ler_sty(origem, nome: str | None = None) -> Ritmo:
    """origem: caminho do arquivo ou bytes."""
    if isinstance(origem, (bytes, bytearray)):
        dados = bytes(origem)
    else:
        with open(origem, "rb") as f:
            dados = f.read()
        if nome is None:
            import os
            nome = os.path.splitext(os.path.basename(origem))[0]
    if dados[:4] != b"MThd":
        from .estilo_korg import identificar
        info = identificar(dados)
        raise ErroEstilo(info["mensagem"])
    blocos = _blocos(dados)
    div = struct.unpack(">HHH", blocos[0][1][:6])[2]
    if div & 0x8000 or div == 0:
        raise ErroEstilo("Divisão de tempo SMPTE não suportada.")
    trilha = next((c for t, c in blocos if t == b"MTrk"), None)
    if trilha is None:
        raise ErroEstilo("Estilo sem trilha MIDI.")
    casm = next((c for t, c in blocos if t == b"CASM"), None)
    segs = ler_casm(casm) if casm else []
    ev = ler_trilha(trilha)

    conv = lambda tick: (tick * PPQ + div // 2) // div
    bpm, num, den, nome_trilha = 120.0, 4, 4, ""
    for t, tipo, _c, a, b in ev:
        if tipo == "tempo" and bpm == 120.0 and a > 0:
            bpm = round(60_000_000 / a, 2)
        elif tipo == "compasso" and (num, den) == (4, 4):
            num, den = a, b
        elif tipo == "nome" and not nome_trilha and t == 0:
            nome_trilha = a
    tc = ticks_do_compasso(num, den)
    fim_trilha = max((t for t, *_ in ev), default=0)

    marcadores = [(t, a) for t, tipo, _c, a, _b in ev if tipo == "marcador"]
    trechos = []                                         # (nome Yamaha, início, fim)
    for k, (t, m) in enumerate(marcadores):
        fim = marcadores[k + 1][0] if k + 1 < len(marcadores) else fim_trilha
        trechos.append((m, t, fim))
    inicio_sint = next((t for t, m, _f in trechos if m == "SInt"), 0)
    fim_sint = next((f for t, m, f in trechos if m == "SInt"), 0)

    # notas: pares on/off (primeiro a entrar, primeiro a sair)
    abertas, notas_brutas = {}, []
    for t, tipo, c, a, b in ev:
        if tipo == "on":
            abertas.setdefault((c, a), []).append(len(notas_brutas))
            notas_brutas.append([t, None, c, a, b])
        elif tipo == "off" and abertas.get((c, a)):
            notas_brutas[abertas[(c, a)].pop(0)][1] = t

    r = Ritmo(nome or nome_trilha or "Estilo Yamaha", bpm, pistas_padrao(), {s: Secao() for s in SECOES}, (num, den))
    padrao = pistas_padrao()

    def tabs_da_secao(nome_y: str) -> dict:
        for nomes, tabs in segs:
            if nome_y in nomes:
                return tabs
        return segs[0][1] if segs else {}

    def tab_ou_padrao(tabs: dict, ch: int):
        if segs:                                         # com CASM: canal sem regra não toca (como no teclado)
            return tabs.get(ch)
        return _tab_padrao(ch, padrao) if 8 <= ch <= 15 else None

    cfg_definida = [False] * 8
    ja_lidas: set[str] = set()
    for nome_y, ini, fim in trechos:
        secao = normalizar_secao(nome_y)
        if not secao or (secao in ja_lidas):
            continue
        ja_lidas.add(secao)
        sec = r.secoes[secao]
        sec.compassos = max(1, (conv(fim) - conv(ini) + tc // 2) // tc)
        tabs = tabs_da_secao(nome_y)
        por_canal = {}
        for on, off, c, n, v in notas_brutas:
            if ini <= on < fim:
                d = (conv(off) if off is not None else conv(fim)) - conv(on)
                por_canal.setdefault(c, []).append(Nota(conv(on) - conv(ini), max(1, d), n, v))
        for ch in sorted(por_canal):
            tab = tab_ou_padrao(tabs, ch)
            if tab is None or not 8 <= tab.destino <= 15:
                continue
            pista = tab.destino - 8
            bateria = tab.destino in (8, 9)
            tipos_mudos = [tp for tp, cod in TIPO_PARA_CODIGO.items() if cod in tab.codigos_mudos]
            raizes_mudas = [x for x in range(12) if not tab.raizes_tocam[x]]
            for (a, b, ntr, tabela, baixo, hk, lo, hi) in tab.zonas:
                notas = [n for n in por_canal[ch] if a <= n.nota <= b]
                if not notas:
                    continue
                faixa = (lo, hi) if lo < hi else (0, 127)
                cam = Camada(pista, notas, _regra(ntr, tabela, baixo, bateria), faixa,
                             (tab.fonte_raiz, CODIGO_PARA_TIPO.get(tab.fonte_codigo, "maj7")), hk,
                             tipos_mudos, raizes_mudas, tab.nome)
                sec.camadas.append(cam)
                if not cfg_definida[pista] or secao == "Var A":
                    cfg = r.pistas[pista]
                    cfg.regra, cfg.faixa = cam.regra, faixa
                    if tab.nome:
                        cfg.nome = f"{padrao[pista].nome.split(' (')[0]} ({tab.nome})"
                    cfg_definida[pista] = True

    # Camadas "simples" (sem filtro e com as regras da pista) viram notas normais, editáveis
    for sec in r.secoes.values():
        resto = []
        for cam in sec.camadas:
            cfg = r.pistas[cam.pista]
            simples = (not cam.tipos_mudos and not cam.raizes_mudas and tuple(cam.fonte) == (0, "maj7")
                       and cam.tecla_alta == TECLA_ALTA_PADRAO and cam.regra == cfg.regra
                       and tuple(cam.faixa) == tuple(cfg.faixa))
            if simples:
                sec.pistas[cam.pista] = sorted(sec.pistas.get(cam.pista, []) + cam.notas, key=lambda n: (n.ini, n.nota))
            else:
                resto.append(cam)
        sec.camadas = resto

    # Timbres e volumes da seção SInt
    tabs0 = segs[0][1] if segs else {}
    for t, tipo, c, a, b in ev:
        if not (inicio_sint <= t < max(fim_sint, inicio_sint + 1)) or tipo not in ("pc", "cc"):
            continue
        tab = tabs0.get(c)
        dest = tab.destino if tab else c
        if not 8 <= dest <= 15:
            continue
        if tipo == "pc":
            r.pistas[dest - 8].programa = a
        elif a == 7:
            r.pistas[dest - 8].volume = round(b / 127, 4)
    if all(s.vazia for s in r.secoes.values()):
        raise ErroEstilo("Nenhuma seção reconhecida no arquivo (marcadores Intro/Main/Variation/Fill/Ending).")
    return r


def _tab_padrao(ch: int, padrao) -> Tab:
    t = Tab()
    t.origem = t.destino = ch
    cfg = padrao[ch - 8]
    tabela, baixo, ntr = {BYPASS: (0, False, 1), FUNDAMENTAL: (1, True, 0), ACORDE: (2, False, 1),
                          MELODIA: (1, False, 0)}[cfg.regra]
    t.zonas = [(0, 127, ntr, tabela, baixo, TECLA_ALTA_PADRAO, int(cfg.faixa[0]), int(cfg.faixa[1]))]
    return t


# ====================================================================== exportar (SFF1)
def _vl(v: int) -> bytes:
    out = [v & 0x7F]
    v >>= 7
    while v:
        out.insert(0, (v & 0x7F) | 0x80)
        v >>= 7
    return bytes(out)


def _bloco(tipo: bytes, corpo: bytes) -> bytes:
    return tipo + struct.pack(">I", len(corpo)) + corpo


def _meta(tipo: int, corpo: bytes) -> bytes:
    return bytes([0xFF, tipo]) + _vl(len(corpo)) + corpo


def _ntr_ntt(regra: str, bateria: bool) -> tuple[int, int]:
    if bateria:
        return 0, 0
    return {BYPASS: (1, 0), FUNDAMENTAL: (0, 3), ACORDE: (1, 2), MELODIA: (0, 1)}[regra]


def _ctab(origem: int, destino: int, nome: str, regra: str, faixa, fonte, tecla_alta: int,
          tipos_mudos, raizes_mudas) -> bytes:
    nome8 = (nome.encode("latin-1", "replace")[:8]).ljust(8, b" ")
    tocam = [r not in raizes_mudas for r in range(12)]
    b11 = sum(1 << (r - 8) for r in range(8, 12) if tocam[r])
    b12 = sum(1 << r for r in range(8) if tocam[r])
    mudos = {TIPO_PARA_CODIGO[t] for t in tipos_mudos if t in TIPO_PARA_CODIGO}
    cm = [0, 0, 0, 0, 0]                             # bytes 13..17
    for c in range(0x22):
        if c not in mudos:
            cm[4 - c // 8] |= 1 << (c % 8)
    cm[0] |= 0x04                                    # autostart habilitado
    ntr, ntt = _ntr_ntt(regra, destino in (8, 9))
    lo, hi = int(faixa[0]), int(faixa[1])
    return bytes([origem]) + nome8 + bytes([destino, 0, b11, b12] + cm +
                                          [int(fonte[0]) % 12, TIPO_PARA_CODIGO.get(fonte[1], 0x02), ntr, ntt,
                                           tecla_alta % 12, lo, hi, 3, 0])


def escrever_sty(ritmo: Ritmo, caminho: str) -> None:
    """Grava o ritmo como estilo Yamaha SFF1 (canais 9–16, CASM com as regras de cada pista)."""
    tc = ritmo.ticks_compasso
    ev = []                                          # (tick, ordem, bytes)
    num, den = ritmo.compasso
    us = int(round(60_000_000 / ritmo.bpm))
    ev.append((0, 0, _meta(0x03, ritmo.nome.encode("latin-1", "replace"))))
    ev.append((0, 0, _meta(0x58, bytes([num, den.bit_length() - 1, 24, 8]))))
    ev.append((0, 0, _meta(0x51, us.to_bytes(3, "big"))))
    ev.append((0, 0, _meta(0x06, b"SFF1")))
    ev.append((0, 0, _meta(0x06, b"SInt")))
    for i, p in enumerate(ritmo.pistas):
        ch = 8 + i
        if p.programa is not None:
            ev.append((0, 1, bytes([0xC0 | ch, p.programa & 0x7F])))
        ev.append((0, 1, bytes([0xB0 | ch, 7, int(round(p.volume * 127)) & 0x7F])))
    t = tc
    csegs = []
    for secao in SECOES:
        sec = ritmo.secoes[secao]
        if sec.vazia:
            continue
        nome_y = SECAO_PARA_YAMAHA[secao]
        ev.append((t, 0, _meta(0x06, nome_y.encode())))
        tabs = []
        for i, notas in sorted(sec.pistas.items()):
            if not notas:
                continue
            p = ritmo.pistas[i]
            tabs.append(_ctab(8 + i, 8 + i, p.nome.split(" (")[-1].rstrip(")")[:8], p.regra, p.faixa,
                              (0, "maj7"), TECLA_ALTA_PADRAO, [], []))
            for n in notas:
                ev.append((t + n.ini, 3, bytes([0x90 | (8 + i), n.nota, max(1, n.vel)])))
                ev.append((t + n.ini + n.dur, 2, bytes([0x80 | (8 + i), n.nota, 0])))
        if len(sec.camadas) > 8:
            raise ErroEstilo(f"'{secao}' tem mais de 8 camadas — o formato Yamaha não comporta.")
        for k, cam in enumerate(sec.camadas):
            tabs.append(_ctab(k, 8 + cam.pista, cam.nome or f"Cam{k}", cam.regra, cam.faixa, cam.fonte,
                              cam.tecla_alta, cam.tipos_mudos, cam.raizes_mudas))
            for n in cam.notas:
                ev.append((t + n.ini, 3, bytes([0x90 | k, n.nota, max(1, n.vel)])))
                ev.append((t + n.ini + n.dur, 2, bytes([0x80 | k, n.nota, 0])))
        csegs.append(_bloco(b"CSEG", _bloco(b"Sdec", nome_y.encode()) + b"".join(_bloco(b"Ctab", x) for x in tabs)))
        t += sec.ticks
    ev.append((t, 9, _meta(0x2F, b"")))
    ev.sort(key=lambda e: (e[0], e[1]))
    trilha, agora = bytearray(), 0
    for tick, _o, b in ev:
        trilha += _vl(tick - agora) + b
        agora = tick
    dados = (_bloco(b"MThd", struct.pack(">HHH", 0, 1, PPQ)) + _bloco(b"MTrk", bytes(trilha)) +
             _bloco(b"CASM", b"".join(csegs)))
    with open(caminho, "wb") as f:
        f.write(dados)
