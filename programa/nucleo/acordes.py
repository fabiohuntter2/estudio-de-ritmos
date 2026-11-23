"""Motor de acordes: reconhecimento do acorde e transposição das pistas (acorde-fonte = CMaj7)."""
from __future__ import annotations

from dataclasses import dataclass

NOMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
ALIASES = {"Db": 1, "Eb": 3, "Gb": 6, "Ab": 8, "Bb": 10, "Cb": 11, "Fb": 4, "E#": 5, "B#": 0}

TIPOS = {
    "":      (0, 4, 7),
    "m":     (0, 3, 7),
    "7":     (0, 4, 7, 10),
    "m7":    (0, 3, 7, 10),
    "maj7":  (0, 4, 7, 11),
    "6":     (0, 4, 7, 9),
    "m6":    (0, 3, 7, 9),
    "dim":   (0, 3, 6),
    "dim7":  (0, 3, 6, 9),
    "m7b5":  (0, 3, 6, 10),
    "aug":   (0, 4, 8),
    "sus4":  (0, 5, 7),
    "sus2":  (0, 2, 7),
    "7sus4": (0, 5, 7, 10),
    "9":     (0, 4, 7, 10, 14),
    "add9":  (0, 4, 7, 14),
    "m9":    (0, 3, 7, 10, 14),
    "mmaj7": (0, 3, 7, 11),
}
# Ordem de preferência no reconhecimento quando dois tipos explicam as mesmas notas
_PREF = ["", "m", "7", "m7", "maj7", "dim", "aug", "sus4", "6", "m6", "dim7", "m7b5",
         "7sus4", "sus2", "add9", "9", "m9", "mmaj7"]

SINONIMOS = {"M7": "maj7", "7M": "maj7", "Maj7": "maj7", "min": "m", "-": "m", "°": "dim",
             "º": "dim", "o": "dim", "+": "aug", "m7(b5)": "m7b5", "ø": "m7b5", "4": "sus4",
             "sus": "sus4", "7/4": "7sus4", "min7": "m7", "-7": "m7", "°7": "dim7", "º7": "dim7"}

BYPASS, FUNDAMENTAL, ACORDE, MELODIA = "bypass", "fundamental", "acorde", "melodia"
REGRAS = [BYPASS, FUNDAMENTAL, ACORDE, MELODIA]
NOMES_REGRAS = {BYPASS: "Não transpõe (bateria)", FUNDAMENTAL: "Fundamental (baixo)",
                ACORDE: "Acorde (vozes)", MELODIA: "Melodia (frases)"}


@dataclass(frozen=True)
class Acorde:
    fundamental: int
    tipo: str = ""
    baixo: int | None = None

    @property
    def intervalos(self):
        return TIPOS[self.tipo]

    @property
    def nome(self) -> str:
        n = NOMES[self.fundamental] + self.tipo
        if self.baixo is not None and self.baixo != self.fundamental:
            n += "/" + NOMES[self.baixo]
        return n

    def terca(self) -> int:
        for i in (4, 3, 5, 2):
            if i in self.intervalos:
                return i
        return 4

    def quinta(self) -> int:
        for i in (7, 6, 8):
            if i in self.intervalos:
                return i
        return 7

    def setima(self) -> int | None:
        for i in (11, 10):
            if i in self.intervalos:
                return i
        if self.tipo in ("dim7", "6", "m6"):
            return 9
        return None


ACORDE_PADRAO = Acorde(0, "")


def _parse_nota(n: str) -> int:
    n = n.strip()
    if n in ALIASES:
        return ALIASES[n]
    if n[:1].upper() + n[1:] in NOMES:
        return NOMES.index(n[:1].upper() + n[1:])
    raise ValueError(f"Nota desconhecida: '{n}'")


def parse_acorde(texto: str) -> Acorde:
    """'Am7' -> Lá menor com sétima; 'C/E' -> Dó com baixo em Mi; 'Bb7M' -> Si bemol com 7ª maior."""
    t = texto.strip()
    if not t:
        raise ValueError("Acorde vazio")
    baixo = None
    if "/" in t[1:]:
        corte = t.index("/", 1)
        resto_baixo = t[corte + 1:]
        if resto_baixo and resto_baixo[0].upper() in "ABCDEFG":
            t, baixo = t[:corte], _parse_nota(resto_baixo)
    t = t[0].upper() + t[1:]
    if len(t) >= 2 and t[1] in "#b":
        raiz, tipo = t[:2], t[2:]
    else:
        raiz, tipo = t[:1], t[1:]
    tipo = SINONIMOS.get(tipo, tipo)
    if tipo not in TIPOS:
        raise ValueError(f"Tipo de acorde desconhecido: '{tipo}' em '{texto}'")
    return Acorde(_parse_nota(raiz), tipo, baixo)


def reconhecer(notas, modo: str = "fingered") -> Acorde | None:
    """Reconhece o acorde das notas tocadas (qualquer inversão).

    modo 'single': 1 tecla = maior; com uma tecla preta à esquerda = menor;
    com uma branca à esquerda = sétima; com preta e branca = menor com sétima.
    """
    notas = sorted(set(notas))
    if not notas:
        return None
    if modo == "single":
        raiz = notas[-1] % 12
        abaixo = [n for n in notas[:-1]]
        pretas = [n for n in abaixo if n % 12 in (1, 3, 6, 8, 10)]
        brancas = [n for n in abaixo if n % 12 not in (1, 3, 6, 8, 10)]
        if pretas and brancas:
            return Acorde(raiz, "m7")
        if pretas:
            return Acorde(raiz, "m")
        if brancas:
            return Acorde(raiz, "7")
        return Acorde(raiz, "")

    pcs = {n % 12 for n in notas}
    nota_baixo = notas[0] % 12
    if len(pcs) == 1:
        return Acorde(nota_baixo, "")
    if len(pcs) == 2:                                   # power chord / quinta: maior sem 3ª
        a, b = sorted(pcs, key=lambda p: (p - nota_baixo) % 12)
        if (b - a) % 12 == 7:
            return Acorde(a, "")
        if (a - b) % 12 == 7:
            return Acorde(b, "", nota_baixo)

    exatos, parciais = [], []
    for raiz in pcs:
        rel = {(p - raiz) % 12 for p in pcs}
        for tipo in _PREF:
            conj = {i % 12 for i in TIPOS[tipo]}
            baixo = nota_baixo if nota_baixo != raiz else None
            ordem = (raiz != nota_baixo, _PREF.index(tipo))
            if rel == conj:
                exatos.append((ordem, Acorde(raiz, tipo, baixo)))
            elif rel <= conj:
                parciais.append(((len(conj - rel),) + ordem, Acorde(raiz, tipo, baixo)))
    if exatos:
        return min(exatos, key=lambda x: x[0])[1]
    if parciais:
        return min(parciais, key=lambda x: x[0])[1]
    return None


FONTE_PADRAO = Acorde(0, "maj7")       # acorde em que as pistas são gravadas (CMaj7)
TECLA_ALTA_PADRAO = 6                  # High Key: acima de F# o padrão desce uma oitava


def _papel(pc_fonte: int, alvo: Acorde, so_notas_do_acorde: bool, fonte: Acorde = FONTE_PADRAO) -> int:
    """pc_fonte é relativo à fundamental do acorde-fonte. Devolve o intervalo no acorde-alvo."""
    t, q, s = alvo.terca(), alvo.quinta(), alvo.setima()
    fs = fonte.setima()
    mapa = {}
    for chave, valor in ((0, 0), (fonte.terca(), t), (fonte.quinta(), q),
                         (fs if fs is not None else 11, s if s is not None else 12)):
        mapa.setdefault(chave, valor)
    if pc_fonte in mapa:
        return mapa[pc_fonte]
    if so_notas_do_acorde:
        cands = [0, t, q] + ([s] if s is not None else [])
        return min(cands, key=lambda c: (abs(c - pc_fonte), c))
    menor = t == 3
    escala = {2: 2, 5: 5, 9: 9 if (9 in alvo.intervalos or not menor) else 8}
    if pc_fonte in escala:
        return escala[pc_fonte]
    ancora = min(mapa, key=lambda a: abs(a - pc_fonte))
    return mapa[ancora] + (pc_fonte - ancora)


def transpor_nota(nota: int, regra: str, faixa: tuple[int, int], alvo: Acorde,
                  fonte: Acorde | None = None, tecla_alta: int = TECLA_ALTA_PADRAO) -> int:
    """Transforma uma nota gravada sobre o acorde `fonte` (padrão CMaj7) na nota do acorde `alvo`."""
    if regra == BYPASS or alvo is None:
        return nota
    fonte = fonte or FONTE_PADRAO
    lo, hi = faixa
    fr = fonte.fundamental
    pc = (nota - fr) % 12
    raiz = alvo.fundamental

    if regra in (FUNDAMENTAL, MELODIA):
        intervalo = _papel(pc, alvo, False, fonte)
        if regra == FUNDAMENTAL and pc == 0 and alvo.baixo is not None:
            intervalo = (alvo.baixo - raiz) % 12
        d = (raiz - fr) % 12
        desloc = d if d <= (tecla_alta - fr) % 12 else d - 12
        nova = nota + desloc + (intervalo - pc)
        while nova > hi and nova - 12 >= 0:
            nova -= 12
        while nova < lo and nova + 12 <= 127:
            nova += 12
        return nova

    if regra == ACORDE:
        pc_alvo = (raiz + _papel(pc, alvo, True, fonte)) % 12
        opcoes = [o * 12 + pc_alvo for o in range(11) if o * 12 + pc_alvo <= 127]
        # faixa "macia": aceita até 4 semitons além do limite para não pular uma oitava inteira
        dentro = [n for n in opcoes if lo - 4 <= n <= hi + 4] or opcoes
        return min(dentro, key=lambda n: (abs(n - nota), n))

    raise ValueError(regra)


def nome_nota(n: int) -> str:
    return f"{NOMES[n % 12]}{n // 12 - 1}"
