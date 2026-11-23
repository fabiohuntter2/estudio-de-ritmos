// Motor de acordes: reconhecimento e transposição (acorde-fonte = CMaj7).
// Porta fiel de nucleo/acordes.py.
#pragma once
#include <string>
#include <vector>
#include <optional>

namespace er
{
enum class Regra { Bypass, Fundamental, Acorde, Melodia };

Regra regraDeTexto (const std::string& s);
const char* textoDaRegra (Regra r);

struct Acorde
{
    int fundamental = 0;
    std::string tipo;      // chave de TIPOS ("", "m", "7", "maj7"...)
    int baixo = -1;        // -1 = sem baixo invertido

    const std::vector<int>& intervalos() const;
    bool tem (int intervalo) const;
    int terca() const;
    int quinta() const;
    int setima() const;    // -1 = sem sétima
    std::string nome() const;

    bool operator== (const Acorde& o) const { return fundamental == o.fundamental && tipo == o.tipo && baixo == o.baixo; }
    bool operator!= (const Acorde& o) const { return ! (*this == o); }
};

const Acorde& acordePadrao();

// Lança std::invalid_argument se não reconhecer o texto.
Acorde parseAcorde (const std::string& texto);

// modoSingle = Single Finger. Devolve vazio se não reconhecer.
std::optional<Acorde> reconhecer (std::vector<int> notas, bool modoSingle = false);

int transporNota (int nota, Regra regra, int faixaLo, int faixaHi, const Acorde& alvo);

std::string nomeNota (int n);
} // namespace er
