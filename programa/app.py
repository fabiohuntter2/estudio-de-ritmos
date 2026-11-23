"""Estúdio de Ritmos — programa de criação de ritmos para teclado arranjador.

Abas:
  1 · Importar loop   — áudio de bateria vira MIDI (pista de bateria)
  2 · Programar       — editar as 8 pistas de cada seção
  3 · Instrumentos    — som interno, VST/Kontakt por pista, regras de transposição
  4 · Tocar           — usar o ritmo ao vivo, como num teclado
"""
from __future__ import annotations

import os
import sys
import threading
import time
import tkinter as tk
import traceback
from tkinter import ttk, filedialog, messagebox, simpledialog

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nucleo import acordes as AC
from nucleo import exportar as EX
from nucleo import midi_io
from nucleo import vst as VST
from nucleo.ritmo import (COMPASSO, PECAS_BATERIA, PPQ, SECOES, SEMI, SONS_INTERNOS, Nota, Ritmo,
                          ler_midi, notas_da_deteccao, ritmo_demo, ritmo_vazio)
from nucleo.sintetizador import Sintetizador
from nucleo.tocador import MaoEsquerda, Tocador

VERSAO = "0.1"
SOM_INTERNO = "Som interno (placa de som)"
COR = {"fundo": "#1e1f24", "painel": "#2a2c33", "grade": "#3a3d46", "grade_forte": "#5a5e6b",
       "nota": "#3d8bfd", "nota_forte": "#7fb2ff", "nota_fraca": "#2a5fb0", "texto": "#e8e8ea",
       "texto2": "#a0a3ad", "acento": "#f0a830", "preta": "#24262c", "branca": "#2f323a",
       "ok": "#4cc38a", "alerta": "#e5534b"}


def tocar_audio(dados, sr):
    try:
        import sounddevice as sd
        sd.stop()
        sd.play(dados, sr)
        return True
    except Exception as e:
        messagebox.showwarning("Áudio", f"Não consegui tocar o áudio:\n{e}")
        return False


def parar_audio():
    try:
        import sounddevice as sd
        sd.stop()
    except Exception:
        pass


# ====================================================================== editor em grade
class EditorGrade(ttk.Frame):
    """Editor de notas: linhas = peças/notas, colunas = semicolcheias.
    Clique: põe/tira nota. Botão direito: muda a força (forte → médio → fraco)."""

    W, H, ROTULO = 22, 18, 128

    def __init__(self, master, on_change=None, somente_leitura=False):
        super().__init__(master)
        self.cv = tk.Canvas(self, bg=COR["fundo"], highlightthickness=0)
        sx = ttk.Scrollbar(self, orient="horizontal", command=self.cv.xview)
        sy = ttk.Scrollbar(self, orient="vertical", command=self.cv.yview)
        self.cv.configure(xscrollcommand=sx.set, yscrollcommand=sy.set)
        self.cv.grid(row=0, column=0, sticky="nsew"); sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1); self.columnconfigure(0, weight=1)
        self.linhas: list[tuple[int, str, bool]] = []
        self.notas: list[Nota] = []
        self.compassos = 1
        self.dur_ticks = SEMI
        self.vel = 100
        self.on_change = on_change
        self.somente_leitura = somente_leitura
        if not somente_leitura:
            self.cv.bind("<Button-1>", self._clique)
            self.cv.bind("<Button-3>", self._clique_dir)
            self.cv.bind("<Button-2>", self._clique_dir)
        self.cv.bind("<MouseWheel>", lambda e: self.cv.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        self.cv.bind("<Button-4>", lambda e: self.cv.yview_scroll(-1, "units"))
        self.cv.bind("<Button-5>", lambda e: self.cv.yview_scroll(1, "units"))

    def carregar(self, linhas, notas, compassos):
        self.linhas, self.notas, self.compassos = linhas, notas, max(1, compassos)
        self.desenhar()
        self.cv.xview_moveto(0)
        # rola até as notas (ou até o Dó central da faixa)
        idx = {n: i for i, (n, _, _) in enumerate(linhas)}
        alvos = [idx[n.nota] for n in notas if n.nota in idx]
        if not alvos:
            alvos = [i for i, (n, _, _) in enumerate(linhas) if n == 60] or [0]
        meio = sum(alvos) / len(alvos)
        total = max(1, len(linhas))
        self.cv.update_idletasks()
        visiveis = max(1, (self.cv.winfo_height() - 20) / self.H)
        self.cv.yview_moveto(max(0.0, (meio - visiveis / 2) / total))

    def desenhar(self):
        cv, W, H, R = self.cv, self.W, self.H, self.ROTULO
        cv.delete("all")
        passos = self.compassos * 16
        largura, altura = R + passos * W, len(self.linhas) * H
        cv.configure(scrollregion=(0, 0, largura + 4, altura + 22))
        y0 = 20
        for k in range(passos + 1):                                   # régua
            x = R + k * W
            if k % 16 == 0 and k < passos:
                cv.create_text(x + 3, 10, text=str(k // 16 + 1), anchor="w", fill=COR["acento"],
                               font=("Segoe UI", 9, "bold"))
            elif k % 4 == 0 and k < passos:
                cv.create_text(x + 3, 10, text=str(k % 16 // 4 + 1), anchor="w", fill=COR["texto2"],
                               font=("Segoe UI", 8))
        for i, (nota, rotulo, preta) in enumerate(self.linhas):
            y = y0 + i * H
            cv.create_rectangle(R, y, largura, y + H, fill=COR["preta"] if preta else COR["branca"], width=0)
            cv.create_text(6, y + H / 2, text=rotulo, anchor="w", fill=COR["texto"], font=("Segoe UI", 9))
            cv.create_line(R, y, largura, y, fill=COR["fundo"])
        for k in range(passos + 1):
            x = R + k * W
            cor = COR["grade_forte"] if k % 16 == 0 else (COR["grade"] if k % 4 == 0 else COR["fundo"])
            cv.create_line(x, y0, x, y0 + altura, fill=cor, width=2 if k % 16 == 0 else 1)
        idx = {nota: i for i, (nota, _, _) in enumerate(self.linhas)}
        for n in self.notas:
            if n.nota not in idx:
                continue
            y = y0 + idx[n.nota] * H
            x1 = R + n.ini / SEMI * W
            x2 = R + min((n.ini + n.dur) / SEMI, passos) * W
            cor = COR["nota_forte"] if n.vel >= 100 else (COR["nota"] if n.vel >= 75 else COR["nota_fraca"])
            cv.create_rectangle(x1 + 1, y + 2, max(x1 + 6, x2 - 1), y + H - 2, fill=cor, outline="#0b1a33")
        if not self.linhas:
            cv.create_text(R + 20, 40, text="(sem linhas)", anchor="w", fill=COR["texto2"])

    def _onde(self, e):
        x, y = self.cv.canvasx(e.x), self.cv.canvasy(e.y)
        passo = int((x - self.ROTULO) // self.W)
        linha = int((y - 20) // self.H)
        if passo < 0 or passo >= self.compassos * 16 or linha < 0 or linha >= len(self.linhas):
            return None
        return passo, self.linhas[linha][0]

    def _nota_em(self, passo, nota):
        t = passo * SEMI
        for n in self.notas:
            if n.nota == nota and n.ini <= t < n.ini + max(n.dur, SEMI):
                return n
        return None

    def _clique(self, e):
        p = self._onde(e)
        if not p:
            return
        existente = self._nota_em(*p)
        if existente:
            self.notas.remove(existente)
        else:
            self.notas.append(Nota(p[0] * SEMI, self.dur_ticks, p[1], self.vel))
            self.notas.sort(key=lambda n: (n.ini, n.nota))
        self.desenhar()
        if self.on_change:
            self.on_change()

    def _clique_dir(self, e):
        p = self._onde(e)
        n = p and self._nota_em(*p)
        if n:
            n.vel = 85 if n.vel >= 100 else (60 if n.vel >= 75 else 115)
            self.desenhar()
            if self.on_change:
                self.on_change()


# ====================================================================== aplicativo
class App:
    def __init__(self, root: tk.Tk, ritmo: Ritmo | None = None, sem_audio=False):
        self.root = root
        self.ritmo = ritmo or ritmo_demo()
        self.caminho: str | None = None
        self.alterado = False
        root.title(f"Estúdio de Ritmos {VERSAO}")
        root.geometry("1280x800")
        root.minsize(1060, 680)
        self._estilo()

        self.synth = Sintetizador()
        self.synth.configurar_de_ritmo(self.ritmo)
        self.audio_ok = False
        if not sem_audio:
            try:
                self.synth.iniciar_audio()
                self.audio_ok = True
            except Exception as e:
                self.erro_audio = str(e)
        self.tocador = Tocador(self.ritmo)
        self.saida_atual = SOM_INTERNO
        self.saida_midi = None
        self.entrada_midi = None
        self.tocador.adicionar_saida(self.synth.enviar)
        self.mao = MaoEsquerda(self.tocador, split=54, direita=self._mao_direita)
        self.vst_vivo: dict[int, object] = {}
        self.analise = None
        self._taps: list[float] = []

        self._barra_superior()
        self.abas = ttk.Notebook(root)
        self.abas.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        self._aba_loop()
        self._aba_programar()
        self._aba_instrumentos()
        self._aba_tocar()
        self.status = ttk.Label(root, text="", style="Status.TLabel", anchor="w")
        self.status.pack(fill="x", side="bottom")
        self._msg("Pronto. " + ("Som interno ligado." if self.audio_ok else
                                "Sem placa de som disponível — use a saída MIDI ou renderize em WAV."))
        self._atalhos()
        self._atualizar_tudo()
        root.protocol("WM_DELETE_WINDOW", self.sair)
        self._loop_interface()

    # ------------------------------------------------------------------ visual
    def _estilo(self):
        st = ttk.Style(self.root)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        self.root.configure(bg=COR["fundo"])
        st.configure(".", background=COR["painel"], foreground=COR["texto"], fieldbackground=COR["branca"],
                     font=("Segoe UI", 10))
        st.configure("TFrame", background=COR["painel"])
        st.configure("Fundo.TFrame", background=COR["fundo"])
        st.configure("TLabel", background=COR["painel"], foreground=COR["texto"])
        st.configure("Fundo.TLabel", background=COR["fundo"])
        st.configure("Titulo.TLabel", font=("Segoe UI", 12, "bold"))
        st.configure("Dica.TLabel", foreground=COR["texto2"], font=("Segoe UI", 9))
        st.configure("Status.TLabel", background=COR["fundo"], foreground=COR["texto2"], padding=(10, 3))
        st.configure("Acorde.TLabel", font=("Segoe UI", 54, "bold"), foreground=COR["acento"])
        st.configure("Grande.TLabel", font=("Segoe UI", 16, "bold"))
        st.configure("TNotebook", background=COR["fundo"], borderwidth=0)
        st.configure("TNotebook.Tab", padding=(16, 7), font=("Segoe UI", 10, "bold"),
                     background=COR["grade"], foreground=COR["texto2"])
        st.map("TNotebook.Tab", background=[("selected", COR["painel"])],
               foreground=[("selected", COR["acento"])])
        st.configure("TButton", padding=(10, 5), background=COR["grade"], foreground=COR["texto"])
        st.map("TButton", background=[("active", COR["grade_forte"])])
        st.configure("Acao.TButton", background="#2f6fd1", foreground="white", font=("Segoe UI", 10, "bold"))
        st.map("Acao.TButton", background=[("active", "#3d8bfd")])
        st.configure("Secao.TButton", font=("Segoe UI", 11, "bold"), padding=(6, 12))
        st.configure("SecaoAtiva.TButton", font=("Segoe UI", 11, "bold"), padding=(6, 12),
                     background=COR["acento"], foreground="#1b1b1b")
        st.map("SecaoAtiva.TButton", background=[("active", "#ffc04d")])
        st.configure("SecaoProx.TButton", font=("Segoe UI", 11, "bold"), padding=(6, 12),
                     background="#6b5320", foreground="white")
        st.configure("Iniciar.TButton", font=("Segoe UI", 14, "bold"), padding=(10, 14),
                     background=COR["ok"], foreground="#0d1f16")
        st.configure("Parar.TButton", font=("Segoe UI", 14, "bold"), padding=(10, 14),
                     background=COR["alerta"], foreground="white")
        st.configure("TCheckbutton", background=COR["painel"], foreground=COR["texto"])
        st.configure("TRadiobutton", background=COR["painel"], foreground=COR["texto"])
        st.configure("TLabelframe", background=COR["painel"], foreground=COR["texto"])
        st.configure("TLabelframe.Label", background=COR["painel"], foreground=COR["acento"],
                     font=("Segoe UI", 10, "bold"))
        st.configure("Treeview", background=COR["branca"], fieldbackground=COR["branca"], foreground=COR["texto"])
        for w in ("TCombobox", "TSpinbox", "TEntry"):
            st.configure(w, fieldbackground=COR["branca"], foreground=COR["texto"], background=COR["grade"],
                         arrowcolor=COR["texto"], insertcolor=COR["texto"])
            st.map(w, fieldbackground=[("readonly", COR["branca"]), ("disabled", COR["painel"])],
                   foreground=[("readonly", COR["texto"]), ("disabled", COR["texto2"])],
                   selectbackground=[("readonly", COR["branca"])], selectforeground=[("readonly", COR["acento"])])
        self.root.option_add("*TCombobox*Listbox.background", COR["branca"])
        self.root.option_add("*TCombobox*Listbox.foreground", COR["texto"])

    def _msg(self, texto):
        self.status.configure(text=texto)

    def _marcar(self):
        self.alterado = True
        self._atualizar_titulo()

    def _atualizar_titulo(self):
        nome = os.path.basename(self.caminho) if self.caminho else "(não salvo)"
        self.root.title(f"Estúdio de Ritmos {VERSAO} — {self.ritmo.nome} — {nome}{' *' if self.alterado else ''}")

    def _erro(self, titulo, e):
        traceback.print_exc()
        messagebox.showerror(titulo, f"{e}")

    # ------------------------------------------------------------------ barra superior
    def _barra_superior(self):
        b = ttk.Frame(self.root, style="Fundo.TFrame", padding=(8, 8, 8, 2))
        b.pack(fill="x")
        b2 = ttk.Frame(self.root, style="Fundo.TFrame", padding=(8, 2, 8, 6))
        b2.pack(fill="x")
        for txt, cmd in (("Novo", self.novo), ("Demo", self.demo), ("Abrir…", self.abrir),
                         ("Salvar", self.salvar), ("Salvar como…", lambda: self.salvar(True)),
                         ("Exportar música…", self.janela_exportar)):
            ttk.Button(b, text=txt, command=cmd).pack(side="left", padx=(0, 4))
        ttk.Label(b, text="  Nome:", style="Fundo.TLabel").pack(side="left")
        self.var_nome = tk.StringVar(value=self.ritmo.nome)
        e = ttk.Entry(b, textvariable=self.var_nome, width=20)
        e.pack(side="left", padx=4)
        self.var_nome.trace_add("write", lambda *_: self._mudar_nome())
        ttk.Label(b, text="BPM:", style="Fundo.TLabel").pack(side="left", padx=(8, 0))
        self.var_bpm = tk.DoubleVar(value=self.ritmo.bpm)
        sp = ttk.Spinbox(b, from_=40, to=250, increment=1, textvariable=self.var_bpm, width=6,
                         command=self._mudar_bpm)
        sp.pack(side="left", padx=4)
        sp.bind("<Return>", lambda e: self._mudar_bpm())
        sp.bind("<FocusOut>", lambda e: self._mudar_bpm())

        ttk.Label(b2, text="Saída do som:", style="Fundo.TLabel").pack(side="left")
        self.var_saida = tk.StringVar(value=SOM_INTERNO)
        self.cb_saida = ttk.Combobox(b2, textvariable=self.var_saida, width=34, state="readonly")
        self.cb_saida.pack(side="left", padx=4)
        self.cb_saida.bind("<<ComboboxSelected>>", lambda e: self._mudar_saida())
        self.cb_saida.bind("<Button-1>", lambda e: self._listar_portas())
        ttk.Label(b2, text="   Teclado MIDI (entrada):", style="Fundo.TLabel").pack(side="left", padx=(6, 0))
        self.var_entrada = tk.StringVar(value="(nenhum)")
        self.cb_entrada = ttk.Combobox(b2, textvariable=self.var_entrada, width=30, state="readonly")
        self.cb_entrada.pack(side="left", padx=4)
        self.cb_entrada.bind("<<ComboboxSelected>>", lambda e: self._mudar_entrada())
        self.cb_entrada.bind("<Button-1>", lambda e: self._listar_portas())
        self._listar_portas()

    def _listar_portas(self):
        self.cb_saida["values"] = [SOM_INTERNO] + ["MIDI: " + n for n in midi_io.listar_saidas()]
        self.cb_entrada["values"] = ["(nenhum)"] + midi_io.listar_entradas()

    def _mudar_nome(self):
        self.ritmo.nome = self.var_nome.get()
        self._marcar()

    def _mudar_bpm(self):
        try:
            bpm = float(self.var_bpm.get())
        except (tk.TclError, ValueError):
            return
        if abs(bpm - self.ritmo.bpm) > 1e-6:
            self.ritmo.bpm = bpm
            self.tocador.definir_bpm(bpm)
            self._marcar()

    def _mudar_saida(self):
        escolha = self.var_saida.get()
        if self.saida_midi:
            self.tocador.remover_saida(self.saida_midi)
            self.saida_midi.fechar()
            self.saida_midi = None
        self.tocador.remover_saida(self.synth.enviar)
        if escolha == SOM_INTERNO:
            self.tocador.adicionar_saida(self.synth.enviar)
            self._msg("Saída: som interno.")
            return
        try:
            self.saida_midi = midi_io.SaidaMidi(escolha[len("MIDI: "):])
            self.tocador.adicionar_saida(self.saida_midi)
            # pistas com VST ao vivo continuam no programa
            if self.vst_vivo:
                self.tocador.adicionar_saida(self._so_vst)
            self._msg(f"Saída MIDI: {escolha[6:]} — no Kontakt/DAW, use os canais 9 a 16.")
        except Exception as e:
            self.var_saida.set(SOM_INTERNO)
            self.tocador.adicionar_saida(self.synth.enviar)
            self._erro("Saída MIDI", e)

    def _so_vst(self, msg):
        if getattr(msg, "channel", None) in self.vst_vivo:
            self.synth.enviar(msg)

    def _mudar_entrada(self):
        if self.entrada_midi:
            self.entrada_midi.fechar()
            self.entrada_midi = None
        nome = self.var_entrada.get()
        if nome == "(nenhum)":
            return
        try:
            self.entrada_midi = midi_io.EntradaMidi(nome, self.mao.receber)
            self._msg(f"Teclado MIDI: {nome}. Mão esquerda (abaixo de {AC.nome_nota(self.mao.split)}) faz o acorde.")
        except Exception as e:
            self.var_entrada.set("(nenhum)")
            self._erro("Teclado MIDI", e)

    def _mao_direita(self, msg):
        self.synth.enviar(msg)
        if self.saida_midi:
            self.saida_midi(msg)

    # ------------------------------------------------------------------ arquivo
    def _confirmar_descartar(self):
        if not self.alterado:
            return True
        r = messagebox.askyesnocancel("Ritmo alterado", "Salvar as alterações antes?")
        if r is None:
            return False
        if r:
            return self.salvar()
        return True

    def _trocar_ritmo(self, r: Ritmo, caminho=None):
        self.tocador.parar()
        self.ritmo = r
        self.tocador.ritmo = r
        self.tocador.bpm = r.bpm
        self.synth.configurar_de_ritmo(r)
        for c in list(self.vst_vivo):
            self.synth.desligar_vst(c)
        self.vst_vivo.clear()
        self.caminho = caminho
        self.alterado = False
        self.var_nome.set(r.nome)
        self.alterado = False
        self.var_bpm.set(r.bpm)
        self._atualizar_tudo()

    def novo(self):
        if self._confirmar_descartar():
            self._trocar_ritmo(ritmo_vazio())

    def demo(self):
        if self._confirmar_descartar():
            self._trocar_ritmo(ritmo_demo())

    def abrir(self, caminho=None):
        if not self._confirmar_descartar():
            return
        caminho = caminho or filedialog.askopenfilename(filetypes=[("Ritmo", "*.ritmo"), ("Todos", "*.*")])
        if not caminho:
            return
        try:
            self._trocar_ritmo(Ritmo.abrir(caminho), caminho)
            self._msg(f"Aberto: {caminho}")
        except Exception as e:
            self._erro("Abrir ritmo", e)

    def salvar(self, como=False):
        if como or not self.caminho:
            c = filedialog.asksaveasfilename(defaultextension=".ritmo", initialfile=self.ritmo.nome + ".ritmo",
                                             filetypes=[("Ritmo", "*.ritmo")])
            if not c:
                return False
            self.caminho = c
        try:
            for canal, inst in self.vst_vivo.items():            # guarda o estado atual dos VSTs
                for p in self.ritmo.pistas:
                    if p.canal == canal:
                        p.vst_estado = inst.estado()
            self.ritmo.salvar(self.caminho)
            self.alterado = False
            self._atualizar_titulo()
            self._msg(f"Salvo: {self.caminho}")
            return True
        except Exception as e:
            self._erro("Salvar", e)
            return False

    def sair(self):
        if not self._confirmar_descartar():
            return
        self.tocador.parar()
        self.synth.parar_audio()
        for p in (self.saida_midi, self.entrada_midi):
            if p:
                p.fechar()
        self.root.destroy()

    # ================================================================== ABA 1: IMPORTAR LOOP
    def _aba_loop(self):
        f = ttk.Frame(self.abas, padding=10)
        self.abas.add(f, text="  1 · Importar loop  ")
        esq = ttk.Frame(f, width=300)
        esq.pack(side="left", fill="y", padx=(0, 10))
        ttk.Label(esq, text="Loop de bateria → MIDI", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(esq, text="WAV, MP3, AIFF ou FLAC. Melhor com loop só de bateria,\ncortado certinho no compasso.",
                  style="Dica.TLabel").pack(anchor="w", pady=(2, 10))
        ttk.Button(esq, text="Escolher arquivo de áudio…", style="Acao.TButton",
                   command=self._escolher_loop).pack(fill="x")
        self.lbl_loop = ttk.Label(esq, text="Nenhum arquivo", style="Dica.TLabel", wraplength=280)
        self.lbl_loop.pack(anchor="w", pady=4)

        lf = ttk.Labelframe(esq, text="Ajustes", padding=8)
        lf.pack(fill="x", pady=8)
        ttk.Label(lf, text="Sensibilidade").grid(row=0, column=0, sticky="w")
        self.var_sens = tk.DoubleVar(value=1.0)
        ttk.Scale(lf, from_=0.6, to=1.8, variable=self.var_sens).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Label(lf, text="Quantização %").grid(row=1, column=0, sticky="w")
        self.var_quant = tk.IntVar(value=100)
        ttk.Spinbox(lf, from_=0, to=100, increment=10, textvariable=self.var_quant, width=5).grid(
            row=1, column=1, sticky="w", padx=6)
        ttk.Label(lf, text="BPM (vazio = detectar)").grid(row=2, column=0, sticky="w")
        self.var_bpm_loop = tk.StringVar()
        ttk.Entry(lf, textvariable=self.var_bpm_loop, width=8).grid(row=2, column=1, sticky="w", padx=6)
        lf.columnconfigure(1, weight=1)
        self.btn_analisar = ttk.Button(esq, text="Analisar loop", style="Acao.TButton",
                                       command=self._analisar_loop, state="disabled")
        self.btn_analisar.pack(fill="x")
        self.lbl_res = ttk.Label(esq, text="", wraplength=280)
        self.lbl_res.pack(anchor="w", pady=8)

        ou = ttk.Frame(esq)
        ou.pack(fill="x")
        ttk.Button(ou, text="▶ Original", command=self._ouvir_original).pack(side="left", expand=True, fill="x")
        ttk.Button(ou, text="▶ Detectado", command=self._ouvir_detectado).pack(side="left", expand=True, fill="x", padx=4)
        ttk.Button(ou, text="■", width=3, command=parar_audio).pack(side="left")

        lf2 = ttk.Labelframe(esq, text="Enviar para o ritmo", padding=8)
        lf2.pack(fill="x", pady=10)
        ttk.Label(lf2, text="Seção").grid(row=0, column=0, sticky="w")
        self.var_dest_sec = tk.StringVar(value="Var A")
        ttk.Combobox(lf2, textvariable=self.var_dest_sec, values=SECOES, state="readonly", width=12).grid(
            row=0, column=1, sticky="w", padx=6, pady=2)
        ttk.Label(lf2, text="Pista").grid(row=1, column=0, sticky="w")
        self.var_dest_pista = tk.StringVar(value="2 · Rhythm 2 (Bateria)")
        self.cb_dest_pista = ttk.Combobox(lf2, textvariable=self.var_dest_pista, state="readonly", width=24)
        self.cb_dest_pista.grid(row=1, column=1, sticky="w", padx=6, pady=2)
        self.var_usar_bpm = tk.BooleanVar(value=True)
        ttk.Checkbutton(lf2, text="Usar o BPM do loop no ritmo", variable=self.var_usar_bpm).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=4)
        self.btn_enviar = ttk.Button(lf2, text="Enviar", style="Acao.TButton", command=self._enviar_loop,
                                     state="disabled")
        self.btn_enviar.grid(row=3, column=0, columnspan=2, sticky="ew")

        dir_ = ttk.Frame(f)
        dir_.pack(side="left", fill="both", expand=True)
        ttk.Label(dir_, text="Resultado da detecção (cada coluna = 1 semicolcheia)", style="Titulo.TLabel").pack(anchor="w")
        self.grade_loop = EditorGrade(dir_, somente_leitura=True)
        self.grade_loop.pack(fill="both", expand=True, pady=6)
        self.loop_arquivo = None

    def _escolher_loop(self):
        c = filedialog.askopenfilename(filetypes=[("Áudio", "*.wav *.mp3 *.aif *.aiff *.flac *.ogg"), ("Todos", "*.*")])
        if c:
            self._definir_loop(c)

    def _definir_loop(self, caminho):
        self.loop_arquivo = caminho
        self.lbl_loop.configure(text=os.path.basename(caminho))
        self.btn_analisar.configure(state="normal")
        import re
        m = re.search(r"(\d{2,3}(?:[.,]\d+)?)\s*bpm|bpm\s*_?(\d{2,3})", os.path.basename(caminho), re.I)
        self.var_bpm_loop.set("")
        if m:
            self._msg(f"O nome do arquivo sugere {m.group(1) or m.group(2)} BPM — o programa mede o andamento real.")

    def _analisar_loop(self, sincrono=False):
        if not self.loop_arquivo:
            return
        self.btn_analisar.configure(state="disabled", text="Analisando…")
        try:
            bpm = float(self.var_bpm_loop.get().replace(",", ".")) if self.var_bpm_loop.get().strip() else None
        except ValueError:
            bpm = None

        def trabalho():
            try:
                from nucleo.deteccao import analisar
                r = analisar(self.loop_arquivo, bpm, self.var_quant.get() / 100, self.var_sens.get())
                self.root.after(0, lambda: self._mostrar_analise(r))
            except Exception as e:
                self.root.after(0, lambda e=e: (self._erro("Análise do loop", e),
                                                self.btn_analisar.configure(state="normal", text="Analisar loop")))
        if sincrono:
            trabalho()
        else:
            threading.Thread(target=trabalho, daemon=True).start()

    def _mostrar_analise(self, r):
        self.analise = r
        self.btn_analisar.configure(state="normal", text="Analisar loop")
        notas, comp = notas_da_deteccao(r["batidas"], r["bpm"])
        self.analise_notas, self.analise_comp = notas, comp
        cont = {}
        for b in r["batidas"]:
            cont[b["peca"]] = cont.get(b["peca"], 0) + 1
        nomes = {"bumbo": "bumbo", "caixa": "caixa", "tom": "tom", "chimbal": "chimbal",
                 "chimbal_aberto": "chimbal aberto"}
        bpm_txt = f"{r['bpm']:.2f}".rstrip("0").rstrip(".")
        self.lbl_res.configure(text=f"Andamento: {bpm_txt} BPM (arquivo: {r['bpm_arquivo']:g})\n"
                               f"{comp} compasso(s), {r['duracao_s']:.2f} s\n" +
                               ", ".join(f"{v} {nomes.get(k, k)}" for k, v in sorted(cont.items())))
        usadas = sorted({n.nota for n in notas})
        linhas = [(n, rot, False) for n, rot in PECAS_BATERIA if n in usadas]
        self.grade_loop.carregar(linhas, notas, comp)
        self.btn_enviar.configure(state="normal")
        self._msg("Análise pronta. Confira ouvindo '▶ Detectado' e envie para o ritmo.")

    def _ouvir_original(self):
        if not self.loop_arquivo:
            return
        import librosa
        y, sr = librosa.load(self.loop_arquivo, sr=44100, mono=False)
        tocar_audio(y.T if y.ndim > 1 else y, sr)

    def _ouvir_detectado(self):
        if not self.analise:
            return
        s = Sintetizador({9: ("bateria", 1.0)})
        bpm = self.analise["bpm"]
        evs = []
        import mido
        for rep in range(2):
            for n in self.analise_notas:
                t = (n.ini + rep * self.analise_comp * COMPASSO) / PPQ * 60 / bpm
                evs.append((t, mido.Message("note_on", channel=9, note=n.nota, velocity=n.vel)))
        tocar_audio(s.renderizar(evs, 2 * self.analise_comp * 4 * 60 / bpm), 44100)

    def _enviar_loop(self):
        if not self.analise:
            return
        sec = self.var_dest_sec.get()
        pista = int(self.var_dest_pista.get().split("·")[0]) - 1
        s = self.ritmo.secoes[sec]
        outras = any(s.pistas.get(i) for i in range(8) if i != pista)
        if outras and self.analise_comp > s.compassos:
            s.estender(self.analise_comp, exceto=pista)       # repete baixo/acordes para acompanhar o loop
        elif not outras:
            s.compassos = self.analise_comp
        s.pistas[pista] = [Nota(n.ini, n.dur, n.nota, n.vel) for n in self.analise_notas]
        if self.var_usar_bpm.get():
            self.var_bpm.set(self.analise["bpm_arquivo"])
            self._mudar_bpm()
        self._marcar()
        self._atualizar_tudo()
        self._msg(f"Bateria enviada para '{sec}', pista {pista + 1}. Veja na aba Programar.")

    # ================================================================== ABA 2: PROGRAMAR
    def _aba_programar(self):
        f = ttk.Frame(self.abas, padding=10)
        self.abas.add(f, text="  2 · Programar  ")
        esq = ttk.Frame(f)
        esq.pack(side="left", fill="y", padx=(0, 10))
        ttk.Label(esq, text="Seções", style="Titulo.TLabel").pack(anchor="w")
        self.lb_secoes = tk.Listbox(esq, height=15, width=16, bg=COR["branca"], fg=COR["texto"],
                                    selectbackground=COR["acento"], selectforeground="#111",
                                    font=("Segoe UI", 10), activestyle="none", exportselection=False,
                                    highlightthickness=0, borderwidth=0)
        self.lb_secoes.pack(fill="y", pady=4)
        self.lb_secoes.bind("<<ListboxSelect>>", lambda e: self._sel_secao())
        lf = ttk.Frame(esq)
        lf.pack(fill="x", pady=4)
        ttk.Label(lf, text="Compassos").pack(side="left")
        self.var_comp = tk.IntVar(value=1)
        sp = ttk.Spinbox(lf, from_=1, to=16, textvariable=self.var_comp, width=4, command=self._mudar_comp)
        sp.pack(side="left", padx=6)
        sp.bind("<Return>", lambda e: self._mudar_comp())
        ttk.Button(esq, text="Copiar de outra seção…", command=self._copiar_secao).pack(fill="x", pady=2)
        ttk.Button(esq, text="Limpar seção", command=self._limpar_secao).pack(fill="x", pady=2)
        ttk.Separator(esq).pack(fill="x", pady=8)
        ttk.Label(esq, text="Ouvir seção no acorde:").pack(anchor="w")
        lo = ttk.Frame(esq)
        lo.pack(fill="x", pady=2)
        self.var_ac_prev = tk.StringVar(value="C")
        ttk.Entry(lo, textvariable=self.var_ac_prev, width=8).pack(side="left")
        ttk.Button(lo, text="▶", width=3, command=self._ouvir_secao).pack(side="left", padx=4)
        ttk.Button(lo, text="■", width=3, command=parar_audio).pack(side="left")
        ttk.Label(esq, text="(toca 2 vezes; aceita vários:\n'C Am F G')", style="Dica.TLabel").pack(anchor="w")

        dir_ = ttk.Frame(f)
        dir_.pack(side="left", fill="both", expand=True)
        topo = ttk.Frame(dir_)
        topo.pack(fill="x")
        self.var_pista = tk.IntVar(value=1)
        self.rb_pistas = []
        for i in range(8):
            rb = ttk.Radiobutton(topo, text=f"{i + 1}", value=i, variable=self.var_pista,
                                 command=self._sel_pista)
            rb.pack(side="left", padx=2)
            self.rb_pistas.append(rb)
        ferr = ttk.Frame(dir_)
        ferr.pack(fill="x", pady=6)
        self.lbl_pista = ttk.Label(ferr, text="", style="Titulo.TLabel")
        self.lbl_pista.pack(side="left")
        ttk.Button(ferr, text="Limpar pista", command=self._limpar_pista).pack(side="right")
        ttk.Button(ferr, text="Importar MIDI…", command=self._importar_midi).pack(side="right", padx=4)
        opc = ttk.Frame(ferr)
        opc.pack(side="right", padx=12)
        ttk.Label(opc, text="Duração:").pack(side="left")
        self.var_dur = tk.StringVar(value="1/16")
        cbd = ttk.Combobox(opc, textvariable=self.var_dur, values=["1/16", "1/8", "1/4", "1/2", "1 compasso"],
                           width=10, state="readonly")
        cbd.pack(side="left", padx=4)
        cbd.bind("<<ComboboxSelected>>", lambda e: self._cfg_editor())
        ttk.Label(opc, text="  Força:").pack(side="left")
        self.var_vel = tk.StringVar(value="Forte")
        cbv = ttk.Combobox(opc, textvariable=self.var_vel, values=["Forte", "Médio", "Fraco"], width=7,
                           state="readonly")
        cbv.pack(side="left", padx=4)
        cbv.bind("<<ComboboxSelected>>", lambda e: self._cfg_editor())
        self.editor = EditorGrade(dir_, on_change=self._editou)
        self.editor.pack(fill="both", expand=True)
        self.lbl_dica = ttk.Label(dir_, style="Dica.TLabel", text="")
        self.lbl_dica.pack(anchor="w", pady=(4, 0))

    def _secao_sel(self):
        s = self.lb_secoes.curselection()
        return SECOES[s[0]] if s else "Var A"

    def _atualizar_lista_secoes(self):
        sel = self.lb_secoes.curselection()
        self.lb_secoes.delete(0, "end")
        for nome in SECOES:
            s = self.ritmo.secoes[nome]
            marca = "●" if not s.vazia else "○"
            self.lb_secoes.insert("end", f" {marca} {nome}   ({s.compassos})")
        self.lb_secoes.selection_set(sel[0] if sel else SECOES.index("Var A"))

    def _sel_secao(self):
        self.var_comp.set(self.ritmo.secoes[self._secao_sel()].compassos)
        self._carregar_editor()

    def _sel_pista(self):
        self._carregar_editor()

    def _linhas_pista(self, i):
        cfg = self.ritmo.pistas[i]
        if cfg.regra == AC.BYPASS:
            usadas = {n.nota for s in self.ritmo.secoes.values() for n in s.pistas.get(i, [])}
            linhas = [(n, rot, False) for n, rot in PECAS_BATERIA]
            extras = sorted(usadas - {n for n, _ in PECAS_BATERIA})
            return linhas + [(n, f"Nota {n}", False) for n in extras]
        lo, hi = cfg.faixa
        lo, hi = max(0, lo - 5), min(127, hi + 5)
        return [(n, AC.nome_nota(n) + ("  ← C" if n % 12 == 0 else ""), n % 12 in (1, 3, 6, 8, 10))
                for n in range(hi, lo - 1, -1)]

    def _carregar_editor(self):
        i = self.var_pista.get()
        sec = self.ritmo.secoes[self._secao_sel()]
        cfg = self.ritmo.pistas[i]
        self.lbl_pista.configure(text=f"{self._secao_sel()}  ›  Pista {i + 1}: {cfg.nome}")
        self.editor.carregar(self._linhas_pista(i), sec.notas(i), sec.compassos)
        self._cfg_editor()
        if cfg.regra == AC.BYPASS:
            self.lbl_dica.configure(text="Clique para pôr/tirar uma batida. Botão direito muda a força. "
                                         "A bateria não é transposta.")
        else:
            self.lbl_dica.configure(text="Programe esta pista em DÓ (acorde C / CMaj7: Dó, Mi, Sol, Si). "
                                         f"O motor transpõe pela regra '{AC.NOMES_REGRAS[cfg.regra]}'. "
                                         "Clique põe/tira nota; botão direito muda a força.")

    def _cfg_editor(self):
        d = {"1/16": SEMI, "1/8": 2 * SEMI, "1/4": PPQ, "1/2": 2 * PPQ, "1 compasso": COMPASSO}
        self.editor.dur_ticks = d.get(self.var_dur.get(), SEMI)
        if self.ritmo.pistas[self.var_pista.get()].regra == AC.BYPASS:
            self.editor.dur_ticks = SEMI
        self.editor.vel = {"Forte": 110, "Médio": 85, "Fraco": 60}[self.var_vel.get()]

    def _editou(self):
        self._marcar()
        self._atualizar_lista_secoes()

    def _mudar_comp(self):
        try:
            c = max(1, min(16, int(self.var_comp.get())))
        except (tk.TclError, ValueError):
            return
        self.ritmo.secoes[self._secao_sel()].compassos = c
        self._marcar()
        self._atualizar_lista_secoes()
        self._carregar_editor()

    def _copiar_secao(self):
        destino = self._secao_sel()
        origem = simpledialog.askstring("Copiar seção", f"Copiar QUAL seção para '{destino}'?\n"
                                        f"(ex.: Var A)", parent=self.root)
        if not origem:
            return
        origem = {s.lower(): s for s in SECOES}.get(origem.strip().lower())
        if not origem:
            messagebox.showwarning("Copiar seção", "Seção não encontrada.")
            return
        self.ritmo.copiar_secao(origem, destino)
        self._marcar(); self._atualizar_tudo()

    def _limpar_secao(self):
        s = self._secao_sel()
        if messagebox.askyesno("Limpar seção", f"Apagar todas as notas de '{s}'?"):
            self.ritmo.secoes[s].pistas.clear()
            self._marcar(); self._atualizar_tudo()

    def _limpar_pista(self):
        sec = self.ritmo.secoes[self._secao_sel()]
        sec.pistas[self.var_pista.get()] = []
        self._marcar(); self._atualizar_tudo()

    def _importar_midi(self):
        c = filedialog.askopenfilename(filetypes=[("MIDI", "*.mid *.midi")])
        if not c:
            return
        canal = simpledialog.askstring("Importar MIDI", "Canal MIDI a importar (1–16)?\nDeixe vazio para todos.",
                                       parent=self.root)
        try:
            notas, comp = ler_midi(c, int(canal) - 1 if canal and canal.strip() else None)
        except Exception as e:
            return self._erro("Importar MIDI", e)
        sec = self.ritmo.secoes[self._secao_sel()]
        sec.pistas[self.var_pista.get()] = notas
        sec.compassos = max(sec.compassos, comp)
        self._marcar(); self._atualizar_tudo()
        self._msg(f"{len(notas)} notas importadas ({comp} compasso(s)).")

    def _ouvir_secao(self):
        nome = self._secao_sel()
        sec = self.ritmo.secoes[nome]
        if sec.vazia:
            return self._msg("Seção vazia.")
        try:
            acs = [[AC.parse_acorde(a) for a in tok.split(",")] for tok in self.var_ac_prev.get().split()] \
                or [[AC.ACORDE_PADRAO]]
        except ValueError as e:
            return self._erro("Acorde", e)
        n = max(sec.compassos, len(acs)) * 2
        compassos = [acs[k % len(acs)] for k in range(n)]
        rot = []
        for k in range(0, n, sec.compassos):
            rot.append((nome, compassos[k:k + sec.compassos]))
        ev, tot = EX.gerar_eventos(self.ritmo, [(s, c) for s, c in rot])
        if nome.startswith(("Fill", "Break", "Intro", "Final")):
            pass

        def trab():
            import tempfile, soundfile as sf
            tmp = os.path.join(tempfile.gettempdir(), "estudio_previa.wav")
            EX.renderizar(self.ritmo, ev, tot, tmp, usar_vst=False)
            dados, sr = sf.read(tmp, dtype="float32")
            self.root.after(0, lambda: tocar_audio(dados, sr))
        threading.Thread(target=trab, daemon=True).start()
        self._msg("Preparando prévia (som interno)…")

    # ================================================================== ABA 3: INSTRUMENTOS
    def _aba_instrumentos(self):
        f = ttk.Frame(self.abas, padding=10)
        self.abas.add(f, text="  3 · Instrumentos  ")
        ttk.Label(f, text="Instrumento de cada pista", style="Titulo.TLabel").grid(row=0, column=0, columnspan=10, sticky="w")
        ttk.Label(f, style="Dica.TLabel", text=(
            "Som interno = timbre simples do programa. VST = Kontakt ou outro instrumento instalado: "
            "'VST…' e depois 'Janela' para escolher a biblioteca no Kontakt.\n"
            "O VST é usado ao renderizar WAV; marque 'Ao vivo' para tocar com ele em tempo real (experimental). "
            "Pela saída MIDI, cada pista sai no seu canal (9 a 16).")).grid(row=1, column=0, columnspan=10, sticky="w", pady=(2, 10))
        cab = ["Pista", "Regra de transposição", "Canal", "Faixa (notas)", "Som interno", "VST", "", "Ao vivo",
               "Volume", "Mudo"]
        for c, t in enumerate(cab):
            ttk.Label(f, text=t, style="Dica.TLabel").grid(row=2, column=c, sticky="w", padx=4)
        self.linhas_inst = []
        nomes_regras = [AC.NOMES_REGRAS[r] for r in AC.REGRAS]
        for i in range(8):
            r = 3 + i
            w = {}
            w["nome"] = tk.StringVar()
            e = ttk.Entry(f, textvariable=w["nome"], width=20)
            e.grid(row=r, column=0, sticky="w", padx=4, pady=3)
            w["regra"] = tk.StringVar()
            cb = ttk.Combobox(f, textvariable=w["regra"], values=nomes_regras, state="readonly", width=20)
            cb.grid(row=r, column=1, padx=4)
            w["canal"] = tk.IntVar()
            ttk.Spinbox(f, from_=1, to=16, textvariable=w["canal"], width=4).grid(row=r, column=2, padx=4)
            w["faixa"] = tk.StringVar()
            ttk.Entry(f, textvariable=w["faixa"], width=7).grid(row=r, column=3, padx=4)
            w["som"] = tk.StringVar()
            ttk.Combobox(f, textvariable=w["som"], values=SONS_INTERNOS, state="readonly", width=9).grid(row=r, column=4, padx=4)
            w["lbl_vst"] = ttk.Label(f, text="—", width=16)
            w["lbl_vst"].grid(row=r, column=5, sticky="w", padx=4)
            bf = ttk.Frame(f)
            bf.grid(row=r, column=6, sticky="w")
            ttk.Button(bf, text="VST…", width=5, command=lambda i=i: self._escolher_vst(i)).pack(side="left")
            ttk.Button(bf, text="Janela", width=6, command=lambda i=i: self._janela_vst(i)).pack(side="left", padx=2)
            ttk.Button(bf, text="✕", width=2, command=lambda i=i: self._remover_vst(i)).pack(side="left")
            w["vivo"] = tk.BooleanVar()
            ttk.Checkbutton(f, variable=w["vivo"], command=lambda i=i: self._vst_ao_vivo(i)).grid(row=r, column=7)
            w["vol"] = tk.DoubleVar()
            ttk.Scale(f, from_=0, to=1, variable=w["vol"], length=90).grid(row=r, column=8, padx=4)
            w["mudo"] = tk.BooleanVar()
            ttk.Checkbutton(f, variable=w["mudo"]).grid(row=r, column=9)
            for chave in ("nome", "regra", "canal", "faixa", "som", "vol", "mudo"):
                w[chave].trace_add("write", lambda *_a, i=i: self._inst_mudou(i))
            self.linhas_inst.append(w)

        bx = ttk.Frame(f)
        bx.grid(row=12, column=0, columnspan=10, sticky="w", pady=12)
        ttk.Button(bx, text="Mapa de notas da bateria…", command=self._mapa_notas).pack(side="left")
        ttk.Button(bx, text="Procurar plugins instalados", command=self._procurar_plugins).pack(side="left", padx=6)
        self.lbl_vst_info = ttk.Label(f, style="Dica.TLabel",
                                      text="" if VST.DISPONIVEL else "Biblioteca 'pedalboard' não instalada: VSTs desativados.")
        self.lbl_vst_info.grid(row=13, column=0, columnspan=10, sticky="w")
        self._carregando_inst = False

    def _preencher_instrumentos(self):
        self._carregando_inst = True
        for i, w in enumerate(self.linhas_inst):
            p = self.ritmo.pistas[i]
            w["nome"].set(p.nome)
            w["regra"].set(AC.NOMES_REGRAS[p.regra])
            w["canal"].set(p.canal + 1)
            w["faixa"].set(f"{p.faixa[0]}-{p.faixa[1]}")
            w["som"].set(p.som_interno)
            w["lbl_vst"].configure(text=VST.nome_curto(p.vst) + (" ✓estado" if p.vst_estado else ""))
            w["vivo"].set(p.canal in self.vst_vivo)
            w["vol"].set(p.volume)
            w["mudo"].set(p.mudo)
        self._carregando_inst = False

    def _inst_mudou(self, i):
        if self._carregando_inst:
            return
        w, p = self.linhas_inst[i], self.ritmo.pistas[i]
        try:
            p.nome = w["nome"].get()
            inv = {v: k for k, v in AC.NOMES_REGRAS.items()}
            p.regra = inv.get(w["regra"].get(), p.regra)
            canal_novo = max(1, min(16, int(w["canal"].get()))) - 1
            if canal_novo != p.canal:
                self.tocador.parar()
                p.canal = canal_novo
            lo, hi = (int(x) for x in w["faixa"].get().split("-"))
            if 0 <= lo < hi <= 127:
                p.faixa = (lo, hi)
            p.som_interno = w["som"].get() or p.som_interno
            p.volume = float(w["vol"].get())
            p.mudo = bool(w["mudo"].get())
        except (ValueError, tk.TclError):
            return
        self.synth.configurar_de_ritmo(self.ritmo)
        self._marcar()

    def _escolher_vst(self, i):
        if not VST.DISPONIVEL:
            return messagebox.showwarning("VST", "Instale a biblioteca 'pedalboard' (o instalador faz isso).")
        tipos = [("Plugins", "*.vst3 *.component"), ("Todos", "*.*")]
        pasta = next((str(p) for p in VST.pastas_padrao() if p.exists()), None)
        c = filedialog.askopenfilename(filetypes=tipos, initialdir=pasta)
        if not c:
            c = filedialog.askdirectory(initialdir=pasta, title="…ou escolha a pasta .vst3")
        if not c:
            return
        self._usar_vst(i, c)

    def _usar_vst(self, i, caminho):
        p = self.ritmo.pistas[i]
        try:
            self.root.config(cursor="watch"); self.root.update()
            inst = VST.InstrumentoVST(caminho)
        except Exception as e:
            self.root.config(cursor="")
            return self._erro("Carregar VST", e)
        self.root.config(cursor="")
        p.vst, p.vst_estado = caminho, inst.estado()
        self._cache_vst = getattr(self, "_cache_vst", {})
        self._cache_vst[i] = inst
        self._marcar(); self._preencher_instrumentos()
        self._msg(f"Pista {i + 1}: {VST.nome_curto(caminho)} carregado. Clique 'Janela' para escolher a biblioteca.")

    def _instancia(self, i):
        p = self.ritmo.pistas[i]
        self._cache_vst = getattr(self, "_cache_vst", {})
        inst = self._cache_vst.get(i)
        if inst is None or inst.caminho != p.vst:
            inst = VST.InstrumentoVST(p.vst, p.vst_estado)
            self._cache_vst[i] = inst
        return inst

    def _janela_vst(self, i):
        p = self.ritmo.pistas[i]
        if not p.vst:
            return messagebox.showinfo("VST", "Escolha um VST para esta pista primeiro.")
        try:
            inst = self.vst_vivo.get(p.canal) or self._instancia(i)
            self._msg("Janela do plugin aberta — feche-a para voltar ao programa.")
            self.root.update()
            inst.abrir_janela()
            p.vst_estado = inst.estado()
            self._marcar(); self._preencher_instrumentos()
            self._msg(f"Estado do {VST.nome_curto(p.vst)} guardado na pista {i + 1}.")
        except Exception as e:
            self._erro("Janela do VST", e)

    def _remover_vst(self, i):
        p = self.ritmo.pistas[i]
        if p.canal in self.vst_vivo:
            self.synth.desligar_vst(p.canal); self.vst_vivo.pop(p.canal)
        p.vst = p.vst_estado = None
        getattr(self, "_cache_vst", {}).pop(i, None)
        self._marcar(); self._preencher_instrumentos()

    def _vst_ao_vivo(self, i):
        p, w = self.ritmo.pistas[i], self.linhas_inst[i]
        if w["vivo"].get():
            if not p.vst:
                w["vivo"].set(False)
                return messagebox.showinfo("VST ao vivo", "Escolha um VST para esta pista primeiro.")
            try:
                inst = self._instancia(i)
                self.synth.ligar_vst(p.canal, inst)
                self.vst_vivo[p.canal] = inst
                if self.saida_midi:
                    self.tocador.adicionar_saida(self._so_vst)
                self._msg(f"Pista {i + 1} tocando ao vivo pelo {VST.nome_curto(p.vst)} (experimental).")
            except Exception as e:
                w["vivo"].set(False)
                self._erro("VST ao vivo", e)
        else:
            self.synth.desligar_vst(p.canal)
            self.vst_vivo.pop(p.canal, None)

    def _procurar_plugins(self):
        achados = VST.procurar_plugins()
        top = tk.Toplevel(self.root)
        top.title("Plugins encontrados")
        top.configure(bg=COR["painel"])
        top.geometry("640x420")
        ttk.Label(top, text=f"{len(achados)} plugin(s) nas pastas padrão. Escolha e diga a pista:",
                  padding=8).pack(anchor="w")
        lb = tk.Listbox(top, bg=COR["branca"], fg=COR["texto"], selectbackground=COR["acento"])
        lb.pack(fill="both", expand=True, padx=8)
        for a in achados:
            lb.insert("end", a)
        bf = ttk.Frame(top, padding=8)
        bf.pack(fill="x")
        var = tk.IntVar(value=2)
        ttk.Label(bf, text="Pista:").pack(side="left")
        ttk.Spinbox(bf, from_=1, to=8, textvariable=var, width=4).pack(side="left", padx=4)

        def usar():
            s = lb.curselection()
            if s:
                self._usar_vst(int(var.get()) - 1, achados[s[0]])
                top.destroy()
        ttk.Button(bf, text="Usar nesta pista", style="Acao.TButton", command=usar).pack(side="left", padx=8)

    def _mapa_notas(self):
        i = self.var_pista.get() if self.ritmo.pistas[self.var_pista.get()].regra == AC.BYPASS else 1
        p = self.ritmo.pistas[i]
        top = tk.Toplevel(self.root)
        top.title(f"Mapa de notas — pista {i + 1}: {p.nome}")
        top.configure(bg=COR["painel"])
        ttk.Label(top, padding=8, style="Dica.TLabel",
                  text="Se a biblioteca do Kontakt usa outras notas para as peças, ajuste aqui (General MIDI → biblioteca).").pack(anchor="w")
        g = ttk.Frame(top, padding=8)
        g.pack()
        vars_ = {}
        for k, (n, rot) in enumerate(PECAS_BATERIA):
            ttk.Label(g, text=f"{rot} ({n})").grid(row=k % 11, column=(k // 11) * 2, sticky="w", padx=4, pady=1)
            v = tk.StringVar(value=str(p.nota_saida(n)))
            ttk.Entry(g, textvariable=v, width=5).grid(row=k % 11, column=(k // 11) * 2 + 1, padx=(0, 16))
            vars_[n] = v

        def ok():
            mapa = {}
            for n, v in vars_.items():
                try:
                    alvo = int(v.get())
                    if alvo != n and 0 <= alvo <= 127:
                        mapa[str(n)] = alvo
                except ValueError:
                    pass
            p.mapa = mapa
            self._marcar()
            top.destroy()
        ttk.Button(top, text="OK", style="Acao.TButton", command=ok).pack(pady=8)

    # ================================================================== ABA 4: TOCAR
    def _aba_tocar(self):
        f = ttk.Frame(self.abas, padding=12)
        self.abas.add(f, text="  4 · Tocar  ")
        esq = ttk.Frame(f)
        esq.pack(side="left", fill="y", padx=(0, 16))
        ttk.Label(esq, text="ACORDE", style="Dica.TLabel").pack(anchor="w")
        self.lbl_acorde = ttk.Label(esq, text="—", style="Acorde.TLabel", width=7)
        self.lbl_acorde.pack(anchor="w")
        self.lbl_secao = ttk.Label(esq, text="Parado", style="Grande.TLabel")
        self.lbl_secao.pack(anchor="w", pady=(6, 0))
        self.lbl_prox = ttk.Label(esq, text="", style="Dica.TLabel")
        self.lbl_prox.pack(anchor="w")
        self.cv_tempo = tk.Canvas(esq, width=220, height=44, bg=COR["painel"], highlightthickness=0)
        self.cv_tempo.pack(anchor="w", pady=10)
        self.lbl_bpm_vivo = ttk.Label(esq, text="", style="Grande.TLabel")
        self.lbl_bpm_vivo.pack(anchor="w")
        bb = ttk.Frame(esq)
        bb.pack(anchor="w", pady=4)
        ttk.Button(bb, text="−", width=3, command=lambda: self._bpm_delta(-1)).pack(side="left")
        ttk.Button(bb, text="+", width=3, command=lambda: self._bpm_delta(1)).pack(side="left", padx=4)
        ttk.Button(bb, text="Tap", width=5, command=self._tap).pack(side="left")

        ttk.Label(esq, text="Digite o acorde (Enter):", style="Dica.TLabel").pack(anchor="w", pady=(14, 0))
        self.var_ac = tk.StringVar()
        ea = ttk.Entry(esq, textvariable=self.var_ac, width=14, font=("Segoe UI", 14))
        ea.pack(anchor="w")
        ea.bind("<Return>", lambda e: self._acorde_digitado())
        self.ent_acorde = ea

        meio = ttk.Frame(f)
        meio.pack(side="left", fill="both", expand=True)
        ctrl = ttk.Frame(meio)
        ctrl.pack(fill="x")
        self.btn_play = ttk.Button(ctrl, text="▶  INICIAR  (espaço)", style="Iniciar.TButton", command=self._play)
        self.btn_play.pack(side="left", fill="x", expand=True)
        self.var_sync = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl, text="Sync Start (começa no acorde)", variable=self.var_sync,
                        command=self._sync).pack(side="left", padx=10)
        self.var_autofill = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl, text="Auto Fill", variable=self.var_autofill,
                        command=lambda: setattr(self.tocador, "auto_fill", self.var_autofill.get())).pack(side="left")
        self.var_gravar = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl, text="Gravar execução", variable=self.var_gravar).pack(side="left", padx=10)

        self.botoes_secao = {}
        grupos = [("INTRO", ["Intro A", "Intro B", "Intro C"]),
                  ("VARIAÇÃO", ["Var A", "Var B", "Var C", "Var D"]),
                  ("", ["Fill", "Break"]),
                  ("FINAL", ["Final A", "Final B", "Final C"])]
        gf = ttk.Frame(meio)
        gf.pack(fill="x", pady=14)
        col = 0
        teclas = {"Var A": "Z", "Var B": "X", "Var C": "C", "Var D": "V", "Fill": "F", "Break": "B",
                  "Intro A": "Q", "Final A": "E"}
        for titulo, nomes in grupos:
            lf = ttk.Labelframe(gf, text=titulo or "VIRADA", padding=6)
            lf.grid(row=col // 2, column=col % 2, padx=4, pady=3, sticky="nw")
            for k, n in enumerate(nomes):
                rot = n.replace("Var ", "").replace("Intro ", "").replace("Final ", "")
                if n in ("Fill", "Break"):
                    rot = n
                t = teclas.get(n)
                b = ttk.Button(lf, text=f"{rot}\n({t})" if t else f"{rot}\n ", style="Secao.TButton", width=6,
                               command=lambda n=n: self._secao(n))
                b.grid(row=0, column=k, padx=2)
                self.botoes_secao[n] = b
            col += 1

        lf = ttk.Labelframe(meio, text="ACORDES RÁPIDOS  (teclas 1–7 = graus do tom)", padding=8)
        lf.pack(fill="x", pady=4)
        topo = ttk.Frame(lf)
        topo.pack(fill="x")
        ttk.Label(topo, text="Tom:").pack(side="left")
        self.var_tom = tk.StringVar(value="C")
        cbt = ttk.Combobox(topo, textvariable=self.var_tom, values=AC.NOMES + [n + "m" for n in AC.NOMES],
                           width=5, state="readonly")
        cbt.pack(side="left", padx=4)
        cbt.bind("<<ComboboxSelected>>", lambda e: self._montar_rapidos())
        self.var_setimas = tk.BooleanVar(value=False)
        ttk.Checkbutton(topo, text="com sétimas", variable=self.var_setimas,
                        command=self._montar_rapidos).pack(side="left", padx=8)
        self.fr_rapidos = ttk.Frame(lf)
        self.fr_rapidos.pack(fill="x", pady=6)
        self._montar_rapidos()

        lf2 = ttk.Labelframe(meio, text="SEQUÊNCIA AUTOMÁTICA  (um acorde por compasso — para testar sem teclado)",
                             padding=8)
        lf2.pack(fill="x", pady=8)
        self.var_seq = tk.StringVar(value="C Am F G7")
        ttk.Entry(lf2, textvariable=self.var_seq, width=50).pack(side="left")
        self.var_seq_on = tk.BooleanVar(value=False)
        ttk.Checkbutton(lf2, text="Ligada", variable=self.var_seq_on, command=self._seq).pack(side="left", padx=8)

        ttk.Label(meio, style="Dica.TLabel", text=(
            "Teclado MIDI: a mão esquerda (abaixo do split) faz o acorde, como no teclado arranjador. "
            "Split:")).pack(anchor="w", pady=(10, 0))
        sf_ = ttk.Frame(meio)
        sf_.pack(anchor="w")
        self.var_split = tk.StringVar(value=AC.nome_nota(54))
        cbs = ttk.Combobox(sf_, textvariable=self.var_split, values=[AC.nome_nota(n) for n in range(36, 73)],
                           width=6, state="readonly")
        cbs.pack(side="left")
        cbs.bind("<<ComboboxSelected>>", lambda e: self._split())
        self.var_modo = tk.StringVar(value="Fingered")
        cbm = ttk.Combobox(sf_, textvariable=self.var_modo, values=["Fingered", "Single Finger", "Fingered On Bass"],
                           width=17, state="readonly")
        cbm.pack(side="left", padx=6)
        cbm.bind("<<ComboboxSelected>>", lambda e: setattr(self.mao, "modo", {
            "Single Finger": "single", "Fingered On Bass": "onbass"}.get(self.var_modo.get(), "fingered")))

    def _montar_rapidos(self):
        for w in self.fr_rapidos.winfo_children():
            w.destroy()
        tom = self.var_tom.get()
        menor = tom.endswith("m")
        raiz = AC.NOMES.index(tom.rstrip("m"))
        set7 = self.var_setimas.get()
        if menor:
            graus = [(0, "m", "m7"), (2, "dim", "m7b5"), (3, "", "maj7"), (5, "m", "m7"), (7, "", "7"),
                     (8, "", "maj7"), (10, "", "7")]
        else:
            graus = [(0, "", "maj7"), (2, "m", "m7"), (4, "m", "m7"), (5, "", "maj7"), (7, "", "7"),
                     (9, "m", "m7"), (11, "dim", "m7b5")]
        self.rapidos = []
        for k, (iv, tri, sete) in enumerate(graus):
            ac = AC.Acorde((raiz + iv) % 12, sete if set7 else tri)
            self.rapidos.append(ac)
            ttk.Button(self.fr_rapidos, text=f"{ac.nome}\n({k + 1})", width=7,
                       command=lambda a=ac: self._acorde(a)).pack(side="left", padx=2)

    def _acorde(self, ac):
        self.tocador.definir_acorde(ac)

    def _acorde_digitado(self):
        try:
            self._acorde(AC.parse_acorde(self.var_ac.get()))
            self.var_ac.set("")
        except ValueError as e:
            self._msg(str(e))

    def _play(self):
        if self.tocador.tocando or self.tocador.armado:
            self.tocador.parar()
            self.var_sync.set(False)
            self._fim_gravacao()
            return
        self.tocador.auto_fill = self.var_autofill.get()
        self.tocador.gravacao = [] if self.var_gravar.get() else None
        self._seq()
        if self.var_sync.get():
            self.tocador.armar_sync(True)
            self._msg("Sync Start armado: toque um acorde para começar.")
        else:
            self.tocador.iniciar()

    def _fim_gravacao(self):
        g = self.tocador.gravacao
        self.tocador.gravacao = None
        if g:
            c = filedialog.asksaveasfilename(defaultextension=".mid", initialfile=self.ritmo.nome + " - gravação.mid",
                                             filetypes=[("MIDI", "*.mid")])
            if c:
                EX.gravacao_para_midi(self.ritmo, g, c, self.tocador.bpm)
                self._msg(f"Gravação salva: {c}")

    def _sync(self):
        if not self.tocador.tocando:
            self.tocador.armar_sync(self.var_sync.get())

    def _secao(self, nome):
        self.tocador.pedir(nome)

    def _seq(self):
        if self.var_seq_on.get():
            try:
                acs = [AC.parse_acorde(a) for a in self.var_seq.get().split()]
                self.tocador.definir_sequencia(acs)
            except ValueError as e:
                self.var_seq_on.set(False)
                self._msg(str(e))
        else:
            self.tocador.definir_sequencia([])

    def _bpm_delta(self, d):
        self.var_bpm.set(round(self.ritmo.bpm + d))
        self._mudar_bpm()

    def _tap(self):
        agora = time.perf_counter()
        self._taps = [t for t in self._taps if agora - t < 2.5] + [agora]
        if len(self._taps) >= 3:
            inter = [b - a for a, b in zip(self._taps, self._taps[1:])]
            self.var_bpm.set(round(60 / (sum(inter) / len(inter))))
            self._mudar_bpm()

    def _split(self):
        n = self.var_split.get()
        self.mao.split = next(k for k in range(128) if AC.nome_nota(k) == n)

    def _atalhos(self):
        mapa = {"z": "Var A", "x": "Var B", "c": "Var C", "v": "Var D", "f": "Fill", "b": "Break",
                "q": "Intro A", "e": "Final A"}

        def tecla(ev):
            foco = self.root.focus_get()
            if isinstance(foco, (tk.Entry, ttk.Entry, ttk.Spinbox, ttk.Combobox, tk.Text)):
                return
            if self.abas.index("current") != 3:
                return
            k = ev.keysym.lower()
            if k == "space":
                self._play(); return "break"
            if k in mapa:
                self._secao(mapa[k])
            elif k.isdigit() and 1 <= int(k) <= 7:
                self._acorde(self.rapidos[int(k) - 1])
        self.root.bind_all("<Key>", tecla)

    # ------------------------------------------------------------------ atualização
    def _atualizar_tudo(self):
        self.cb_dest_pista["values"] = [f"{i + 1} · {p.nome}" for i, p in enumerate(self.ritmo.pistas)]
        for i, rb in enumerate(self.rb_pistas):
            rb.configure(text=f"{i + 1}. {self.ritmo.pistas[i].nome.split('(')[-1].rstrip(')')}")
        self._atualizar_lista_secoes()
        self.var_comp.set(self.ritmo.secoes[self._secao_sel()].compassos)
        self._carregar_editor()
        self._preencher_instrumentos()
        self._atualizar_titulo()

    def _loop_interface(self):
        try:
            e = self.tocador.estado()
            self.lbl_acorde.configure(text=e["acorde"])
            if e["tocando"]:
                self.lbl_secao.configure(text=f"{e['secao']}   compasso {e['compasso']}")
                self.lbl_prox.configure(text=f"próxima: {e['proxima']}" if e["proxima"] else "")
                self.btn_play.configure(text="■  PARAR  (espaço)", style="Parar.TButton")
            elif e["armado"]:
                self.lbl_secao.configure(text="Aguardando acorde…")
                self.btn_play.configure(text="■  DESARMAR", style="Parar.TButton")
            else:
                intro = f"   (com {e['intro']})" if e["intro"] else ""
                self.lbl_secao.configure(text=f"Parado — {e['var']}{intro}")
                self.lbl_prox.configure(text="")
                self.btn_play.configure(text="▶  INICIAR  (espaço)", style="Iniciar.TButton")
                if self.tocador.gravacao:
                    self._fim_gravacao()
            self.lbl_bpm_vivo.configure(text=f"{e['bpm']:g} BPM")
            cv = self.cv_tempo
            cv.delete("all")
            for k in range(4):
                ativo = e["tocando"] and e["tempo"] == k + 1
                cv.create_oval(6 + k * 52, 6, 38 + k * 52, 38, fill=COR["acento"] if ativo else COR["grade"],
                               outline="")
            for n, b in self.botoes_secao.items():
                if e["tocando"] and (e["secao"] == n or (n == "Fill" and (e["secao"] or "").startswith("Fill"))):
                    b.configure(style="SecaoAtiva.TButton")
                elif (e["tocando"] and e["proxima"] == n) or (not e["tocando"] and (n == e["var"] or n == e["intro"])):
                    b.configure(style="SecaoProx.TButton")
                else:
                    b.configure(style="Secao.TButton")
            for canal, erro in list(self.synth.erros_vst.items()):
                self.vst_vivo.pop(canal, None)
                self._msg(f"VST do canal {canal + 1} parou ao vivo ({erro}). Voltou ao som interno.")
                self.synth.erros_vst.pop(canal)
                self._preencher_instrumentos()
        except Exception:
            traceback.print_exc()
        self.root.after(50, self._loop_interface)

    # ================================================================== EXPORTAR
    def janela_exportar(self):
        top = tk.Toplevel(self.root)
        top.title("Exportar música")
        top.configure(bg=COR["painel"])
        top.geometry("640x520")
        ttk.Label(top, padding=(10, 8), style="Dica.TLabel", text=(
            "Escreva o roteiro: uma seção por linha, um acorde por compasso.\n"
            "Dois acordes no mesmo compasso: C,Am.  Seções: Intro A–C, Var A–D, Fill A–D, Break, Final A–C.")).pack(anchor="w")
        txt = tk.Text(top, height=14, bg=COR["branca"], fg=COR["texto"], insertbackground=COR["texto"],
                      font=("Consolas", 12))
        txt.pack(fill="both", expand=True, padx=10)
        txt.insert("1.0", "Intro A: C\nVar A: C Am F G7\nVar A: C Am Dm,G7 C\nFill B: G7\n"
                          "Var B: C Am F G7\nVar C: C Am F G7\nFill D: G7\nVar D: C Am F G7\nFinal A: C\n")
        bf = ttk.Frame(top, padding=10)
        bf.pack(fill="x")
        prog = ttk.Label(top, text="", padding=(10, 0, 10, 10))
        prog.pack(anchor="w")
        var_vst = tk.BooleanVar(value=True)

        def eventos():
            rot = EX.parse_roteiro(txt.get("1.0", "end"))
            return EX.gerar_eventos(self.ritmo, rot)

        def midi():
            try:
                ev, tot = eventos()
            except ValueError as e:
                return messagebox.showerror("Roteiro", str(e), parent=top)
            c = filedialog.asksaveasfilename(parent=top, defaultextension=".mid",
                                             initialfile=self.ritmo.nome + ".mid", filetypes=[("MIDI", "*.mid")])
            if c:
                EX.salvar_midi(self.ritmo, ev, c)
                prog.configure(text=f"MIDI salvo: {c}")

        def wav():
            try:
                ev, tot = eventos()
            except ValueError as e:
                return messagebox.showerror("Roteiro", str(e), parent=top)
            c = filedialog.asksaveasfilename(parent=top, defaultextension=".wav",
                                             initialfile=self.ritmo.nome + ".wav", filetypes=[("WAV", "*.wav")])
            if not c:
                return

            def p(frac, nome):
                self.root.after(0, lambda: prog.configure(text=f"Renderizando… {int(frac * 100)}%  {nome}"))

            def trab():
                try:
                    info = EX.renderizar(self.ritmo, ev, tot, c, usar_vst=var_vst.get(), progresso=p)
                    linhas = "\n".join(f"  {k}: {v}" for k, v in info["pistas"].items())
                    self.root.after(0, lambda: prog.configure(text=f"WAV salvo ({info['duracao_s']} s): {c}\n{linhas}"))
                except Exception as e:
                    self.root.after(0, lambda e=e: self._erro("Renderizar", e))
            threading.Thread(target=trab, daemon=True).start()

        ttk.Button(bf, text="Salvar MIDI…", style="Acao.TButton", command=midi).pack(side="left")
        ttk.Button(bf, text="Renderizar WAV…", style="Acao.TButton", command=wav).pack(side="left", padx=8)
        ttk.Checkbutton(bf, text="Usar os VSTs das pistas", variable=var_vst).pack(side="left")


def main():
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.2)
    except tk.TclError:
        pass
    ritmo = None
    if len(sys.argv) > 1 and sys.argv[1].endswith(".ritmo"):
        ritmo = Ritmo.abrir(sys.argv[1])
    App(root, ritmo)
    root.mainloop()


if __name__ == "__main__":
    main()
