"""Testes dos estilos Yamaha (.sty): importar estilo real, exportar e reimportar (ida e volta)."""
import os
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from nucleo import acordes as AC                                           # noqa: E402
from nucleo.estilo_yamaha import ErroEstilo, escrever_sty, ler_sty         # noqa: E402
from nucleo.ritmo import (Camada, Nota, PPQ, SEMI, ritmo_demo, ticks_do_compasso)  # noqa: E402
from nucleo.tocador import Tocador                                         # noqa: E402

TMP = tempfile.mkdtemp(prefix="estudio_sty_")
STY_REAL = os.path.join(AQUI, "dados", "PianoBallad.sty")


def tocar(ritmo, roteiro):
    """roteiro: lista de (compasso, comando, valor). Devolve lista de notas (tick, on/off, canal, nota)."""
    t = Tocador(ritmo)
    t._thread_auto = False
    log = []
    t.adicionar_saida(lambda m: log.append((t.pos, m.type, m.channel, m.note))
                      if m.type in ("note_on", "note_off") else None)
    tc = ritmo.ticks_compasso
    for comp, cmd, v in roteiro:
        t.avancar(comp * tc)
        if cmd == "acorde":
            t.definir_acorde(AC.parse_acorde(v))
        elif cmd == "iniciar":
            t.iniciar(com_thread=False)
        elif cmd == "pedir":
            t.pedir(v)
        elif cmd == "parar":
            t.parar()
    return log, t


ROTEIRO = [(0, "acorde", "C"), (0, "iniciar", ""), (1, "acorde", "Am"), (2, "acorde", "F"), (2.5, "acorde", "G7"),
           (3, "pedir", "Var B"), (4, "acorde", "Dm7"), (5, "acorde", "E7"), (6, "pedir", "Var C"),
           (7, "acorde", "Bbmaj7"), (8, "acorde", "C9"), (9, "pedir", "Var D"), (10, "acorde", "F#m7b5"),
           (12, "pedir", "Final A"), (20, "parar", "")]


def sem_notas_presas(log):
    abertas = {}
    for _t, tipo, ch, n in log:
        k = (ch, n)
        abertas[k] = abertas.get(k, 0) + (1 if tipo == "note_on" else -1)
    return all(v <= 0 for v in abertas.values())


class TesteEstiloReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = ler_sty(STY_REAL)

    def test_cabecalho(self):
        self.assertEqual(self.r.nome, "PianoBallad")
        self.assertEqual(self.r.bpm, 85.0)
        self.assertEqual(self.r.compasso, (4, 4))
        for s in ["Intro A", "Var A", "Var B", "Var C", "Var D", "Fill A", "Break", "Final A"]:
            self.assertFalse(self.r.secoes[s].vazia, s)
        self.assertEqual(self.r.secoes["Var A"].compassos, 2)
        self.assertEqual(self.r.pistas[2].regra, AC.FUNDAMENTAL)          # baixo
        self.assertEqual(self.r.pistas[2].programa, 33)                    # timbre da seção SInt

    def test_toca_sem_notas_presas(self):
        roteiro = [(c / 1, cmd, v) for c, cmd, v in ROTEIRO]
        log, t = tocar(self.r, roteiro)
        self.assertGreater(sum(1 for e in log if e[1] == "note_on"), 300)
        self.assertTrue(sem_notas_presas(log))
        self.assertFalse(t.tocando)

    def test_camadas_respeitam_o_acorde(self):
        """Neste estilo, as camadas extras (pad e guitarra 'Root') só entram em acordes com sétima."""
        sec = self.r.secoes["Var B"]
        extras = [c for c in sec.camadas if "" in c.tipos_mudos]
        self.assertEqual(sorted(c.nome for c in extras), ["Root EGi", "pad51"])
        for nome, toca in [("C", False), ("Am", False), ("G7", True), ("Dm7", True), ("C9", True)]:
            ac = AC.parse_acorde(nome)
            for cam in extras:
                self.assertEqual(sec.camada_toca(cam, ac), toca, (nome, cam.nome))

    def test_nunca_duas_camadas_da_mesma_pista_sem_filtro_dobrando(self):
        """Para qualquer acorde, cada pista tem pelo menos uma camada tocando (nada fica mudo)."""
        for nome, sec in self.r.secoes.items():
            pistas = {c.pista for c in sec.camadas}
            for raiz in range(12):
                for tipo in AC.TIPOS:
                    ac = AC.Acorde(raiz, tipo)
                    for p in pistas:
                        tocam = [c for c in sec.camadas if c.pista == p and sec.camada_toca(c, ac)]
                        self.assertTrue(tocam or sec.pistas.get(p), (nome, p, ac.nome))


class TesteIdaEVolta(unittest.TestCase):
    def comparar(self, original, roteiro):
        caminho = os.path.join(TMP, "ida_volta.sty")
        escrever_sty(original, caminho)
        reimportado = ler_sty(caminho)
        a, _ = tocar(original, roteiro)
        b, _ = tocar(reimportado, roteiro)
        self.assertEqual(len(a), len(b))
        self.assertEqual(sorted(a), sorted(b))
        return reimportado

    def test_demo_4_por_4(self):
        r = ritmo_demo()
        r2 = self.comparar(r, ROTEIRO)
        self.assertEqual(r2.bpm, r.bpm)
        for nome, s in r.secoes.items():
            self.assertEqual(r2.secoes[nome].compassos, s.compassos, nome)

    def test_camadas_fonte_menor_high_key_e_3_por_4(self):
        r = ritmo_demo("Valsa", 96)
        r.definir_compasso(3, 4)
        tc = ticks_do_compasso(3, 4)
        for s in r.secoes.values():                     # recorta tudo para 3/4
            for i in list(s.pistas):
                s.pistas[i] = [n for n in s.pistas[i] if n.ini % 1920 < tc and n.ini < s.compassos * 1920]
                s.pistas[i] = [Nota(n.ini // 1920 * tc + n.ini % 1920, min(n.dur, tc), n.nota, n.vel)
                               for n in s.pistas[i]]
        var = r.secoes["Var A"]
        var.pistas[2] = []                              # baixo vira duas camadas: maior e menor
        var.camadas = [
            Camada(2, [Nota(0, PPQ, 36, 110), Nota(PPQ, PPQ, 43, 90), Nota(2 * PPQ, PPQ, 40, 90)], AC.FUNDAMENTAL,
                   (28, 52), (0, "maj7"), 6, ["m", "m7", "m6", "m7b5", "dim", "dim7", "mmaj7", "m9"], [], "BassMaj"),
            Camada(2, [Nota(0, PPQ, 36, 110), Nota(PPQ, PPQ, 43, 90), Nota(2 * PPQ, PPQ, 39, 90)], AC.FUNDAMENTAL,
                   (28, 52), (0, "m7"), 4, ["", "maj7", "6", "7", "9", "add9", "aug", "sus4", "sus2", "7sus4"], [],
                   "BassMin"),
            Camada(5, [Nota(0, tc - 10, n, 70) for n in (60, 63, 67, 70)], AC.ACORDE, (50, 79), (0, "m7"), 6,
                   [], [1, 6], "PadM7"),
        ]
        roteiro = [(0, "acorde", "C"), (0, "iniciar", ""), (1, "acorde", "Am"), (2, "acorde", "F"),
                   (3, "acorde", "Em7"), (4, "acorde", "G7"), (5, "acorde", "C#m"), (6, "acorde", "F#7"),
                   (7, "acorde", "B"), (8, "pedir", "Var B"), (10, "pedir", "Final A"), (16, "parar", "")]
        r2 = self.comparar(r, roteiro)
        self.assertEqual(r2.compasso, (3, 4))
        self.assertEqual(len(r2.secoes["Var A"].camadas), 3)
        log, _ = tocar(r2, roteiro)
        # em Am (compasso 1) o baixo toca a camada menor: terceira nota = Dó (b3 de Lá)
        baixo = [n for tick, tipo, ch, n in log if tipo == "note_on" and ch == 10 and tc <= tick < 2 * tc]
        self.assertEqual([AC.NOMES[n % 12] for n in baixo], ["A", "E", "C"])
        baixo_c = [n for tick, tipo, ch, n in log if tipo == "note_on" and ch == 10 and tick < tc]
        self.assertEqual([AC.NOMES[n % 12] for n in baixo_c], ["C", "G", "E"])
        # o pad não toca com fundamental C# nem F# (raízes mudas)
        pad = [tick for tick, tipo, ch, n in log if tipo == "note_on" and ch == 13 and 5 * tc <= tick < 7 * tc]
        self.assertEqual(pad, [])

    def test_arquivo_invalido(self):
        c = os.path.join(TMP, "x.sty")
        with open(c, "wb") as f:
            f.write(b"KORF....")
        with self.assertRaises(ErroEstilo):
            ler_sty(c)


class TesteKorg(unittest.TestCase):
    def test_nomes_de_secao(self):
        from nucleo.estilo_yamaha import normalizar_secao as N
        casos = {"Main A": "Var A", "Variation 2": "Var B", "Var3": "Var C", "VARIATION4": "Var D",
                 "Intro 1": "Intro A", "Fill In BB": "Fill B", "Fill 3": "Fill C", "Fill In BA": "Break",
                 "Break": "Break", "Ending 1": "Final A", "Ending C": "Final C", "SInt": None, "SFF1": None,
                 "Fill In AB": None, "Count In": None}
        for m, esperado in casos.items():
            self.assertEqual(N(m), esperado, m)

    def test_estilo_korg_em_midi(self):
        """Estilo Korg exportado como MIDI (sem CASM, marcadores Korg) importa com regras padrão."""
        import mido
        mid = mido.MidiFile(type=0, ticks_per_beat=96)
        t = mido.MidiTrack(); mid.tracks.append(t)
        t.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(110), time=0))
        for nome, base in (("Variation 1", 36), ("Variation 2", 38), ("Fill 1", 40), ("Ending 1", 41)):
            t.append(mido.MetaMessage("marker", text=nome, time=0))
            for k in range(4):
                t.append(mido.Message("note_on", channel=9, note=base, velocity=100, time=0))
                t.append(mido.Message("note_on", channel=10, note=36 + k % 2 * 7, velocity=90, time=0))
                t.append(mido.Message("note_off", channel=9, note=base, time=48))
                t.append(mido.Message("note_off", channel=10, note=36 + k % 2 * 7, time=48))
        t.append(mido.MetaMessage("end_of_track", time=0))
        c = os.path.join(TMP, "BANK_KORG_MIDI.STY")
        mid.save(c)
        r = ler_sty(c)
        self.assertEqual(r.bpm, 110.0)
        self.assertEqual(len(r.secoes["Var A"].pistas[1]), 4)
        self.assertEqual(len(r.secoes["Var B"].pistas[2]), 4)      # canal 11 = baixo
        self.assertFalse(r.secoes["Fill A"].vazia)
        self.assertFalse(r.secoes["Final A"].vazia)
        log, _ = tocar(r, [(0, "acorde", "G"), (0, "iniciar", ""), (1, "pedir", "Var B"), (3, "pedir", "Final A"),
                           (8, "parar", "")])
        self.assertTrue(sem_notas_presas(log))
        baixo = [n for _t, tipo, ch, n in log if tipo == "note_on" and ch == 10]
        self.assertTrue(baixo and all(AC.NOMES[n % 12] in ("G", "D") for n in baixo))   # transposto para G

    def test_banco_korg_binario(self):
        from nucleo.estilo_korg import identificar, relatorio
        falso = b"KORF\x00\x00\x01\x00" + b"STYLE BANK " + b"OC31" + bytes(range(200)) + b"OC31" + b"\x00" * 50
        c = os.path.join(TMP, "USER01.STY")
        with open(c, "wb") as f:
            f.write(falso)
        info = identificar(c)
        self.assertEqual(info["tipo"], "korg_sty_banco")
        self.assertEqual(info["blocos_oc31"], 2)
        with self.assertRaises(ErroEstilo) as ctx:
            ler_sty(c)
        self.assertIn("Korg", str(ctx.exception))
        self.assertIn("OC31", relatorio(c))


if __name__ == "__main__":
    unittest.main(verbosity=2)
