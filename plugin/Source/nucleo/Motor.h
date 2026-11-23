// Motor de execução (porta fiel de nucleo/tocador.py): seções, viradas, troca de acorde.
// Não usa relógio: quem chama avança o tempo em ticks (PPQ 480). Sem alocação no caminho comum.
#pragma once
#include "Ritmo.h"
#include <functional>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace er
{
struct Evento
{
    enum Tipo { NoteOn, NoteOff, ControlChange, ProgramChange };
    long long tick;
    Tipo tipo;
    int canal, d1, d2;
};

struct EstadoMotor
{
    bool tocando = false, armado = false;
    std::string secao, var, intro, proxima, acorde = "—";
    int compasso = 0, tempo = 0;
};

class Motor
{
public:
    using Saida = std::function<void (const Evento&)>;

    void setRitmo (std::shared_ptr<const Ritmo> r);
    const Ritmo* ritmo() const { return ritmoAtual.get(); }
    void setSaida (Saida s) { saida = std::move (s); }

    void iniciar (long long posInicial = 0);
    void parar();
    void armarSync (bool ligado);
    void pedir (const std::string& nome);
    bool definirAcorde (const Acorde& ac);          // true se iniciou (Sync Start)
    void definirSequencia (std::vector<Acorde> seq);
    void avancar (long long ate);                   // processa eventos com tick em [pos, ate)

    bool tocando = false, armado = false, autoFill = true;
    long long pos = 0;
    EstadoMotor estado() const;
    std::optional<Acorde> acorde;
    std::string varAtual = "Var A";
    std::string introEscolhida;
    std::string secao;

private:
    struct Agendado { long long tick; int pista; Nota n; };
    struct Soando { int canal, nota; long long off; int pista, fonte, vel; };

    bool vazia (const std::string& n) const;
    void enviar (Evento::Tipo t, int canal, int d1, int d2);
    void entrar (const std::string& nome, long long inicio, long long aPartir = -1);
    int notaSaida (int pista, int fonte) const;
    void ligar (int pista, int fonte, int vel, long long off);
    void desligar (size_t idx);
    void todasOff();
    void retocar();
    void fronteira (bool fimSecao);
    void viradaAgora (std::vector<std::string> f);
    void proximoDaSequencia();

    std::shared_ptr<const Ritmo> ritmoAtual;
    Saida saida;
    long long inicioSecao = 0;
    std::vector<std::string> fila;
    bool trocaNoCompasso = false;
    std::vector<Soando> soando;     // ordem de inserção (como o dict do Python)
    std::vector<Agendado> eventos;
    size_t evIdx = 0;
    std::vector<Acorde> sequencia;
    size_t seqIdx = 0;
};
} // namespace er
