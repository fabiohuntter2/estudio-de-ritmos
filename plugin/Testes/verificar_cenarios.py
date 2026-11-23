"""Confere notas presas e comportamento nos cenários interno/relocar/semplayhead do HostDeTeste."""
import json, sys
pasta = sys.argv[1]
ok = True
for nome in ["cubase_512", "interno", "relocar", "semplayhead"]:
    ev = [json.loads(l) for l in open(f"{pasta}/host_{nome}.jsonl")]
    abertas = {}
    for s, t, ch, d1, d2 in ev:
        if t == "on":
            abertas[(ch, d1)] = abertas.get((ch, d1), 0) + 1
        elif t == "off" and abertas.get((ch, d1)):
            abertas[(ch, d1)] -= 1
        elif t == "cc" and d1 == 123:
            for k in list(abertas):
                if k[0] == ch:
                    abertas[k] = 0
    presas = {k: v for k, v in abertas.items() if v}
    notas = sum(1 for e in ev if e[1] == "on" and e[2] != 0)
    primeiro = next((e[0] for e in ev if e[1] == "on" and e[2] != 0), None)
    print(f"{nome:12s} notas={notas:4d}  primeira nota na amostra {primeiro}  notas presas={len(presas)}")
    ok &= not presas
    if nome == "interno":                      # Sync Start: começa no acorde (meio compasso = 960 ticks = 42352 amostras a 136 BPM/48 kHz)
        ok &= primeiro is not None and abs(primeiro - 42352) <= 1 and notas > 50
    if nome == "relocar":
        ok &= notas > 100
print("OK" if ok else "FALHA")
sys.exit(0 if ok else 1)
