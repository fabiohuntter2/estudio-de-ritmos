// Ritmo: 8 pistas × seções, lido do arquivo .ritmo (JSON) do Estúdio de Ritmos.
#pragma once
#include "Acordes.h"
#include <map>
#include <memory>
#include <string>
#include <vector>

namespace er
{
constexpr int PPQ = 480;
constexpr int SEMI = PPQ / 4;
constexpr int COMPASSO = PPQ * 4;

const std::vector<std::string>& nomesSecoes();

struct Nota { int ini = 0, dur = 0, nota = 60, vel = 100; };

struct ConfigPista
{
    std::string nome;
    int canal = 0;                 // 0..15
    Regra regra = Regra::Bypass;
    int lo = 0, hi = 127;
    int programa = -1;             // General MIDI; -1 = nenhum
    double volume = 0.8;
    bool mudo = false;
    std::map<int, int> mapa;       // bateria: nota GM -> nota da biblioteca

    int notaSaida (int n) const
    {
        auto it = mapa.find (n);
        return it == mapa.end() ? n : it->second;
    }
};

struct Secao
{
    int compassos = 1;
    std::vector<std::pair<int, std::vector<Nota>>> pistas;   // ordem do arquivo

    bool vazia() const
    {
        for (auto& p : pistas) if (! p.second.empty()) return false;
        return true;
    }
    long long ticks() const { return (long long) compassos * COMPASSO; }
};

struct Ritmo
{
    std::string nome = "Sem nome";
    double bpm = 120.0;
    std::vector<ConfigPista> pistas;
    std::map<std::string, Secao> secoes;

    const Secao& secao (const std::string& n) const;
    bool vazia (const std::string& n) const { return secao (n).vazia(); }

    // Lança std::runtime_error se o JSON for inválido.
    static std::shared_ptr<Ritmo> deJson (const std::string& texto);
};
} // namespace er
