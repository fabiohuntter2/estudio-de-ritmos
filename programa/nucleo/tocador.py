"""Tocador em tempo real: executa o ritmo como um teclado arranjador.

- Seções: Intro → Variação (em loop) → Virada → Variação → Final.
- Troca de variação no compasso seguinte; virada e break entram na hora e vão até o fim do compasso.
- Sync Start: arma e começa quando chega o primeiro acorde.
- Troca de acorde: cada pista reage pela sua regra (acorde = retoca as vozes, baixo = corta,
  melodia = deixa terminar).

O núcleo (`avancar`) é determinístico e testável; a thread só converte relógio em ticks.
"""
from __future__ import annotations

import threading
import time

import mido

from .acordes import ACORDE, FUNDAMENTAL, BYPASS, ACORDE_PADRAO, Acorde, transpor_nota
from .ritmo import PPQ, SEMI, Ritmo


def letra(secao: str) -> str:
    return secao.split()[-1] if secao else "A"


class Tocador:
    def __init__(self, ritmo: Ritmo, saida=None):
        self.ritmo = ritmo
        self.saidas = [saida] if saida else []
        self.lock = threading.RLock()
        self.tocando = False
        self.armado = False                    # Sync Start
        self.auto_fill = True
        self.acorde: Acorde | None = None
        self.var_atual = "Var A"
        self.intro_escolhida: str | None = None
        self.secao: str | None = None
        self.inicio_secao = 0
        self.fila: list[str] = []
        self.troca_no_compasso = False
        self.pos = 0
        self.soando: dict = {}                 # (canal, nota_saida) -> [off_tick, pista, nota_fonte, vel]
        self._eventos: list = []
        self._ev_idx = 0
        self.gravacao: list | None = None
        self._thread = None
        self._rodando = False
        self.bpm = ritmo.bpm
        self._reancorar = True
        self.sequencia: list = []               # acordes automáticos, um por compasso
        self._seq_idx = 0

    def definir_sequencia(self, acordes: list):
        """Lista de Acorde (um por compasso). Lista vazia = desliga."""
        with self.lock:
            self.sequencia = list(acordes)
            self._seq_idx = 0

    def _proximo_da_sequencia(self):
        if self.sequencia:
            ac = self.sequencia[self._seq_idx % len(self.sequencia)]
            self._seq_idx += 1
            if ac != self.acorde:
                self.acorde = ac
                self._retocar()

    # ------------------------------------------------------------------ saída
    def adicionar_saida(self, fn):
        with self.lock:
            if fn not in self.saidas:
                self.saidas.append(fn)

    def remover_saida(self, fn):
        with self.lock:
            if fn in self.saidas:
                self.saidas.remove(fn)

    def _enviar(self, msg: mido.Message):
        if self.gravacao is not None:
            self.gravacao.append((self.pos, msg))
        for s in list(self.saidas):
            try:
                s(msg)
            except Exception as e:                       # uma saída com problema não para as outras
                print("Erro na saída MIDI:", e)

    # ------------------------------------------------------------------ estado (para a interface)
    def estado(self) -> dict:
        with self.lock:
            rel = self.pos - self.inicio_secao
            return {"tocando": self.tocando, "armado": self.armado, "secao": self.secao,
                    "var": self.var_atual, "intro": self.intro_escolhida,
                    "proxima": self.fila[0] if self.fila else None,
                    "compasso": rel // self._tc + 1 if self.tocando else 0,
                    "tempo": (rel % self._tc) // PPQ + 1 if self.tocando else 0,
                    "acorde": self.acorde.nome if self.acorde else "—", "bpm": self.bpm}

    # ------------------------------------------------------------------ comandos
    def _vazia(self, nome):
        return self.ritmo.secoes[nome].vazia

    def iniciar(self, com_thread=True):
        with self.lock:
            if self.tocando:
                return
            self.armado = False
            self.pos = 0
            self.fila = []
            primeira = self.var_atual
            if self.intro_escolhida and not self._vazia(self.intro_escolhida):
                primeira = self.intro_escolhida
                self.fila = [self.var_atual]
            for p in self.ritmo.pistas:            # timbres e volumes para quem usa saída MIDI
                if p.programa is not None:
                    self._enviar(mido.Message("program_change", channel=p.canal, program=p.programa))
                self._enviar(mido.Message("control_change", channel=p.canal, control=7,
                                          value=int(p.volume * 127)))
            self._seq_idx = 0
            self._proximo_da_sequencia()
            self._entrar(primeira, 0)
            self.troca_no_compasso = False
            self.tocando = True
            self.intro_escolhida = None
        if com_thread:
            self._iniciar_thread()

    def parar(self):
        with self.lock:
            self.tocando = False
            self.armado = False
            self._rodando = False
            self._todas_off()
            self.secao = None
            self.fila = []
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)
        self._thread = None

    def armar_sync(self, ligado=True):
        with self.lock:
            if not self.tocando:
                self.armado = ligado

    def definir_bpm(self, bpm: float):
        with self.lock:
            self.bpm = max(30.0, min(300.0, float(bpm)))
            self._reancorar = True

    def pedir(self, nome: str):
        """Botão de seção apertado (Intro X, Var X, Fill, Break, Final X)."""
        with self.lock:
            if not self.tocando:
                if nome.startswith("Var"):
                    self.var_atual = nome
                elif nome.startswith("Intro"):
                    self.intro_escolhida = None if self.intro_escolhida == nome else nome
                return
            atual = self.secao or ""
            if nome.startswith("Var"):
                mesma = nome == self.var_atual
                self.var_atual = nome
                if atual.startswith(("Fill", "Break", "Intro")):
                    self.fila = [s for s in self.fila if not s.startswith("Var")] + [nome]
                    return
                fill = f"Fill {letra(nome)}"
                if self.auto_fill and not self._vazia(fill):
                    self._virada_agora([fill, nome])
                elif not mesma:
                    self.fila = [nome]
                    self.troca_no_compasso = True
            elif nome == "Fill" or nome.startswith("Fill"):
                fill = nome if nome != "Fill" else f"Fill {letra(self.var_atual)}"
                if not self._vazia(fill):
                    self._virada_agora([fill, self.var_atual])
            elif nome == "Break":
                if not self._vazia("Break"):
                    self._virada_agora(["Break", self.var_atual])
            elif nome.startswith("Final"):
                if not self._vazia(nome):
                    self.fila = [nome]
                    self.troca_no_compasso = True
            elif nome.startswith("Intro"):
                if not self._vazia(nome):
                    self.fila = [nome, self.var_atual]
                    self.troca_no_compasso = True

    def _virada_agora(self, fila):
        """Virada/break: entra já, alinhada ao compasso atual (toca do ponto atual até o fim)."""
        rel = self.pos - self.inicio_secao
        tc = self._tc
        inicio_compasso = self.inicio_secao + (rel // tc) * tc
        if self.pos - inicio_compasso > tc - PPQ // 2:      # apertou no finalzinho: próximo compasso
            self.fila = fila
            self.troca_no_compasso = True
            return
        self.fila = fila[1:]
        self.troca_no_compasso = False
        self._entrar(fila[0], inicio_compasso, a_partir=self.pos)

    def definir_acorde(self, ac: Acorde | None):
        if ac is None:
            return
        iniciar = False
        with self.lock:
            mudou = ac != self.acorde
            self.acorde = ac
            if self.armado and not self.tocando:
                iniciar = True
            elif self.tocando and mudou:
                self._retocar()
        if iniciar:
            self.iniciar(com_thread=self._thread_auto)

    _thread_auto = True

    @property
    def _tc(self) -> int:
        return self.ritmo.ticks_compasso

    # ------------------------------------------------------------------ núcleo
    def _entrar(self, nome: str, inicio: int, a_partir: int | None = None):
        self.secao = nome
        self.inicio_secao = inicio
        sec = self.ritmo.secoes[nome]
        ev = []
        for i, notas in sec.pistas.items():
            for n in notas:
                if n.ini < sec.ticks:
                    ev.append((inicio + n.ini, i, n, None, sec))
        for cam in sec.camadas:
            for n in cam.notas:
                if n.ini < sec.ticks:
                    ev.append((inicio + n.ini, cam.pista, n, cam, sec))
        ev.sort(key=lambda e: (e[0], e[1], e[2].nota))
        self._eventos = ev
        a_partir = inicio if a_partir is None else a_partir
        self._ev_idx = 0
        while self._ev_idx < len(ev) and ev[self._ev_idx][0] < a_partir:
            self._ev_idx += 1

    def _nota_saida(self, pista: int, nota_fonte: int, cam=None) -> int:
        cfg = self.ritmo.pistas[pista]
        ac = self.acorde or ACORDE_PADRAO
        if cam is None:
            n = transpor_nota(nota_fonte, cfg.regra, tuple(cfg.faixa), ac)
        else:
            n = transpor_nota(nota_fonte, cam.regra, tuple(cam.faixa), ac, cam.acorde_fonte(), cam.tecla_alta)
        return max(0, min(127, cfg.nota_saida(n)))

    def _on(self, pista: int, nota_fonte: int, vel: int, off: int, cam=None, sec=None):
        cfg = self.ritmo.pistas[pista]
        if cfg.mudo:
            return
        if cam is not None and not sec.camada_toca(cam, self.acorde or ACORDE_PADRAO):
            return                                      # camada de outro tipo de acorde (ex.: só menores)
        n = self._nota_saida(pista, nota_fonte, cam)
        chave = (cfg.canal, n)
        if chave in self.soando:
            self._enviar(mido.Message("note_off", channel=cfg.canal, note=n, velocity=0))
        self._enviar(mido.Message("note_on", channel=cfg.canal, note=n, velocity=max(1, min(127, vel))))
        self.soando[chave] = [off, pista, nota_fonte, vel, cam, sec]

    def _off(self, chave):
        canal, n = chave
        self._enviar(mido.Message("note_off", channel=canal, note=n, velocity=0))
        self.soando.pop(chave, None)

    def _todas_off(self):
        for chave in list(self.soando):
            self._off(chave)
        for canal in sorted({p.canal for p in self.ritmo.pistas}):
            self._enviar(mido.Message("control_change", channel=canal, control=123, value=0))

    def _retocar(self):
        """Acorde mudou com notas soando."""
        ac = self.acorde or ACORDE_PADRAO
        for chave, (off, pista, fonte, vel, cam, sec) in list(self.soando.items()):
            if cam is not None and not sec.camada_toca(cam, ac):
                self._off(chave)                         # camada deixou de valer para este acorde
                continue
            regra = cam.regra if cam is not None else self.ritmo.pistas[pista].regra
            if regra == FUNDAMENTAL:
                self._off(chave)
            elif regra == ACORDE:
                self._off(chave)
                if off - self.pos > SEMI // 2:
                    self._on(pista, fonte, max(1, int(vel * 0.85)), off, cam, sec)
            # MELODIA e BYPASS: deixa terminar

    def _fronteira(self, fim_secao: bool):
        """Chamado em cada início de compasso (e no fim da seção)."""
        self._proximo_da_sequencia()
        if self.fila and (fim_secao or self.troca_no_compasso):
            prox = self.fila.pop(0)
            while self._vazia(prox) and self.fila:
                prox = self.fila.pop(0)
            if self._vazia(prox):
                prox = self.var_atual
            self.troca_no_compasso = False
            self._entrar(prox, self.pos)
        elif fim_secao:
            if self.secao and self.secao.startswith("Final"):
                self.tocando = False
                self._rodando = False
                self._todas_off()
                self.secao = None
                return
            self._entrar(self.secao, self.pos)

    def avancar(self, ate: int):
        """Processa todos os eventos com tick em [pos, ate)."""
        with self.lock:
            while self.tocando and self.pos < ate:
                sec = self.ritmo.secoes[self.secao]
                fim_secao = self.inicio_secao + sec.ticks
                rel = self.pos - self.inicio_secao
                prox_compasso = self.inicio_secao + (rel // self._tc + 1) * self._tc
                limite = min(ate, fim_secao, prox_compasso)

                # note-off e note-on em ordem de tempo (off antes de on no mesmo tick)
                while True:
                    off_tick, off_chave = None, None
                    for chave, (off, *_r) in self.soando.items():
                        if off < limite and (off_tick is None or off < off_tick):
                            off_tick, off_chave = off, chave
                    on_tick = (self._eventos[self._ev_idx][0]
                               if self._ev_idx < len(self._eventos) else None)
                    if on_tick is not None and on_tick >= limite:
                        on_tick = None
                    if off_tick is None and on_tick is None:
                        break
                    if on_tick is None or (off_tick is not None and off_tick <= on_tick):
                        self.pos = max(self.pos, off_tick)
                        self._off(off_chave)
                    else:
                        t, pista, n, cam, sec = self._eventos[self._ev_idx]
                        self._ev_idx += 1
                        self.pos = max(self.pos, t)
                        self._on(pista, n.nota, n.vel, t + n.dur, cam, sec)

                self.pos = limite
                if self.pos in (prox_compasso, fim_secao):
                    self._fronteira(self.pos >= fim_secao)

    # ------------------------------------------------------------------ relógio
    def _iniciar_thread(self):
        self._rodando = True
        self._reancorar = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="tocador")
        self._thread.start()

    def _loop(self):
        t0, tick0 = time.perf_counter(), 0
        while self._rodando:
            with self.lock:
                agora = time.perf_counter()
                if self._reancorar:
                    t0, tick0 = agora, self.pos
                    self._reancorar = False
                alvo = tick0 + (agora - t0) * self.bpm / 60 * PPQ
                self.avancar(int(alvo) + 1)
                if not self.tocando:
                    break
            time.sleep(0.001)
        self._rodando = False


class MaoEsquerda:
    """Reconhece o acorde nas teclas abaixo do ponto de split (com memória).
    modo: 'fingered' (inversão = posição fundamental), 'onbass' (nota mais grave vai para o baixo), 'single'."""

    def __init__(self, tocador: Tocador, split: int = 54, modo: str = "fingered", direita=None):
        self.tocador = tocador
        self.split = split
        self.modo = modo
        self.direita = direita          # função para notas da mão direita (ex.: tocar piano)
        self.presas: set[int] = set()

    def receber(self, msg: mido.Message):
        from .acordes import reconhecer
        if msg.type not in ("note_on", "note_off"):
            return
        liga = msg.type == "note_on" and msg.velocity > 0
        if msg.note >= self.split:
            if self.direita:
                self.direita(msg.copy(channel=0))
            return
        if liga:
            self.presas.add(msg.note)
            ac = reconhecer(sorted(self.presas), "single" if self.modo == "single" else "fingered")
            if ac:
                if self.modo == "fingered" and ac.baixo is not None:   # inversão toca como fundamental
                    ac = Acorde(ac.fundamental, ac.tipo)
                self.tocador.definir_acorde(ac)
        else:
            self.presas.discard(msg.note)
