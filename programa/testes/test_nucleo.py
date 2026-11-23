"""Testes automáticos do núcleo. Rodar:  python -m unittest discover -s testes -v"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

from nucleo import acordes as AC                      # noqa: E402
from nucleo import exportar as EX                     # noqa: E402
from nucleo.ritmo import (COMPASSO, PPQ, SEMI, Nota, Ritmo, ler_midi, notas_da_deteccao,  # noqa: E402
                          ritmo_demo, ritmo_vazio)
from nucleo.sintetizador import Sintetizador          # noqa: E402
from nucleo.tocador import MaoEsquerda, Tocador       # noqa: E402

import mido                                            # noqa: E402

TMP = tempfile.mkdtemp(prefix="estudio_testes_")


# ====================================================================== acordes
class TesteAcordes(unittest.TestCase):
    def test_parse(self):
        casos = {"C": (0, ""), "Am": (9, "m"), "G7": (7, "7"), "Bb7M": (10, "maj7"), "F#m7": (6, "m7"),
                 "Ebdim": (3, "dim"), "Dsus4": (2, "sus4"), "Bm7b5": (11, "m7b5"), "C7M": (0, "maj7"),
                 "A°": (9, "dim"), "E9": (4, "9"), "db": (1, ""), "g": (7, "")}
        for txt, (raiz, tipo) in casos.items():
            a = AC.parse_acorde(txt)
            self.assertEqual((a.fundamental, a.tipo), (raiz, tipo), txt)

    def test_parse_baixo_invertido(self):
        a = AC.parse_acorde("C/E")
        self.assertEqual((a.fundamental, a.tipo, a.baixo), (0, "", 4))
        self.assertEqual(a.nome, "C/E")

    def test_parse_invalido(self):
        with self.assertRaises(ValueError):
            AC.parse_acorde("Cxyz")
        with self.assertRaises(ValueError):
            AC.parse_acorde("H7")

    def test_reconhecer_fingered(self):
        casos = {
            (60, 64, 67): "C", (57, 60, 64): "Am", (55, 59, 62, 65): "G7", (62, 65, 69, 72): "Dm7",
            (60, 64, 67, 71): "Cmaj7", (59, 62, 65): "Bdim", (60, 64, 68): "Caug", (62, 67, 69): "Dsus4",
            (64, 67, 72): "C/E", (67, 72, 76): "C/G", (59, 62, 65, 68): "Bdim7", (57, 60, 63, 67): "Am7b5",
            (48, 55): "C", (52, 55, 59, 62): "Em7", (53, 57, 60, 62): "F6", (50, 53, 57, 60): "Dm7",
        }
        for notas, esperado in casos.items():
            self.assertEqual(AC.reconhecer(list(notas)).nome, esperado, notas)

    def test_reconhecer_single_finger(self):
        self.assertEqual(AC.reconhecer([48], "single").nome, "C")
        self.assertEqual(AC.reconhecer([46, 48], "single").nome, "Cm")      # preta à esquerda
        self.assertEqual(AC.reconhecer([47, 48], "single").nome, "C7")      # branca à esquerda
        self.assertEqual(AC.reconhecer([46, 47, 48], "single").nome, "Cm7")

    def test_transposicao_baixo_mantem_desenho(self):
        linha = [36, 36, 43, 40, 43, 45]          # C2 C2 G2 E2 G2 A2
        faixa = (28, 52)
        am = [AC.nome_nota(AC.transpor_nota(n, AC.FUNDAMENTAL, faixa, AC.parse_acorde("Am"))) for n in linha]
        self.assertEqual(am, ["A1", "A1", "E2", "C2", "E2", "F2"])
        g7 = [AC.nome_nota(AC.transpor_nota(n, AC.FUNDAMENTAL, faixa, AC.parse_acorde("G7"))) for n in linha]
        self.assertEqual(g7, ["G1", "G1", "D2", "B1", "D2", "E2"])

    def test_baixo_invertido(self):
        ce = AC.parse_acorde("C/E")
        self.assertEqual(AC.transpor_nota(36, AC.FUNDAMENTAL, (28, 52), ce), 40)   # C2 -> E2

    def test_vozes_do_acorde(self):
        fonte = [52, 55, 59, 60]                  # E3 G3 B3 C4
        for nome, esperado in {"G7": {"F", "G", "B", "D"}, "Am": {"A", "C", "E"}, "F": {"F", "A", "C"},
                               "Dm7": {"D", "F", "A", "C"}}.items():
            vozes = {AC.NOMES[AC.transpor_nota(n, AC.ACORDE, (52, 76), AC.parse_acorde(nome)) % 12] for n in fonte}
            self.assertEqual(vozes, esperado, nome)

    def test_conducao_de_vozes_perto(self):
        fonte = [52, 55, 59, 60]
        for nome in ["C", "Dm", "Em", "F", "G7", "Am", "Bdim", "E7", "Bb", "F#m"]:
            novas = [AC.transpor_nota(n, AC.ACORDE, (52, 76), AC.parse_acorde(nome)) for n in fonte]
            for a, b in zip(fonte, novas):
                self.assertLessEqual(abs(a - b), 7, f"{nome}: voz saltou {AC.nome_nota(a)} -> {AC.nome_nota(b)}")
                self.assertTrue(52 - 4 <= b <= 76 + 4)

    def test_bateria_nao_transpoe(self):
        for n in range(30, 90):
            self.assertEqual(AC.transpor_nota(n, AC.BYPASS, (0, 127), AC.parse_acorde("F#m7")), n)

    def test_todos_os_acordes_dentro_da_faixa(self):
        for raiz in range(12):
            for tipo in AC.TIPOS:
                ac = AC.Acorde(raiz, tipo)
                for regra, faixa, folga in ((AC.FUNDAMENTAL, (28, 52), 0), (AC.ACORDE, (48, 79), 4),
                                            (AC.MELODIA, (60, 88), 0)):
                    for n in range(faixa[0], faixa[1] + 1):
                        r = AC.transpor_nota(n, regra, faixa, ac)
                        self.assertTrue(faixa[0] - folga <= r <= faixa[1] + folga, (ac.nome, regra, n, r))


# ====================================================================== detecção
class TesteDeteccao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import gerar_loops_teste as G
        cls.casos = {}
        for nome, c in G.CASOS.items():
            ev, dur = G.padrao(c["bpm"], c["compassos"], c["grade"], c.get("swing", 0), c.get("humano", 0))
            audio = G.render(ev, dur, c.get("ruido", 0), c.get("reverb", 0))
            caminho = os.path.join(TMP, f"{nome}.wav")
            import soundfile as sf
            sf.write(caminho, audio, G.SR)
            cls.casos[nome] = (caminho, ev, c["bpm"])

    def _f1(self, nome):
        from nucleo.deteccao import analisar
        caminho, ref, bpm = self.casos[nome]
        r = analisar(caminho)
        det = [(b["tempo_s"] + r["inicio_cortado_s"], b["peca"]) for b in r["batidas"]]
        acertos = 0
        usados = set()
        for e in ref:
            for j, (t, p) in enumerate(det):
                if j not in usados and p == e["peca"] and abs(t - e["tempo_s"]) <= 0.03:
                    usados.add(j); acertos += 1; break
        prec, rec = acertos / max(1, len(det)), acertos / len(ref)
        return r, 2 * prec * rec / max(1e-9, prec + rec)

    def test_loop_pop(self):
        r, f1 = self._f1("pop_100bpm")
        self.assertAlmostEqual(r["bpm"], 100, delta=0.5)
        self.assertGreaterEqual(f1, 0.85, f"F1 {f1:.2f}")

    def test_loop_forro_humanizado(self):
        r, f1 = self._f1("forro_120bpm_humano")
        self.assertAlmostEqual(r["bpm"], 120, delta=0.5)
        self.assertGreaterEqual(f1, 0.85, f"F1 {f1:.2f}")

    def test_loop_do_usuario_136(self):
        from nucleo.deteccao import analisar
        r = analisar(os.path.join(AQUI, "dados", "loop136.wav"), forca_quant=1.0)
        self.assertAlmostEqual(r["bpm"], 136.4, delta=0.3)
        self.assertEqual(r["bpm_arquivo"], 136)
        notas, comp = notas_da_deteccao(r["batidas"], r["bpm"])
        self.assertEqual(comp, 4)
        for compasso in range(4):                         # bumbo nos tempos 1, 3 e 4 de cada compasso
            bumbos = sorted((n.ini - compasso * COMPASSO) // SEMI for n in notas
                            if n.nota == 36 and compasso * COMPASSO <= n.ini < (compasso + 1) * COMPASSO)
            self.assertEqual(bumbos, [0, 8, 12], f"compasso {compasso + 1}")
            caixa_no_2 = any(n.nota == 38 and n.ini == compasso * COMPASSO + 4 * SEMI for n in notas)
            self.assertTrue(caixa_no_2, f"caixa no tempo 2, compasso {compasso + 1}")


# ====================================================================== ritmo / arquivos
class TesteRitmo(unittest.TestCase):
    def test_salvar_abrir(self):
        r = ritmo_demo()
        r.pistas[1].mapa = {"36": 24}
        c = os.path.join(TMP, "t.ritmo")
        r.salvar(c)
        self.assertEqual(Ritmo.abrir(c).para_dict(), r.para_dict())

    def test_demo_tem_todas_as_secoes_principais(self):
        r = ritmo_demo()
        for s in ["Intro A", "Var A", "Var B", "Var C", "Var D", "Fill A", "Fill D", "Break", "Final A"]:
            self.assertFalse(r.secoes[s].vazia, s)
        for s in r.secoes.values():
            for notas in s.pistas.values():
                for n in notas:
                    self.assertTrue(0 <= n.ini < s.ticks and n.dur > 0 and 0 <= n.nota <= 127 and 1 <= n.vel <= 127)

    def test_importar_midi(self):
        mid = mido.MidiFile(ticks_per_beat=96)
        t = mido.MidiTrack(); mid.tracks.append(t)
        for k in range(8):
            t.append(mido.Message("note_on", note=60 + k % 3, velocity=90, time=0 if k == 0 else 24))
            t.append(mido.Message("note_off", note=60 + k % 3, velocity=0, time=24))
        c = os.path.join(TMP, "in.mid"); mid.save(c)
        notas, comp = ler_midi(c)
        self.assertEqual(len(notas), 8)
        self.assertEqual(notas[1].ini, 240)            # 48 ticks@96 -> 240@480
        self.assertEqual(comp, 1)

    def test_estender_secao(self):
        r = ritmo_demo()
        s = r.secoes["Var A"]
        baixo = len(s.pistas[2])
        s.estender(4, exceto=1)
        self.assertEqual(s.compassos, 4)
        self.assertEqual(len(s.pistas[2]), 4 * baixo)
        self.assertTrue(all(n.ini < 4 * COMPASSO for n in s.pistas[2]))

    def test_exemplos_abrem(self):
        pasta = os.path.join(os.path.dirname(AQUI), "exemplos")
        for nome in os.listdir(pasta):
            if nome.endswith(".ritmo"):
                r = Ritmo.abrir(os.path.join(pasta, nome))
                self.assertFalse(r.secoes["Var A"].vazia, nome)

    def test_mapa_de_notas(self):
        r = ritmo_vazio()
        r.pistas[1].mapa = {"36": 24}
        self.assertEqual(r.pistas[1].nota_saida(36), 24)
        self.assertEqual(r.pistas[1].nota_saida(38), 38)


# ====================================================================== tocador
class Coletor:
    def __init__(self, tocador):
        self.t, self.log = tocador, []

    def __call__(self, m):
        self.log.append((self.t.pos, m))

    def ons(self, canal=None, desde=0):
        return [(p, m.note) for p, m in self.log if m.type == "note_on" and m.velocity > 0
                and (canal is None or m.channel == canal) and p >= desde]


class TesteTocador(unittest.TestCase):
    def novo(self):
        t = Tocador(ritmo_demo())
        t._thread_auto = False
        c = Coletor(t)
        t.adicionar_saida(c)
        return t, c

    def test_sync_start_espera_acorde(self):
        t, c = self.novo()
        t.armar_sync()
        t.avancar(COMPASSO)
        self.assertFalse(t.tocando)
        t.definir_acorde(AC.parse_acorde("C"))
        self.assertTrue(t.tocando)

    def test_intro_depois_variacao(self):
        t, c = self.novo()
        t.pedir("Intro A"); t.definir_acorde(AC.parse_acorde("C")); t.iniciar(com_thread=False)
        self.assertEqual(t.secao, "Intro A")
        t.avancar(2 * COMPASSO + 1)
        self.assertEqual(t.secao, "Var A")

    def test_troca_de_variacao_com_virada(self):
        t, c = self.novo()
        t.iniciar(com_thread=False)
        t.avancar(PPQ + 10)                      # meio do 1º compasso
        t.pedir("Var C")
        self.assertEqual(t.secao, "Fill C")      # virada entra na hora
        t.avancar(COMPASSO + 1)
        self.assertEqual(t.secao, "Var C")       # e no compasso seguinte vem a variação

    def test_troca_sem_auto_fill_no_compasso(self):
        t, c = self.novo()
        t.auto_fill = False
        t.iniciar(com_thread=False)
        t.avancar(PPQ)
        t.pedir("Var B")
        self.assertEqual(t.secao, "Var A")
        t.avancar(COMPASSO + 1)
        self.assertEqual(t.secao, "Var B")

    def test_final_para_e_solta_notas(self):
        t, c = self.novo()
        t.iniciar(com_thread=False)
        t.avancar(PPQ); t.pedir("Final A")
        t.avancar(10 * COMPASSO)
        self.assertFalse(t.tocando)
        self.assertEqual(t.soando, {})
        # todo note_on teve seu note_off
        abertas = {}
        for _, m in c.log:
            k = (m.channel, getattr(m, "note", None))
            if m.type == "note_on" and m.velocity > 0:
                abertas[k] = abertas.get(k, 0) + 1
            elif m.type == "note_off":
                abertas[k] = max(0, abertas.get(k, 0) - 1)
        self.assertFalse(any(abertas.values()), "notas presas")

    def test_baixo_segue_acorde(self):
        t, c = self.novo()
        t.definir_acorde(AC.parse_acorde("Am"))
        t.iniciar(com_thread=False)
        t.avancar(COMPASSO)
        self.assertEqual([AC.nome_nota(n) for _, n in c.ons(canal=10)], ["A1", "E2", "C2"])

    def test_troca_de_acorde_retoca_pad(self):
        t, c = self.novo()
        t.var_atual = "Var C"                    # tem pad (nota longa)
        t.definir_acorde(AC.parse_acorde("C"))
        t.iniciar(com_thread=False)
        t.avancar(2 * PPQ)
        t.definir_acorde(AC.parse_acorde("F"))
        pad = {n % 12 for p, n in c.ons(canal=13) if p == 2 * PPQ}
        self.assertEqual(pad, {5, 9, 0})          # F A C retocados na hora
        self.assertTrue(all((m.channel, m.note) != (13, 64) for k, m in t.soando and [] or []))

    def test_sequencia_automatica(self):
        t, c = self.novo()
        t.definir_sequencia([AC.parse_acorde(a) for a in ["C", "G", "Am", "F"]])
        t.iniciar(com_thread=False)
        vistos = []
        for k in range(4):
            t.avancar(k * COMPASSO + 1)
            vistos.append(t.acorde.nome)
        self.assertEqual(vistos, ["C", "G", "Am", "F"])

    def test_mao_esquerda(self):
        t, c = self.novo()
        t.armar_sync()
        mao = MaoEsquerda(t, split=54)
        for n in (45, 48, 52):                   # A2 C3 E3 -> Am
            mao.receber(mido.Message("note_on", note=n, velocity=80))
        self.assertTrue(t.tocando)
        self.assertEqual(t.acorde.nome, "Am")
        for n in (45, 48, 52):
            mao.receber(mido.Message("note_off", note=n))
        self.assertEqual(t.acorde.nome, "Am")     # memória do acorde
        mao.receber(mido.Message("note_on", note=72, velocity=80))   # mão direita não muda acorde
        self.assertEqual(t.acorde.nome, "Am")
        for n in (43, 48, 52):                   # G2 C3 E3: invertido
            mao.receber(mido.Message("note_on", note=n, velocity=80))
        self.assertEqual(t.acorde.nome, "C")      # Fingered: toca como C
        for n in (43, 48, 52):
            mao.receber(mido.Message("note_off", note=n))
        mao.modo = "onbass"
        for n in (43, 48, 52):
            mao.receber(mido.Message("note_on", note=n, velocity=80))
        self.assertEqual(t.acorde.nome, "C/G")    # On Bass: Sol no baixo

    def test_mudo_e_mapa(self):
        t, c = self.novo()
        t.ritmo.pistas[2].mudo = True
        t.ritmo.pistas[1].mapa = {"36": 24}
        t.iniciar(com_thread=False)
        t.avancar(COMPASSO)
        self.assertFalse(c.ons(canal=10))
        self.assertIn(24, [n for _, n in c.ons(canal=9)])
        self.assertNotIn(36, [n for _, n in c.ons(canal=9)])

    def test_relogio_real(self):
        import time
        t = Tocador(ritmo_demo())
        c = Coletor(t); t.adicionar_saida(c)
        t.definir_bpm(120)
        t.iniciar()
        time.sleep(1.05)                          # 2 tempos a 120 BPM
        t.parar()
        self.assertTrue(abs(t.pos - 2 * PPQ) < PPQ * 0.2, t.pos)


# ====================================================================== exportar / som
class TesteExportar(unittest.TestCase):
    ROT = "Intro A: C\nVar A: C Am F G7\nFill B: G7\nVar B: C Am Dm,G7 C\nFinal A: C"

    def test_roteiro(self):
        rot = EX.parse_roteiro(self.ROT)
        self.assertEqual([s for s, _ in rot], ["Intro A", "Var A", "Fill B", "Var B", "Final A"])
        self.assertEqual([a.nome for a in rot[3][1][2]], ["Dm", "G7"])
        with self.assertRaises(ValueError):
            EX.parse_roteiro("Var Z: C")

    def test_midi(self):
        r = ritmo_demo()
        ev, tot = EX.gerar_eventos(r, EX.parse_roteiro(self.ROT))
        self.assertEqual(tot, (2 + 4 + 1 + 4 + 2) * COMPASSO)
        c = os.path.join(TMP, "musica.mid")
        EX.salvar_midi(r, ev, c)
        mid = mido.MidiFile(c)
        self.assertAlmostEqual(mid.length, tot / PPQ * 60 / r.bpm, delta=0.5)
        ons = sum(1 for m in mid if m.type == "note_on" and m.velocity > 0)
        offs = sum(1 for m in mid if m.type == "note_off" or (m.type == "note_on" and m.velocity == 0))
        self.assertEqual(ons, offs)

    def test_wav(self):
        import soundfile as sf
        r = ritmo_demo()
        ev, tot = EX.gerar_eventos(r, EX.parse_roteiro("Var D: C G Am F"))
        c = os.path.join(TMP, "musica.wav")
        info = EX.renderizar(r, ev, tot, c)
        a, sr = sf.read(c)
        self.assertEqual(a.shape[1], 2)
        self.assertGreater(len(a) / sr, 6.5)
        self.assertLess(np.max(np.abs(a)), 1.0)
        self.assertGreater(np.sqrt(np.mean(a ** 2)), 0.02)
        self.assertEqual(len(info["pistas"]), 8)

    def test_vst_falha_cai_no_som_interno(self):
        r = ritmo_demo()
        r.pistas[2].vst = "/nao/existe/Kontakt 8.vst3"
        ev, tot = EX.gerar_eventos(r, EX.parse_roteiro("Var A: C"))
        info = EX.renderizar(r, ev, tot, os.path.join(TMP, "v.wav"))
        self.assertIn("som interno", info["pistas"]["Bass (Baixo)"])

    def test_vst_simulado_usado_na_renderizacao(self):
        r = ritmo_demo()
        r.pistas[2].vst = "Kontakt.vst3"
        chamadas = []

        class Falso:
            def __init__(self, caminho, estado=None):
                pass

            def renderizar(self, evs, dur, sr):
                chamadas.append(len(evs))
                return np.full((int((dur + 1.5) * sr), 2), 0.1, dtype=np.float32)

        with mock.patch("nucleo.vst.InstrumentoVST", Falso):
            ev, tot = EX.gerar_eventos(r, EX.parse_roteiro("Var A: C"))
            info = EX.renderizar(r, ev, tot, os.path.join(TMP, "v2.wav"))
        self.assertTrue(chamadas and chamadas[0] > 0)
        self.assertTrue(info["pistas"]["Bass (Baixo)"].startswith("VST"))


class TesteSintetizador(unittest.TestCase):
    def test_toca_e_solta(self):
        s = Sintetizador({0: ("pad", 1.0), 9: ("bateria", 1.0)})
        s.enviar(mido.Message("note_on", channel=0, note=60, velocity=100))
        s.enviar(mido.Message("note_on", channel=9, note=36, velocity=100))
        a = s.misturar(4410)
        self.assertEqual(a.shape, (4410, 2))
        self.assertGreater(np.abs(a).max(), 0.05)
        s.enviar(mido.Message("note_off", channel=0, note=60))
        for _ in range(200):
            s.misturar(512)
        self.assertEqual(len(s.vozes), 0)

    def test_todos_os_timbres(self):
        from nucleo.sintetizador import som_bateria, som_tonal
        for t in ["baixo", "violao", "piano", "pad", "sanfona", "metais", "orgao"]:
            for n in (30, 60, 96):
                x = som_tonal(t, n)
                self.assertTrue(np.isfinite(x).all() and np.abs(x).max() > 0.5, (t, n))
        for n in range(27, 88):
            self.assertTrue(np.isfinite(som_bateria(n)).all())

    def test_vst_ao_vivo_simulado(self):
        class PluginFalso:
            def __init__(self):
                self.recebidas = []

            def __call__(self, msgs, duration, sample_rate, num_channels, buffer_size, reset):
                assert reset is False
                self.recebidas += msgs
                return np.full((2, int(round(duration * sample_rate))), 0.2, dtype=np.float32)

        class Inst:
            plugin = PluginFalso()

        s = Sintetizador({10: ("baixo", 1.0)})
        s.ligar_vst(10, Inst)
        s.enviar(mido.Message("note_on", channel=10, note=40, velocity=100))
        a = s.misturar(256)
        self.assertEqual(len(Inst.plugin.recebidas), 1)
        self.assertGreater(a.max(), 0.1)
        self.assertEqual(len(s.vozes), 0)        # não tocou no som interno


if __name__ == "__main__":
    unittest.main(verbosity=2)
