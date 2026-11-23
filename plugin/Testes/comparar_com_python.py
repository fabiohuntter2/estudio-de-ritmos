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


falhas = 0
for nome, (arq, cmds) in CENARIOS.items():
    if arq == "__mudo__":
        r = Ritmo.abrir(os.path.join(PY, "exemplos", "Arrocha Demo.ritmo"))
        r.pistas[3].mudo = True
        r.pistas[1].mapa = {"36": 24, "42": 30}
        caminho = os.path.join(tempfile.gettempdir(), "mudo.ritmo")
        r.salvar(caminho)
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
esperado.append(f"T C/E {AC.transpor_nota(36, AC.FUNDAMENTAL, (28, 52), AC.parse_acorde('C/E'))}")
dif = [(x, y) for x, y in zip(esperado, saida_cpp) if x != y]
if dif or len(esperado) != len(saida_cpp):
    falhas += 1
    print(f"FALHA  acordes: {len(dif)} linhas diferentes")
    for x, y in dif[:5]:
        print("   py :", x[:120]); print("   c++:", y[:120])
else:
    print(f"OK     acordes: {len(casos)} reconhecimentos + {12 * 18} acordes × 3 regras × todas as notas idênticos")

print("\nTUDO IGUAL" if not falhas else f"\n{falhas} DIFERENÇA(S)")
sys.exit(1 if falhas else 0)
