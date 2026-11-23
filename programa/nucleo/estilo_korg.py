"""Estilos Korg (série Pa): identificação e importação do que é possível hoje.

O que a Korg usa:
  - Pa (Pa50 ... Pa4X/Pa1000/Pa700): pasta  NOME.SET/STYLE/  com arquivos  BANKxx.STY / USERxx.STY /
    FAVORITExx.STY. Cada .STY é um BANCO com vários estilos, em formato fechado; partes vêm comprimidas
    (blocos que começam com "OC31"). A Korg não publica a especificação.
  - Pa5X: conjuntos .KST com um estilo por arquivo .STG (formato novo, também fechado).
  - Alguns .STY antigos/convertidos e as exportações de estilo são MIDI comum com marcadores
    ("Variation 1", "Fill 2", "Ending 1"...): esses o programa importa direto.

Para os bancos binários, `relatorio()` gera um diagnóstico técnico do arquivo, base para a
engenharia reversa quando houver arquivos reais para comparar.
"""
from __future__ import annotations

import os
import re
import struct


def _ler(origem) -> bytes:
    if isinstance(origem, (bytes, bytearray)):
        return bytes(origem)
    with open(origem, "rb") as f:
        return f.read()


def identificar(origem) -> dict:
    """Descobre o tipo do arquivo de estilo e devolve {tipo, mensagem, ...}."""
    if isinstance(origem, str) and os.path.isdir(origem):
        pasta_style = os.path.join(origem, "STYLE")
        arquivos = sorted(os.listdir(pasta_style)) if os.path.isdir(pasta_style) else []
        return {"tipo": "korg_set", "arquivos": arquivos,
                "mensagem": f"Pasta de SET da Korg com {len(arquivos)} arquivo(s) de estilo em STYLE/. "
                            "Escolha um dos arquivos .STY dentro dela."}
    d = _ler(origem)
    nome = origem if isinstance(origem, str) else ""
    ext = os.path.splitext(nome)[1].lower()
    if d[:4] == b"MThd":
        casm = b"CASM" in d
        return {"tipo": "yamaha" if casm else "midi_estilo",
                "mensagem": "Estilo Yamaha (SFF)." if casm else "Estilo em MIDI comum (Korg exportado/convertido)."}
    oc31 = d.count(b"OC31")
    midi_dentro = d.find(b"MThd")
    tipo = "korg_stg" if ext == ".stg" else "korg_sty_banco"
    modelo = "Pa5X (.STG)" if tipo == "korg_stg" else "Korg Pa (banco .STY)"
    msg = (f"Este arquivo é um {modelo}, um formato fechado da Korg"
           + (" e comprimido" if oc31 else "") + ". "
           "Ainda não é possível abri-lo diretamente. Caminhos que funcionam hoje: "
           "(1) estilos Korg convertidos para Yamaha (.sty) abrem normalmente; "
           "(2) no teclado Korg, grave cada seção do estilo como MIDI (modo Sequencer) e importe pelo programa. "
           "Mande este arquivo para análise: ele ajuda a decifrar o formato.")
    return {"tipo": tipo, "mensagem": msg, "tamanho": len(d), "blocos_oc31": oc31,
            "midi_embutido_em": midi_dentro if midi_dentro >= 0 else None}


def relatorio(origem) -> str:
    """Diagnóstico técnico de um arquivo Korg (para engenharia reversa)."""
    d = _ler(origem)
    info = identificar(origem)
    linhas = [f"Tipo: {info['tipo']}", f"Tamanho: {len(d)} bytes"]
    linhas.append("Início (hex): " + d[:64].hex(" "))
    linhas.append("Início (texto): " + "".join(chr(b) if 32 <= b < 127 else "." for b in d[:64]))
    marcas = {}
    for m in re.finditer(rb"[A-Z][A-Za-z0-9 ]{3}", d[:200000]):
        marcas[m.group()] = marcas.get(m.group(), 0) + 1
    comuns = sorted(marcas.items(), key=lambda kv: -kv[1])[:25]
    linhas.append("Etiquetas de 4 letras mais frequentes: " +
                  ", ".join(f"{k.decode('latin-1')}×{v}" for k, v in comuns))
    pos = [m.start() for m in re.finditer(rb"OC31", d)]
    linhas.append(f"Blocos OC31 (comprimidos): {len(pos)}" + (f" — primeiros em {pos[:10]}" if pos else ""))
    textos = re.findall(rb"[ -~]{6,}", d)
    linhas.append("Textos legíveis (até 40): " + " | ".join(t.decode("latin-1") for t in textos[:40]))
    if len(d) >= 16:
        be = struct.unpack(">IIII", d[:16])
        le = struct.unpack("<IIII", d[:16])
        linhas.append(f"Primeiros 4 inteiros (big-endian): {be}  (little-endian): {le}")
    return "\n".join(linhas)


if __name__ == "__main__":
    import sys
    for caminho in sys.argv[1:]:
        print("=" * 70, "\n", caminho, "\n", relatorio(caminho), sep="")
