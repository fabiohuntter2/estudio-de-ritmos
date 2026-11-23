"""Teste da interface: abre o programa, usa cada aba por código e tira fotos (precisa de tela/Xvfb).

Uso: python testes/teste_interface.py [pasta_das_fotos]
"""
import os
import subprocess
import sys
import time
import tkinter as tk

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

import app as A  # noqa: E402

PASTA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(AQUI, "fotos")
os.makedirs(PASTA, exist_ok=True)
erros = []


def foto(root, nome):
    root.update(); time.sleep(0.15); root.update()
    if os.environ.get("DISPLAY"):
        subprocess.run(["import", "-window", "root", os.path.join(PASTA, nome + ".png")], check=False)


def checar(cond, msg):
    print(("OK   " if cond else "FALHA ") + msg)
    if not cond:
        erros.append(msg)


root = tk.Tk()
root.geometry("1280x800+0+0")
app = A.App(root, sem_audio=True)
log = []
app.tocador.adicionar_saida(lambda m: log.append(m))
root.update()

# ---- Aba 1: importar loop
app.abas.select(0)
app._definir_loop(os.path.join(AQUI, "dados", "loop136.wav"))
app._analisar_loop(sincrono=True)
root.update()
checar(app.analise is not None and abs(app.analise["bpm"] - 136.4) < 0.5, "loop analisado (~136,4 BPM)")
checar(len(app.analise_notas) > 40, f"batidas detectadas: {len(app.analise_notas)}")
foto(root, "1_importar_loop")
app.var_dest_sec.set("Var A")
app._enviar_loop()
checar(app.ritmo.bpm == 136 and len(app.ritmo.secoes["Var A"].pistas[1]) == len(app.analise_notas),
       "bateria enviada para Var A / pista 2 e BPM 136")
checar(app.ritmo.secoes["Var A"].compassos == 4, "Var A ficou com 4 compassos (tamanho do loop)")

# ---- Aba 2: programar
app.abas.select(1)
app.lb_secoes.selection_clear(0, "end"); app.lb_secoes.selection_set(A.SECOES.index("Var A")); app._sel_secao()
app.var_pista.set(1); app._sel_pista()
foto(root, "2_programar_bateria")
app.var_pista.set(2); app._sel_pista()
antes = len(app.ritmo.secoes["Var A"].pistas[2])


class Ev:  # clique simulado no editor
    def __init__(self, x, y): self.x, self.y = x, y


ed = app.editor
linha_c2 = next(k for k, (n, _, _) in enumerate(ed.linhas) if n == 36)
ed.cv.xview_moveto(0); ed.cv.yview_moveto(0); root.update()
ed._clique(Ev(ed.ROTULO + 7 * ed.W + 5, 20 + linha_c2 * ed.H + 5))
checar(len(app.ritmo.secoes["Var A"].pistas[2]) == antes + 1, "clique no editor adiciona nota")
ed._clique(Ev(ed.ROTULO + 7 * ed.W + 5, 20 + linha_c2 * ed.H + 5))
checar(len(app.ritmo.secoes["Var A"].pistas[2]) == antes, "segundo clique remove a nota")
app.var_pista.set(4); app._sel_pista()
ed.cv.yview_moveto(0.25)
foto(root, "3_programar_piano")

# ---- Aba 3: instrumentos
app.abas.select(2)
foto(root, "4_instrumentos")
app.linhas_inst[2]["som"].set("orgao"); root.update()
checar(app.ritmo.pistas[2].som_interno == "orgao", "mudar som interno da pista 3")
app.linhas_inst[2]["som"].set("baixo")

# ---- Aba 4: tocar (relógio real, saída capturada)
app.abas.select(3)
app.var_seq.set("C Am F G7"); app.var_seq_on.set(True)
app._play()
t0 = time.time()
while time.time() - t0 < 2.0:
    root.update(); time.sleep(0.01)
app._secao("Var B")
while time.time() - t0 < 3.2:
    root.update(); time.sleep(0.01)
foto(root, "5_tocar")
e = app.tocador.estado()
checar(e["tocando"], "tocador tocando")
checar(any(m.type == "note_on" and m.channel == 9 for m in log), "bateria tocou (canal 10)")
checar(any(m.type == "note_on" and m.channel == 10 for m in log), "baixo tocou (canal 11)")
checar(e["secao"] in ("Fill B", "Var B"), f"pediu Var B -> agora em {e['secao']}")
app._play()
root.update()
checar(not app.tocador.tocando, "parar")

# ---- salvar / abrir
app.alterado = False
caminho = os.path.join(PASTA, "teste.ritmo")
app.caminho = caminho
app.salvar()
r2 = A.Ritmo.abrir(caminho)
checar(r2.para_dict() == app.ritmo.para_dict(), "salvar e abrir .ritmo (idêntico)")

# ---- abrir estilo Yamaha real e um 3/4
app.alterado = False
sys.path.insert(0, AQUI)
import gerar_estilo_sff2  # noqa: E402
app.abrir(gerar_estilo_sff2.gerar(os.path.join(PASTA, "TesteSFF2.sty")))
root.update()
checar(app.ritmo.nome == "TesteSFF2" and app.ritmo.bpm == 100.0, "abrir estilo Yamaha .sty (SFF2)")
app.abas.select(1)
app.lb_secoes.selection_clear(0, "end"); app.lb_secoes.selection_set(A.SECOES.index("Var A")); app._sel_secao()
app.var_pista.set(3); app._sel_pista()
checar(len(app.editor.extras) > 0, "editor mostra as camadas do estilo")
foto(root, "7_estilo_yamaha_camadas")
app.abas.select(3)
log.clear()
app.var_seq.set("C Am Dm7 G7"); app.var_seq_on.set(True)
app._play()
t0 = time.time()
while time.time() - t0 < 2.5:
    root.update(); time.sleep(0.01)
app._play(); root.update()
checar(sum(1 for m in log if m.type == "note_on") > 20, "estilo Yamaha toca no tocador")
app.var_compasso.set("3/4"); app._mudar_compasso(); root.update()
checar(app.ritmo.ticks_compasso == 1440 and app.editor.ppc == 12, "compasso 3/4 na grade")
app.abas.select(1); root.update()
foto(root, "8_grade_3_4")

# ---- janela de exportação
app.janela_exportar(); root.update()
foto(root, "6_exportar")

root.destroy()
print("\n" + ("TUDO OK" if not erros else f"{len(erros)} FALHA(S)"))
sys.exit(1 if erros else 0)
