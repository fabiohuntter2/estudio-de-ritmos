#!/bin/bash
cd "$(dirname "$0")"
.venv/bin/python app.py "$@" || read -p "O programa fechou com erro. Tire um print e mande. Enter para sair"
