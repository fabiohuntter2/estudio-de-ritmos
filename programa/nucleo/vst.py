"""Instrumentos VST3/AU (Kontakt e outros) por pista, via biblioteca pedalboard (Spotify).

O que funciona nesta versão:
  - procurar os plugins instalados nas pastas padrão;
  - carregar o plugin numa pista e abrir a janela dele (para escolher a biblioteca no Kontakt);
  - guardar o estado do plugin dentro do arquivo .ritmo (a biblioteca carregada volta ao abrir);
  - renderizar a pista com o plugin para WAV.
Tocar AO VIVO com o Kontakt é feito pela saída MIDI (Kontakt standalone ou DAW) — veja o LEIA-ME.
"""
from __future__ import annotations

import base64
import os
import platform
from pathlib import Path

try:
    import pedalboard
    DISPONIVEL = True
except Exception:                       # pragma: no cover
    pedalboard = None
    DISPONIVEL = False


def pastas_padrao() -> list[Path]:
    s = platform.system()
    if s == "Windows":
        pf = os.environ.get("CommonProgramFiles", r"C:\Program Files\Common Files")
        return [Path(pf) / "VST3", Path(r"C:\Program Files\Common Files\VST3"),
                Path(r"C:\Program Files\Native Instruments")]
    if s == "Darwin":
        h = Path.home()
        return [Path("/Library/Audio/Plug-Ins/VST3"), h / "Library/Audio/Plug-Ins/VST3",
                Path("/Library/Audio/Plug-Ins/Components"), h / "Library/Audio/Plug-Ins/Components"]
    return [Path.home() / ".vst3", Path("/usr/lib/vst3"), Path("/usr/local/lib/vst3")]


def procurar_plugins(pastas=None) -> list[str]:
    """Lista caminhos de .vst3 (e .component no Mac). Kontakt aparece como 'Kontakt 8.vst3' etc."""
    achados = []
    for pasta in pastas or pastas_padrao():
        if not pasta.exists():
            continue
        for raiz, dirs, arquivos in os.walk(pasta):
            for nome in list(dirs) + arquivos:
                if nome.lower().endswith((".vst3", ".component")):
                    achados.append(str(Path(raiz) / nome))
            dirs[:] = [d for d in dirs if not d.lower().endswith((".vst3", ".component"))]
    vistos, unicos = set(), []
    for a in sorted(achados, key=lambda p: (("kontakt" not in p.lower()), p.lower())):
        if a not in vistos:
            vistos.add(a); unicos.append(a)
    return unicos


def nome_curto(caminho: str | None) -> str:
    return Path(caminho).stem if caminho else "—"


class InstrumentoVST:
    def __init__(self, caminho: str, estado_b64: str | None = None, nome_plugin: str | None = None):
        if not DISPONIVEL:
            raise RuntimeError("A biblioteca 'pedalboard' não está instalada.")
        self.caminho = caminho
        self.plugin = pedalboard.load_plugin(caminho, plugin_name=nome_plugin) if nome_plugin \
            else pedalboard.load_plugin(caminho)
        if not getattr(self.plugin, "is_instrument", True):
            raise ValueError(f"'{nome_curto(caminho)}' não é um instrumento (é um efeito).")
        if estado_b64:
            self.definir_estado(estado_b64)

    def abrir_janela(self):
        """Abre a janela do plugin (bloqueia até ela ser fechada)."""
        self.plugin.show_editor()

    def estado(self) -> str:
        return base64.b64encode(bytes(self.plugin.raw_state)).decode("ascii")

    def definir_estado(self, b64: str):
        self.plugin.raw_state = base64.b64decode(b64)

    def renderizar(self, eventos_seg: list, duracao: float, sr: int = 44100):
        """eventos_seg: [(segundos, mido.Message)]. Devolve np.ndarray (amostras, canais)."""
        msgs = [(bytes(m.bytes()), float(t)) for t, m in sorted(eventos_seg, key=lambda e: e[0])]
        audio = self.plugin(msgs, duration=duracao + 1.5, sample_rate=sr, num_channels=2)
        return audio.T
