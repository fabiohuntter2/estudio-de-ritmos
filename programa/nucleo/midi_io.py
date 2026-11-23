"""Portas MIDI (entrada do teclado e saída para Kontakt/DAW). Funciona sem rtmidi (lista vazia)."""
from __future__ import annotations

import mido


def _seguro(fn):
    try:
        return list(fn())
    except Exception:
        return []


def listar_saidas() -> list[str]:
    return _seguro(mido.get_output_names)


def listar_entradas() -> list[str]:
    return _seguro(mido.get_input_names)


class SaidaMidi:
    def __init__(self, nome: str):
        self.nome = nome
        self.porta = mido.open_output(nome)

    def __call__(self, msg):
        self.porta.send(msg)

    def fechar(self):
        try:
            for ch in range(16):
                self.porta.send(mido.Message("control_change", channel=ch, control=123, value=0))
            self.porta.close()
        except Exception:
            pass


class EntradaMidi:
    def __init__(self, nome: str, callback):
        self.nome = nome
        self.porta = mido.open_input(nome, callback=callback)

    def fechar(self):
        try:
            self.porta.close()
        except Exception:
            pass
