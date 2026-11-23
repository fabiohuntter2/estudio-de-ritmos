// Testes do núcleo C++.
//   TestesNucleo cenario <ritmo.ritmo> <cenario.json>  -> imprime os eventos (JSON, uma linha cada)
//   TestesNucleo acordes                               -> imprime reconhecimento/transposição de uma bateria de casos
#include <juce_core/juce_core.h>
#include "../Source/nucleo/Motor.h"
#include <iostream>

using namespace er;

static int cenario (const char* ritmoPath, const char* cenarioPath)
{
    auto texto = juce::File (ritmoPath).loadFileAsString().toStdString();
    auto ritmo = Ritmo::deJson (texto);
    Motor m;
    m.setRitmo (ritmo);
    m.setSaida ([] (const Evento& e) {
        static const char* t[] = { "on", "off", "cc", "pc" };
        std::cout << "[" << e.tick << ",\"" << t[e.tipo] << "\"," << e.canal << "," << e.d1 << "," << e.d2 << "]\n";
    });
    juce::var cmds = juce::JSON::parse (juce::File (cenarioPath));
    for (auto& c : *cmds.getArray())
    {
        long long tick = (long long) (juce::int64) c["tick"];
        juce::String cmd = c["cmd"].toString();
        std::string v = c["v"].toString().toStdString();
        m.avancar (tick);
        if (cmd == "acorde") m.definirAcorde (parseAcorde (v));
        else if (cmd == "iniciar") m.iniciar();
        else if (cmd == "parar") m.parar();
        else if (cmd == "pedir") m.pedir (v);
        else if (cmd == "sync") m.armarSync (true);
        else if (cmd == "autofill") m.autoFill = v == "1";
        else if (cmd == "sequencia")
        {
            std::vector<Acorde> seq;
            for (auto& s : juce::StringArray::fromTokens (juce::String (v), " ", ""))
                seq.push_back (parseAcorde (s.toStdString()));
            m.definirSequencia (seq);
        }
        else if (cmd == "fim") {}
        std::cout << "# " << cmd << " " << v << " -> " << (m.tocando ? m.secao : std::string ("parado")) << "\n";
    }
    return 0;
}

static int acordes()
{
    // reconhecimento
    std::vector<std::vector<int>> casos = { { 60, 64, 67 }, { 57, 60, 64 }, { 55, 59, 62, 65 }, { 62, 65, 69, 72 },
        { 60, 64, 67, 71 }, { 59, 62, 65 }, { 60, 64, 68 }, { 62, 67, 69 }, { 64, 67, 72 }, { 67, 72, 76 },
        { 59, 62, 65, 68 }, { 57, 60, 63, 67 }, { 48, 55 }, { 52, 55, 59, 62 }, { 53, 57, 60, 62 }, { 50, 53, 57, 60 },
        { 45, 48, 52, 55 }, { 43, 47, 50, 53, 57 }, { 41, 45, 48, 52 } };
    for (auto& c : casos)
    {
        auto a = reconhecer (c);
        std::cout << "R";
        for (int n : c) std::cout << " " << n;
        std::cout << " = " << (a ? a->nome() : "?") << "\n";
    }
    // transposição: todas as regras, todos os acordes, todas as notas de uma faixa
    const char* tiposTeste[] = { "", "m", "7", "m7", "maj7", "6", "m6", "dim", "dim7", "m7b5", "aug", "sus4", "sus2", "7sus4", "9", "add9", "m9", "mmaj7" };
    const char* nomes[] = { "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B" };
    for (int raiz = 0; raiz < 12; ++raiz)
        for (auto* tipo : tiposTeste)
        {
            Acorde ac = parseAcorde (std::string (nomes[raiz]) + tipo);
            std::cout << "T " << ac.nome();
            for (auto [regra, lo, hi] : { std::tuple { Regra::Fundamental, 28, 52 }, { Regra::Acorde, 52, 76 }, { Regra::Melodia, 60, 88 } })
                for (int n = lo; n <= hi; ++n) std::cout << " " << transporNota (n, regra, lo, hi, ac);
            std::cout << "\n";
        }
    auto inv = parseAcorde ("C/E");
    std::cout << "T C/E " << transporNota (36, Regra::Fundamental, 28, 52, inv) << "\n";
    return 0;
}

int main (int argc, char** argv)
{
    try
    {
        if (argc >= 4 && std::string (argv[1]) == "cenario") return cenario (argv[2], argv[3]);
        if (argc >= 2 && std::string (argv[1]) == "acordes") return acordes();
    }
    catch (const std::exception& e)
    {
        std::cerr << "ERRO: " << e.what() << "\n";
        return 2;
    }
    std::cerr << "uso: TestesNucleo cenario <ritmo> <cenario.json> | acordes\n";
    return 1;
}
