"""Confere o MIDI que o .vst3 gerou no HostDeTeste contra o motor Python (mesmo cenário).

Uso: python verificar_host.py <pasta EstudioRitmos (Python)> <saida_cubase.jsonl> [bloco]
"""
import json
import math
import sys

sys.path.insert(0, sys.argv[1])
from nucleo import acordes as AC                 # noqa: E402
from nucleo.ritmo import Ritmo                   # noqa: E402
from nucleo.tocador import Tocador               # noqa: E402

BLOCO = int(sys.argv[3]) if len(sys.argv) > 3 else 512
ESTILO = sys.argv[4] if len(sys.argv) > 4 else None
SR, BPM, PPQ, C = 48000.0, 136.0, 480, 1920
TPS = BPM / 60 * PPQ / SR
amostra = lambda tick: math.floor(tick / TPS)

plug = [json.loads(l) for l in open(sys.argv[2])]
mao_direita = [e for e in plug if e[2] == 0]
plug = [e for e in plug if e[2] != 0]

if ESTILO:
    from nucleo.estilo_yamaha import ler_sty   # noqa: E402
    r = ler_sty(ESTILO)
else:
    r = Ritmo.abrir(sys.argv[1] + "/exemplos/Arrocha Demo.ritmo")
t = Tocador(r)
t._thread_auto = False
esp = []
nomes = {"note_on": "on", "note_off": "off", "control_change": "cc", "program_change": "pc"}


def sai(m):
    d = (m.control, m.value) if m.type == "control_change" else (m.program, 0) if m.type == "program_change" \
        else (m.note, m.velocity if m.type == "note_on" else 0)
    esp.append((t.pos, nomes[m.type], m.channel, d[0], d[1]))


t.adicionar_saida(sai)
parar_host = amostra(10 * C) + 77
bloco_parada = math.ceil(parar_host / BLOCO) * BLOCO
t.iniciar(com_thread=False)
for tick, cmd, v in [(0, "acorde", "C"), (C, "acorde", "Am"), (4000, "pedir", "Var B"), (3 * C, "acorde", "G7"),
                     (6 * C, "acorde", "C")]:   # E2 G2 C3 em modo Fingered = C
    t.avancar(math.ceil(amostra(tick) * TPS))
    t.definir_acorde(AC.parse_acorde(v)) if cmd == "acorde" else t.pedir(v)
t.avancar(math.ceil(bloco_parada * TPS))
t.parar()

print(f"eventos: plugin {len(plug)}  python {len(esp)}")
ok = len(plug) == len(esp)
pior = 0.0
for i, (p, e) in enumerate(zip(plug, esp)):
    if (p[1], p[2], p[3], p[4]) != e[1:]:
        print(f"DIFERENTE #{i}: plugin {p}  python {e}")
        ok = False
        break
    erro = abs(p[0] - e[0] / TPS)
    pior = max(pior, erro)
print(f"pior diferença de tempo: {pior:.1f} amostras ({pior / SR * 1000:.2f} ms)")
ok = ok and pior <= 1 / TPS + 1
print(f"mão direita repassada: {len(mao_direita)} evento(s) no canal 1 {mao_direita}")
ok = ok and len(mao_direita) == 2
print("OK — o plugin toca exatamente como o motor testado" if ok else "FALHA")
sys.exit(0 if ok else 1)
