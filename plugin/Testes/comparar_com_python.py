"""Compara o motor C++ (TestesNucleo) com o motor Python (EstudioRitmos/nucleo) evento por evento.

Uso: python comparar_com_python.py <pasta EstudioRitmos (Python)> <executável TestesNucleo>
"""
import json
import os
import subprocess
import sys
import tempfile

PY, EXE = sys.argv[1], sys.argv[2]
sys.path.insert(0, PY)
from nucleo import acordes as AC          # noqa: E402
from nucleo.ritmo import Ritmo            # noqa: E402
from nucleo.tocador import Tocador        # noqa: E402
from nucleo.estilo_yamaha import ler_sty, escrever_sty   # noqa: E402
from nucleo.ritmo import Camada, Nota, ritmo_demo        # noqa: E402

C = 1920
CENARIOS = {
    "basico": ("Arrocha Demo.ritmo", [
        (0, "acorde", "C"), (0, "iniciar", ""), (C, "acorde", "Am"), (C + 960, "acorde", "F"),
        (4000, "pedir", "Var B"), (3 * C, "acorde", "G7"), (8000, "pedir", "Break"), (9700, "pedir", "Var D"),
        (9800, "acorde", "Bb7M"), (11000, "acorde", "C/E"), (13000, "pedir", "Final A"), (30000, "fim", "")]),
    "intro_sync_sequencia": ("Arrocha Demo.ritmo", [
        (0, "pedir", "Intro A"), (0, "sync", ""), (500, "acorde", "Dm7"), (600, "sequencia", "C G Am F"),
        (3000, "autofill", "0"), (4100, "pedir", "Var C"), (7000, "pedir", "Fill"), (9000, "pedir", "Var C"),
        (2 * C * 6 - 100, "pedir", "Var B"), (15000, "parar", ""), (16000, "fim", "")]),
    "loop136": ("Loop 136 (do seu loop).ritmo", [
        (0, "acorde", "G"), (0, "iniciar", ""), (C * 2 + 7, "acorde", "Em7"), (C * 3, "acorde", "C/E"),
        (C * 4 + 333, "pedir", "Var B"), (C * 6, "acorde", "D7sus4"), (C * 9 + 1800, "pedir", "Var D"),
        (C * 11, "acorde", "F#m7b5"), (C * 13, "acorde", "B7"), (C * 15, "pedir", "Final B"), (C * 30, "fim", "")]),
    "mudo_e_mapa": ("__mudo__", [
        (0, "acorde", "A"), (0, "iniciar", ""), (C + 1, "acorde", "E7"), (C * 3, "pedir", "Var C"), (C * 8, "fim", "")]),
}


def python(ritmo, cmds):
    t = Tocador(ritmo)
    t._thread_auto = False
    linhas = []
    tipo = {"note_on": "on", "note_off": "off", "control_change": "cc", "program_change": "pc"}

    def saida(m):
        if m.type == "control_change":
            d = (m.control, m.value)
        elif m.type == "program_change":
            d = (m.program, 0)
        else:
            d = (m.note, m.velocity if m.type == "note_on" else 0)
        linhas.append(f"[{t.pos},\"{tipo[m.type]}\",{m.channel},{d[0]},{d[1]}]")
    t.adicionar_saida(saida)
    for tick, cmd, v in cmds:
        t.avancar(tick)
        if cmd == "acorde":
            t.definir_acorde(AC.parse_acorde(v))
        elif cmd == "iniciar":
            t.iniciar(com_thread=False)
        elif cmd == "parar":
            t.parar()
        elif cmd == "pedir":
            t.pedir(v)
        elif cmd == "sync":
            t.armar_sync(True)
        elif cmd == "autofill":
            t.auto_fill = v == "1"
        elif cmd == "sequencia":
            t.definir_sequencia([AC.parse_acorde(a) for a in v.split()])
        linhas.append(f"# {cmd} {v} -> {t.secao if t.tocando else 'parado'}")
    return linhas


def cpp(caminho_ritmo, cmds):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump([{"tick": a, "cmd": b, "v": c} for a, b, c in cmds], f)
    out = subprocess.run([EXE, "cenario", caminho_ritmo, f.name], capture_output=True, text=True, check=True).stdout
    return out.strip().splitlines()


TMPD = tempfile.mkdtemp()


def criar_valsa():
    """Ritmo 3/4 com camadas maior/menor, fonte Cm7, High Key e raízes mudas, gravado como .sty."""
    r = ritmo_demo("Valsa", 96)
    r.definir_compasso(3, 4)
    tc = 1440
    for s in r.secoes.values():
        for i in list(s.pistas):
            s.pistas[i] = [Nota(n.ini // 1920 * tc + n.ini % 1920, min(n.dur, tc), n.nota, n.vel)
                           for n in s.pistas[i] if n.ini % 1920 < tc]
    for nome in ("Var A", "Var C"):
        var = r.secoes[nome]
        var.pistas[2] = []
        var.camadas = [
            Camada(2, [Nota(0, 480, 36, 110), Nota(480, 480, 43, 90), Nota(960, 480, 40, 90)], AC.FUNDAMENTAL,
                   (28, 52), (0, "maj7"), 6, ["m", "m7", "m6", "m7b5", "dim", "dim7", "mmaj7", "m9"], [], "BassMaj"),
            Camada(2, [Nota(0, 480, 36, 110), Nota(480, 480, 43, 90), Nota(960, 480, 39, 90)], AC.FUNDAMENTAL,
                   (28, 52), (0, "m7"), 4, ["", "maj7", "6", "7", "add9", "aug", "sus4", "sus2", "7sus4"], [], "BassMin"),
            Camada(5, [Nota(0, tc - 10, n, 70) for n in (60, 63, 67, 70)], AC.ACORDE, (50, 79), (0, "m7"), 6,
                   [], [1, 6], "PadM7"),
            Camada(6, [Nota(240 * k, 200, n, 90) for k, n in enumerate((62, 63, 65, 67, 70, 72))], AC.MELODIA,
                   (60, 88), (2, "m"), 9, ["7"], [], "Frase"),
        ]
    c = os.path.join(TMPD, "Valsa.sty")
    escrever_sty(r, c)
    return c


def criar_korg_midi():
    import mido
    mid = mido.MidiFile(type=0, ticks_per_beat=96)
    t = mido.MidiTrack(); mid.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(110), time=0))
    for nome, base in (("Intro 1", 35), ("Variation 1", 36), ("Variation 2", 38), ("Fill 1", 40), ("Ending 1", 41)):
        t.append(mido.MetaMessage("marker", text=nome, time=0))
        for k in range(8):
            t.append(mido.Message("note_on", channel=9, note=base, velocity=100, time=0))
            t.append(mido.Message("note_on", channel=10, note=36 + k % 3 * 2, velocity=90, time=0))
            t.append(mido.Message("note_on", channel=11, note=60 + k % 4, velocity=80, time=0))
            t.append(mido.Message("note_off", channel=9, note=base, time=24))
            t.append(mido.Message("note_off", channel=10, note=36 + k % 3 * 2, time=0))
            t.append(mido.Message("note_off", channel=11, note=60 + k % 4, time=24))
    t.append(mido.MetaMessage("end_of_track", time=0))
    c = os.path.join(TMPD, "KorgMidi.STY")
    mid.save(c)
    return c


DADOS = os.path.join(PY, "testes", "dados")
SEQ = [(C, "acorde", "Am"), (2 * C, "acorde", "G7"), (2 * C + 960, "acorde", "Dm7"), (3 * C, "pedir", "Var B"),
       (4 * C, "acorde", "C9"), (5 * C, "acorde", "Bbmaj7"), (6 * C + 500, "pedir", "Var C"), (7 * C, "acorde", "F#m7b5"),
       (8 * C, "acorde", "E7"), (9 * C, "pedir", "Fill"), (10 * C, "acorde", "C/E"), (11 * C, "pedir", "Var D"),
       (12 * C, "acorde", "Cm7"), (13 * C, "acorde", "Ab"), (14 * C, "pedir", "Break"), (15 * C, "pedir", "Final A"),
       (30 * C, "fim", "")]
sys.path.insert(0, os.path.join(PY, "testes"))
import gerar_estilo_sff2   # noqa: E402
CENARIOS["estilo_yamaha_sff2"] = (gerar_estilo_sff2.gerar(os.path.join(TMPD, "TesteSFF2.sty")),
                                  [(0, "acorde", "C"), (0, "iniciar", "")] + SEQ)
EXTRA = os.environ.get("ESTILO_EXTRA")         # um .sty real, para conferência local
if EXTRA and os.path.exists(EXTRA):
    CENARIOS["estilo_extra"] = (EXTRA, [(0, "acorde", "C"), (0, "iniciar", "")] + SEQ)
T = 1440
CENARIOS["valsa_3_4_camadas"] = ("__valsa__", [
    (0, "acorde", "C"), (0, "iniciar", ""), (T, "acorde", "Am"), (2 * T, "acorde", "F"), (3 * T, "acorde", "Em7"),
    (4 * T, "acorde", "G7"), (5 * T, "acorde", "C#m"), (6 * T, "acorde", "F#7"), (7 * T, "acorde", "B"),
    (7 * T + 700, "acorde", "Bm"), (8 * T, "pedir", "Var C"), (9 * T, "acorde", "D"), (10 * T, "acorde", "Dm7b5"),
    (11 * T, "pedir", "Var B"), (13 * T, "pedir", "Final A"), (30 * T, "fim", "")])
CENARIOS["korg_em_midi"] = ("__korg__", [(0, "pedir", "Intro A"), (0, "acorde", "G"), (0, "iniciar", ""),
                                          (C * 3, "acorde", "Em"), (C * 4, "pedir", "Var B"), (C * 6, "acorde", "D7"),
                                          (C * 7, "pedir", "Final A"), (C * 20, "fim", "")])

falhas = 0
for nome, (arq, cmds) in CENARIOS.items():
    if arq == "__mudo__":
        r = Ritmo.abrir(os.path.join(PY, "exemplos", "Arrocha Demo.ritmo"))
        r.pistas[3].mudo = True
        r.pistas[1].mapa = {"36": 24, "42": 30}
        caminho = os.path.join(tempfile.gettempdir(), "mudo.ritmo")
        r.salvar(caminho)
    elif arq in ("__valsa__", "__korg__"):
        caminho = criar_valsa() if arq == "__valsa__" else criar_korg_midi()
        r = ler_sty(caminho)
    elif arq.lower().endswith((".sty", ".prs", ".sst")):
        caminho = arq
        r = ler_sty(caminho)
    else:
        caminho = os.path.join(PY, "exemplos", arq)
        r = Ritmo.abrir(caminho)
    a, b = python(r, cmds), cpp(caminho, cmds)
    notas = sum(1 for x in a if '"on"' in x)
    if a == b:
        print(f"OK     {nome}: {len(a)} linhas idênticas ({notas} notas)")
    else:
        falhas += 1
        k = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        print(f"FALHA  {nome}: diverge na linha {k} (python {len(a)} x c++ {len(b)})")
        for i in range(max(0, k - 3), k + 4):
            print(f"   {i:5d} py: {a[i] if i < len(a) else '-':40s} c++: {b[i] if i < len(b) else '-'}")

# reconhecimento e transposição
saida_cpp = subprocess.run([EXE, "acordes"], capture_output=True, text=True, check=True).stdout.splitlines()
casos = [(60, 64, 67), (57, 60, 64), (55, 59, 62, 65), (62, 65, 69, 72), (60, 64, 67, 71), (59, 62, 65), (60, 64, 68),
         (62, 67, 69), (64, 67, 72), (67, 72, 76), (59, 62, 65, 68), (57, 60, 63, 67), (48, 55), (52, 55, 59, 62),
         (53, 57, 60, 62), (50, 53, 57, 60), (45, 48, 52, 55), (43, 47, 50, 53, 57), (41, 45, 48, 52)]
esperado = []
for c in casos:
    a = AC.reconhecer(list(c))
    esperado.append("R " + " ".join(map(str, c)) + " = " + (a.nome if a else "?"))
for raiz in AC.NOMES:
    for tipo in ["", "m", "7", "m7", "maj7", "6", "m6", "dim", "dim7", "m7b5", "aug", "sus4", "sus2", "7sus4", "9",
                 "add9", "m9", "mmaj7"]:
        ac = AC.parse_acorde(raiz + tipo)
        nums = []
        for regra, lo, hi in ((AC.FUNDAMENTAL, 28, 52), (AC.ACORDE, 52, 76), (AC.MELODIA, 60, 88)):
            nums += [AC.transpor_nota(n, regra, (lo, hi), ac) for n in range(lo, hi + 1)]
        esperado.append("T " + ac.nome + "".join(f" {x}" for x in nums))
for raiz in AC.NOMES:
    for tipo in ["", "m", "7", "m7", "maj7", "dim", "sus4", "9", "m7b5"]:
        ac = AC.parse_acorde(raiz + tipo)
        nums = []
        for fonte, hk in (("Cm7", 4), ("Dm", 9), ("G7", 2), ("Csus4", 6), ("C", 11)):
            for regra, lo, hi in ((AC.FUNDAMENTAL, 28, 52), (AC.ACORDE, 50, 79), (AC.MELODIA, 60, 88)):
                nums += [AC.transpor_nota(n, regra, (lo, hi), ac, AC.parse_acorde(fonte), hk) for n in range(lo, hi + 1)]
        esperado.append("F " + ac.nome + "".join(f" {x}" for x in nums))
esperado.append(f"T C/E {AC.transpor_nota(36, AC.FUNDAMENTAL, (28, 52), AC.parse_acorde('C/E'))}")
dif = [(x, y) for x, y in zip(esperado, saida_cpp) if x != y]
if dif or len(esperado) != len(saida_cpp):
    falhas += 1
    print(f"FALHA  acordes: {len(dif)} linhas diferentes")
    for x, y in dif[:5]:
        print("   py :", x[:120]); print("   c++:", y[:120])
else:
    print(f"OK     acordes: {len(casos)} reconhecimentos + {12 * 18} acordes × 3 regras + {12 * 9} acordes × 5 fontes/High Key, todas as notas idênticos")

print("\nTUDO IGUAL" if not falhas else f"\n{falhas} DIFERENÇA(S)")
sys.exit(1 if falhas else 0)
