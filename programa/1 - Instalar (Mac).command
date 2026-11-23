#!/bin/bash
cd "$(dirname "$0")"
echo "== Estúdio de Ritmos — instalação =="
PY=""
for v in 3.12 3.13 3.11; do command -v python$v >/dev/null && { PY=python$v; break; }; done
if [ -z "$PY" ]; then
  echo "Instale o Python 3.12: https://www.python.org/downloads/release/python-31210/ (macOS 64-bit universal2 installer)"
  open "https://www.python.org/downloads/release/python-31210/"; read -p "Enter para sair"; exit 1
fi
echo "Usando $($PY --version)"
rm -rf .venv && "$PY" -m venv .venv && .venv/bin/python -m pip install --upgrade pip >/dev/null
.venv/bin/python -m pip install --only-binary=:all: -r requirements.txt || { echo "Falhou. Mande um print."; read -p "Enter"; exit 1; }
FALTOU=""
.venv/bin/python -m pip install --only-binary=:all: "sounddevice>=0.4.6" || FALTOU="$FALTOU [som]"
.venv/bin/python -m pip install --only-binary=:all: "python-rtmidi>=1.5" || FALTOU="$FALTOU [teclado-MIDI]"
.venv/bin/python -m pip install --only-binary=:all: "pedalboard>=0.9.10" || FALTOU="$FALTOU [VST]"
.venv/bin/python -m unittest discover -s testes -p "test_*.py"
[ -n "$FALTOU" ] && echo "ATENÇÃO: não instalou:$FALTOU (o programa abre sem esses recursos)"
echo; echo "Pronto! Abra com '2 - Abrir Estudio de Ritmos (Mac).command'"; read -p "Enter para sair"
