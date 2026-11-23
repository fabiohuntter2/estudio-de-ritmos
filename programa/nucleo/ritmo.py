"""Modelo de dados do ritmo: 8 pistas × seções, salvar/abrir (.ritmo = JSON), importar MIDI."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict

import mido

from .acordes import BYPASS, FUNDAMENTAL, ACORDE, MELODIA, Acorde, TECLA_ALTA_PADRAO

PPQ = 480
SEMI = PPQ // 4          # semicolcheia
COL = PPQ // 2           # colcheia
TEMPO = PPQ              # semínima
COMPASSO = PPQ * 4       # 4/4 (padrão; o ritmo pode ter outro compasso)


def ticks_do_compasso(num: int, den: int) -> int:
    """3/4 -> 1440, 4/4 -> 1920, 6/8 -> 1440, 2/4 -> 960."""
    return num * PPQ * 4 // den

SECOES = ["Intro A", "Intro B", "Intro C",
          "Var A", "Var B", "Var C", "Var D",
          "Fill A", "Fill B", "Fill C", "Fill D",
          "Break",
          "Final A", "Final B", "Final C"]

SONS_INTERNOS = ["bateria", "baixo", "violao", "piano", "pad", "sanfona", "metais", "orgao"]

# Peças de bateria/percussão (General MIDI) — linhas do editor de bateria
PECAS_BATERIA = [
    (49, "Prato ataque"), (51, "Prato condução"), (46, "Chimbal aberto"), (42, "Chimbal fechado"),
    (44, "Chimbal pedal"), (50, "Tom agudo"), (47, "Tom médio"), (45, "Tom grave"),
    (39, "Palmas"), (37, "Aro"), (38, "Caixa"), (36, "Bumbo"),
    (54, "Pandeiro"), (70, "Shaker"), (81, "Triângulo aberto"), (80, "Triângulo fechado"),
    (56, "Agogô/cowbell"), (63, "Conga aguda"), (64, "Conga grave"), (60, "Bongô agudo"), (61, "Bongô grave"),
]
NOME_PECA = dict(PECAS_BATERIA)


@dataclass
class Nota:
    ini: int        # em ticks (PPQ 480), a partir do início da seção
    dur: int
    nota: int
    vel: int


@dataclass
class ConfigPista:
    nome: str
    canal: int                      # 0..15
    regra: str
    faixa: tuple = (0, 127)
    som_interno: str = "piano"
    programa: int | None = None     # General MIDI, para saída MIDI
    vst: str | None = None          # caminho do plugin VST3/AU
    vst_estado: str | None = None   # estado salvo do plugin (base64)
    volume: float = 0.8
    mudo: bool = False
    mapa: dict = field(default_factory=dict)   # só bateria: nota GM -> nota da biblioteca

    def nota_saida(self, n: int) -> int:
        return int(self.mapa.get(str(n), self.mapa.get(n, n)))


@dataclass
class Camada:
    """Notas extras de uma pista com regras próprias e filtro por acorde.
    Vem dos estilos Yamaha: ex. uma parte para acordes maiores e outra para menores no mesmo canal."""
    pista: int
    notas: list
    regra: str
    faixa: tuple = (0, 127)
    fonte: tuple = (0, "maj7")          # acorde em que as notas foram gravadas (raiz, tipo)
    tecla_alta: int = TECLA_ALTA_PADRAO
    tipos_mudos: list = field(default_factory=list)    # tipos de acorde em que esta camada NÃO toca
    raizes_mudas: list = field(default_factory=list)   # fundamentais (0..11) em que NÃO toca
    nome: str = ""

    def acorde_fonte(self) -> Acorde:
        return Acorde(int(self.fonte[0]), self.fonte[1])

    def ativa(self, ac: Acorde) -> bool:
        return ac.tipo not in self.tipos_mudos and ac.fundamental not in self.raizes_mudas

    def para_dict(self) -> dict:
        return {"pista": self.pista, "nome": self.nome, "regra": self.regra, "faixa": list(self.faixa),
                "fonte": list(self.fonte), "tecla_alta": self.tecla_alta,
                "tipos_mudos": list(self.tipos_mudos), "raizes_mudas": list(self.raizes_mudas),
                "notas": [[n.ini, n.dur, n.nota, n.vel] for n in self.notas]}

    @staticmethod
    def de_dict(d: dict) -> "Camada":
        return Camada(int(d["pista"]), [Nota(*n) for n in d.get("notas", [])], d.get("regra", BYPASS),
                      tuple(d.get("faixa", (0, 127))), tuple(d.get("fonte", (0, "maj7"))),
                      int(d.get("tecla_alta", TECLA_ALTA_PADRAO)), list(d.get("tipos_mudos", [])),
                      list(d.get("raizes_mudas", [])), d.get("nome", ""))


@dataclass
class Secao:
    compassos: int = 1
    pistas: dict = field(default_factory=dict)   # índice da pista (0..7) -> list[Nota]
    camadas: list = field(default_factory=list)  # list[Camada]
    tc: int = COMPASSO                           # ticks por compasso (definido pelo Ritmo)

    def notas(self, pista: int) -> list[Nota]:
        return self.pistas.setdefault(pista, [])

    def camadas_da_pista(self, pista: int) -> list:
        return [c for c in self.camadas if c.pista == pista]

    def camada_toca(self, cam: Camada, ac: Acorde) -> bool:
        """A camada toca neste acorde?
        - fundamental silenciada (Note Mute): nunca toca;
        - tipo de acorde silenciado (Chord Mute): não toca, a não ser que nenhuma camada da pista cubra
          esse tipo — aí toca a primeira da mesma família (maior/menor), para nada ficar mudo nem dobrado."""
        if ac.fundamental in cam.raizes_mudas:
            return False
        if ac.tipo not in cam.tipos_mudos:
            return True
        irmas = [c for c in self.camadas if c.pista == cam.pista and ac.fundamental not in c.raizes_mudas]
        if any(ac.tipo not in c.tipos_mudos for c in irmas):
            return False
        menor = ac.terca() == 3
        mesma = [c for c in irmas if (c.acorde_fonte().terca() == 3) == menor]
        return (mesma or irmas)[0] is cam

    @property
    def vazia(self) -> bool:
        return not any(self.pistas.values()) and not any(c.notas for c in self.camadas)

    @property
    def ticks(self) -> int:
        return self.compassos * self.tc

    def estender(self, novos: int, exceto: int | None = None) -> None:
        """Aumenta a seção para `novos` compassos repetindo o conteúdo atual de cada pista."""
        antigo = self.compassos
        if novos <= antigo:
            self.compassos = max(1, novos)
            return
        tc = self.tc

        def repetir(notas):
            base = [n for n in notas if n.ini < antigo * tc]
            extra = []
            for k in range(1, (novos + antigo - 1) // antigo):
                for n in base:
                    ini = n.ini + k * antigo * tc
                    if ini < novos * tc:
                        extra.append(Nota(ini, n.dur, n.nota, n.vel))
            return sorted(base + extra, key=lambda n: (n.ini, n.nota))

        for i, notas in self.pistas.items():
            if i != exceto and notas:
                self.pistas[i] = repetir(notas)
        for c in self.camadas:
            if c.pista != exceto and c.notas:
                c.notas = repetir(c.notas)
        self.compassos = novos


@dataclass
class Ritmo:
    nome: str
    bpm: float
    pistas: list
    secoes: dict
    compasso: tuple = (4, 4)

    def __post_init__(self):
        self.definir_compasso(*self.compasso)

    @property
    def ticks_compasso(self) -> int:
        return ticks_do_compasso(*self.compasso)

    def definir_compasso(self, num: int, den: int) -> None:
        self.compasso = (int(num), int(den))
        for s in self.secoes.values():
            s.tc = self.ticks_compasso

    # --------------------------------------------------------------- arquivo
    def para_dict(self) -> dict:
        secoes = {}
        for nome, s in self.secoes.items():
            d = {"compassos": s.compassos,
                 "pistas": {str(i): [[n.ini, n.dur, n.nota, n.vel] for n in ns] for i, ns in s.pistas.items() if ns}}
            if s.camadas:
                d["camadas"] = [c.para_dict() for c in s.camadas]
            secoes[nome] = d
        return {
            "formato": "estudio-ritmos", "versao": 2,
            "nome": self.nome, "bpm": self.bpm, "compasso": list(self.compasso),
            "pistas": [asdict(p) for p in self.pistas],
            "secoes": secoes,
        }

    @staticmethod
    def de_dict(d: dict) -> "Ritmo":
        pistas = []
        for p in d["pistas"]:
            p = dict(p)
            p["faixa"] = tuple(p.get("faixa", (0, 127)))
            pistas.append(ConfigPista(**p))
        secoes = {}
        for nome in SECOES:
            s = d.get("secoes", {}).get(nome)
            sec = Secao(compassos=s["compassos"] if s else 1)
            if s:
                for i, ns in s["pistas"].items():
                    sec.pistas[int(i)] = [Nota(*n) for n in ns]
                sec.camadas = [Camada.de_dict(c) for c in s.get("camadas", [])]
            secoes[nome] = sec
        return Ritmo(d.get("nome", "Sem nome"), float(d.get("bpm", 120)), pistas, secoes,
                     tuple(d.get("compasso", (4, 4))))

    def salvar(self, caminho: str) -> None:
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(self.para_dict(), f, ensure_ascii=False, indent=1)

    @staticmethod
    def abrir(caminho: str) -> "Ritmo":
        with open(caminho, encoding="utf-8") as f:
            return Ritmo.de_dict(json.load(f))

    def copiar_secao(self, origem: str, destino: str) -> None:
        s = self.secoes[origem]
        self.secoes[destino] = Secao(s.compassos, {i: [Nota(**asdict(n)) for n in ns] for i, ns in s.pistas.items()},
                                     [Camada.de_dict(c.para_dict()) for c in s.camadas], s.tc)


def pistas_padrao() -> list[ConfigPista]:
    return [
        ConfigPista("Rhythm 1 (Percussão)", 8, BYPASS, (0, 127), "bateria"),
        ConfigPista("Rhythm 2 (Bateria)", 9, BYPASS, (0, 127), "bateria"),
        ConfigPista("Bass (Baixo)", 10, FUNDAMENTAL, (28, 52), "baixo", 33),
        ConfigPista("Chord 1 (Violão)", 11, ACORDE, (52, 76), "violao", 25),
        ConfigPista("Chord 2 (Piano)", 12, ACORDE, (55, 84), "piano", 0, volume=0.6),
        ConfigPista("Pad (Cordas)", 13, ACORDE, (48, 79), "pad", 48, volume=0.5),
        ConfigPista("Phrase 1 (Sanfona)", 14, MELODIA, (60, 88), "sanfona", 21, volume=0.7),
        ConfigPista("Phrase 2 (Metais)", 15, MELODIA, (55, 84), "metais", 61, volume=0.6),
    ]


def ritmo_vazio(nome="Novo ritmo", bpm=120.0) -> Ritmo:
    return Ritmo(nome, bpm, pistas_padrao(), {s: Secao() for s in SECOES})


# ------------------------------------------------------------------ ritmo de demonstração
def _n(lista, ini, dur, nota, vel):
    lista.append(Nota(int(ini), int(dur), int(nota), int(vel)))


def _bateria_groove(ns, compasso=0, chimbal=True, aberto=False, prato=False):
    b = compasso * COMPASSO
    for t in (0, 8, 12):                                  # bumbo nos tempos 1, 3 e 4
        _n(ns, b + t * SEMI, SEMI, 36, 112)
    _n(ns, b + 4 * SEMI, SEMI, 38, 108)                   # caixa no 2
    _n(ns, b + 14 * SEMI, SEMI, 45, 96)                   # tom no "4 e"
    if chimbal:
        for t in (2, 6, 10):
            _n(ns, b + t * SEMI, SEMI, 46 if (aberto and t == 10) else 42, 92)
        for t in (3, 11):
            _n(ns, b + t * SEMI, SEMI, 42, 66)
    if prato:
        _n(ns, b, TEMPO, 49, 110)


def _percussao(ns, compasso=0):
    b = compasso * COMPASSO
    for i in range(16):
        _n(ns, b + i * SEMI, SEMI // 2, 70, 82 if i % 4 == 2 else 52)
    for t in (4, 12):
        _n(ns, b + t * SEMI, SEMI, 54, 85)


def _baixo(ns, compasso=0, variacao=False):
    b = compasso * COMPASSO
    if variacao:
        seq = [(0, 6, 36, 112), (6, 2, 36, 90), (8, 4, 43, 105), (12, 2, 40, 100), (14, 2, 43, 95)]
    else:
        seq = [(0, 7, 36, 112), (8, 4, 43, 105), (12, 4, 40, 100)]
    for ini, d, n, v in seq:
        _n(ns, b + ini * SEMI, d * SEMI - 15, n, v)


def _violao(ns, compasso=0):
    b = compasso * COMPASSO
    for t in (2, 6, 10, 14):
        for k, n in enumerate((52, 55, 59, 60)):
            _n(ns, b + t * SEMI + k * 8, COL - 20, n, 84 - k * 3)


def _piano(ns, compasso=0):
    b = compasso * COMPASSO
    for t in (0, 8):
        for n in (64, 67, 71, 72):
            _n(ns, b + t * SEMI, 2 * TEMPO - 20, n, 70)


def _pad(ns, compasso=0):
    b = compasso * COMPASSO
    for n in (60, 64, 67, 71):
        _n(ns, b, COMPASSO - 10, n, 62)


def _sanfona(ns, compasso=0):
    b = compasso * COMPASSO
    for ini, d, n, v in [(9, 1, 67, 88), (10, 1, 69, 90), (11, 1, 71, 92), (12, 2, 72, 100),
                         (14, 2, 76, 104)]:
        _n(ns, b + ini * SEMI, d * SEMI - 10, n, v)


def _metais(ns, compasso=0):
    b = compasso * COMPASSO
    for t in (6, 14):
        for n in (64, 67, 72):
            _n(ns, b + t * SEMI, SEMI, n, 100)


def _virada(ns, compasso=0):
    b = compasso * COMPASSO
    _n(ns, b, SEMI, 36, 112)
    _n(ns, b + 4 * SEMI, SEMI, 38, 105)
    _n(ns, b + 8 * SEMI, SEMI, 36, 110)
    for i, (t, n) in enumerate([(9, 38), (10, 38), (11, 38), (12, 50), (13, 50), (14, 47), (15, 45)]):
        _n(ns, b + t * SEMI, SEMI, n, 85 + i * 5)


def ritmo_demo(nome="Arrocha Demo", bpm=136.0) -> Ritmo:
    r = ritmo_vazio(nome, bpm)
    S = r.secoes
    P1, P2, BA, V, PI, PAD, F1, F2 = range(8)

    # Intro A: 2 compassos — piano e pad, bateria entra no 2º
    S["Intro A"].compassos = 2
    _piano(S["Intro A"].notas(PI), 0); _pad(S["Intro A"].notas(PAD), 0)
    _piano(S["Intro A"].notas(PI), 1); _pad(S["Intro A"].notas(PAD), 1)
    _n(S["Intro A"].notas(BA), 0, COMPASSO - 20, 36, 100)
    _virada(S["Intro A"].notas(P2), 1)
    _sanfona(S["Intro A"].notas(F1), 1)

    # Var A: básico
    _bateria_groove(S["Var A"].notas(P2)); _baixo(S["Var A"].notas(BA)); _violao(S["Var A"].notas(V))
    # Var B: + percussão e piano
    _bateria_groove(S["Var B"].notas(P2)); _percussao(S["Var B"].notas(P1)); _baixo(S["Var B"].notas(BA))
    _violao(S["Var B"].notas(V)); _piano(S["Var B"].notas(PI))
    # Var C: + pad e sanfona, baixo com variação
    _bateria_groove(S["Var C"].notas(P2), aberto=True); _percussao(S["Var C"].notas(P1))
    _baixo(S["Var C"].notas(BA), variacao=True); _violao(S["Var C"].notas(V)); _pad(S["Var C"].notas(PAD))
    _sanfona(S["Var C"].notas(F1))
    # Var D: tudo + metais e prato
    _bateria_groove(S["Var D"].notas(P2), aberto=True, prato=True); _percussao(S["Var D"].notas(P1))
    _baixo(S["Var D"].notas(BA), variacao=True); _violao(S["Var D"].notas(V)); _piano(S["Var D"].notas(PI))
    _pad(S["Var D"].notas(PAD)); _sanfona(S["Var D"].notas(F1)); _metais(S["Var D"].notas(F2))

    # Viradas: 1 compasso
    for letra in "ABCD":
        f = S[f"Fill {letra}"]
        _virada(f.notas(P2))
        _baixo(f.notas(BA))
        for n in (52, 55, 59, 60):
            _n(f.notas(V), 0, TEMPO, n, 90)
        if letra in "CD":
            _pad(f.notas(PAD))
        if letra == "D":
            for n in (64, 67, 72):
                _n(f.notas(F2), 12 * SEMI, SEMI, n, 105)
                _n(f.notas(F2), 14 * SEMI, SEMI, n, 110)

    # Break: golpe no 1 e retomada no "4 e"
    br = S["Break"]
    _n(br.notas(P2), 0, SEMI, 36, 115); _n(br.notas(P2), 0, SEMI, 49, 110)
    _n(br.notas(BA), 0, TEMPO, 36, 110)
    for n in (52, 55, 59, 60):
        _n(br.notas(V), 0, TEMPO, n, 95)
    _n(br.notas(P2), 14 * SEMI, SEMI, 38, 100); _n(br.notas(P2), 15 * SEMI, SEMI, 38, 110)

    # Finais: 2 compassos, último acorde sustentado
    for letra in "ABC":
        fi = S[f"Final {letra}"]
        fi.compassos = 2
        _bateria_groove(fi.notas(P2), 0); _baixo(fi.notas(BA), 0); _violao(fi.notas(V), 0)
        _n(fi.notas(P2), COMPASSO, TEMPO, 36, 120); _n(fi.notas(P2), COMPASSO, 2 * TEMPO, 49, 120)
        _n(fi.notas(BA), COMPASSO, 3 * TEMPO, 36, 115)
        for n in (60, 64, 67, 71):
            _n(fi.notas(PAD), COMPASSO, 3 * TEMPO, n, 80)
        for n in (52, 55, 59, 60):
            _n(fi.notas(V), COMPASSO, 2 * TEMPO, n, 100)
        if letra != "A":
            _sanfona(fi.notas(F1), 0)
    return r


# ------------------------------------------------------------------ importar MIDI
def ler_midi(caminho: str, canal: int | None = None) -> tuple[list[Nota], int]:
    """Lê as notas de um arquivo MIDI (todas as faixas). Devolve (notas, compassos)."""
    mid = mido.MidiFile(caminho)
    escala = PPQ / mid.ticks_per_beat
    notas, abertas = [], {}
    for trk in mid.tracks:
        t = 0
        for m in trk:
            t += m.time
            if m.type not in ("note_on", "note_off"):
                continue
            if canal is not None and m.channel != canal:
                continue
            chave = (m.channel, m.note)
            if m.type == "note_on" and m.velocity > 0:
                abertas.setdefault(chave, []).append((t, m.velocity))
            elif abertas.get(chave):
                ini, vel = abertas[chave].pop(0)
                notas.append(Nota(round(ini * escala), max(1, round((t - ini) * escala)), m.note, vel))
    for (ch, n), lst in abertas.items():               # notas sem note_off
        for ini, vel in lst:
            notas.append(Nota(round(ini * escala), SEMI, n, vel))
    notas.sort(key=lambda n: (n.ini, n.nota))
    fim = max((n.ini + n.dur for n in notas), default=COMPASSO)
    compassos = max(1, math.ceil((fim - SEMI // 2) / COMPASSO))
    return notas, compassos


def notas_da_deteccao(batidas: list[dict], bpm: float) -> tuple[list[Nota], int]:
    """Converte a saída do detector (tempo em segundos) em notas da pista de bateria."""
    from .deteccao import GM
    tick = lambda s: int(round(s * bpm / 60 * PPQ))
    notas = [Nota(tick(b["tempo_s"]), SEMI, GM[b["peca"]], int(b["vel"])) for b in batidas]
    fim = max((n.ini for n in notas), default=0)
    compassos = max(1, math.ceil((fim + SEMI) / COMPASSO))
    # notas que caíram depois do fim (arredondamento) voltam para o início do loop
    total = compassos * COMPASSO
    unicas: dict = {}
    for n in notas:                                    # uma nota por (tempo, peça): a mais forte
        k = (n.ini % total, n.nota)
        if k not in unicas or n.vel > unicas[k].vel:
            unicas[k] = Nota(k[0], n.dur, n.nota, n.vel)
    return sorted(unicas.values(), key=lambda n: (n.ini, n.nota)), compassos
