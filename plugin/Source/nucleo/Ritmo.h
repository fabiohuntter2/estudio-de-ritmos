// Ritmo: 8 pistas × seções (+ camadas por tipo de acorde), lido do .ritmo (JSON) ou de um estilo .sty.
// Porta fiel de nucleo/ritmo.py.
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
constexpr int COMPASSO = PPQ * 4;     // 4/4 (padrão)

inline int ticksDoCompasso (int num, int den) { return num * PPQ * 4 / den; }

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

std::vector<ConfigPista> pistasPadrao();

// Notas extras de uma pista, com regras próprias e filtro por acorde (estilos Yamaha).
struct Camada
{
    int pista = 0;
    std::vector<Nota> notas;
    Regra regra = Regra::Bypass;
    int lo = 0, hi = 127;
    Acorde fonte { 0, "maj7", -1 };
    int teclaAlta = TECLA_ALTA_PADRAO;
    std::vector<std::string> tiposMudos;
    std::vector<int> raizesMudas;
    std::string nome;

    bool tipoMudo (const std::string& t) const;
    bool raizMuda (int r) const;
};

struct Secao
{
    int compassos = 1;
    int tc = COMPASSO;                                       // ticks por compasso
    std::vector<std::pair<int, std::vector<Nota>>> pistas;   // ordem do arquivo
    std::vector<Camada> camadas;

    bool vazia() const;
    long long ticks() const { return (long long) compassos * tc; }
    bool camadaToca (const Camada& c, const Acorde& ac) const;
    std::vector<Nota>& notasDaPista (int pista);
};

struct Ritmo
{
    std::string nome = "Sem nome";
    double bpm = 120.0;
    int compassoNum = 4, compassoDen = 4;
    std::vector<ConfigPista> pistas;
    std::map<std::string, Secao> secoes;

    int ticksCompasso() const { return ticksDoCompasso (compassoNum, compassoDen); }
    void definirCompasso (int num, int den);
    const Secao& secao (const std::string& n) const;
    bool vazia (const std::string& n) const { return secao (n).vazia(); }

    // Lança std::runtime_error se o JSON for inválido.
    static std::shared_ptr<Ritmo> deJson (const std::string& texto);
};
} // namespace er
