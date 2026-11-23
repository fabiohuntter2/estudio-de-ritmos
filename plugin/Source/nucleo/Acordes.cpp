#include "Acordes.h"
#include <algorithm>
#include <map>
#include <set>
#include <stdexcept>
#include <cstdlib>
#include <tuple>

namespace er
{
static const char* NOMES[12] = { "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B" };

// Na mesma ordem de preferência de _PREF do Python.
static const std::vector<std::pair<std::string, std::vector<int>>>& tipos()
{
    static const std::vector<std::pair<std::string, std::vector<int>>> t = {
        { "", { 0, 4, 7 } },        { "m", { 0, 3, 7 } },         { "7", { 0, 4, 7, 10 } },
        { "m7", { 0, 3, 7, 10 } },  { "maj7", { 0, 4, 7, 11 } },  { "dim", { 0, 3, 6 } },
        { "aug", { 0, 4, 8 } },     { "sus4", { 0, 5, 7 } },      { "6", { 0, 4, 7, 9 } },
        { "m6", { 0, 3, 7, 9 } },   { "dim7", { 0, 3, 6, 9 } },   { "m7b5", { 0, 3, 6, 10 } },
        { "7sus4", { 0, 5, 7, 10 } }, { "sus2", { 0, 2, 7 } },    { "add9", { 0, 4, 7, 14 } },
        { "9", { 0, 4, 7, 10, 14 } }, { "m9", { 0, 3, 7, 10, 14 } }, { "mmaj7", { 0, 3, 7, 11 } },
    };
    return t;
}

static int indiceTipo (const std::string& tipo)
{
    const auto& t = tipos();
    for (size_t i = 0; i < t.size(); ++i)
        if (t[i].first == tipo) return (int) i;
    return -1;
}

static int mod12 (int x) { return ((x % 12) + 12) % 12; }

Regra regraDeTexto (const std::string& s)
{
    if (s == "fundamental") return Regra::Fundamental;
    if (s == "acorde") return Regra::Acorde;
    if (s == "melodia") return Regra::Melodia;
    return Regra::Bypass;
}

const char* textoDaRegra (Regra r)
{
    switch (r)
    {
        case Regra::Fundamental: return "fundamental";
        case Regra::Acorde: return "acorde";
        case Regra::Melodia: return "melodia";
        default: return "bypass";
    }
}

const std::vector<int>& Acorde::intervalos() const
{
    int i = indiceTipo (tipo);
    return tipos()[(size_t) (i < 0 ? 0 : i)].second;
}

bool Acorde::tem (int iv) const
{
    const auto& v = intervalos();
    return std::find (v.begin(), v.end(), iv) != v.end();
}

int Acorde::terca() const
{
    for (int i : { 4, 3, 5, 2 }) if (tem (i)) return i;
    return 4;
}

int Acorde::quinta() const
{
    for (int i : { 7, 6, 8 }) if (tem (i)) return i;
    return 7;
}

int Acorde::setima() const
{
    for (int i : { 11, 10 }) if (tem (i)) return i;
    if (tipo == "dim7" || tipo == "6" || tipo == "m6") return 9;
    return -1;
}

std::string Acorde::nome() const
{
    std::string n = std::string (NOMES[mod12 (fundamental)]) + tipo;
    if (baixo >= 0 && baixo != fundamental) n += std::string ("/") + NOMES[mod12 (baixo)];
    return n;
}

const Acorde& acordePadrao()
{
    static const Acorde a { 0, "", -1 };
    return a;
}

static int parseNota (std::string n)
{
    static const std::map<std::string, int> aliases = { { "Db", 1 }, { "Eb", 3 }, { "Gb", 6 }, { "Ab", 8 }, { "Bb", 10 },
                                                        { "Cb", 11 }, { "Fb", 4 }, { "E#", 5 }, { "B#", 0 } };
    while (! n.empty() && n.back() == ' ') n.pop_back();
    while (! n.empty() && n.front() == ' ') n.erase (n.begin());
    if (auto it = aliases.find (n); it != aliases.end()) return it->second;
    if (! n.empty()) n[0] = (char) std::toupper ((unsigned char) n[0]);
    for (int i = 0; i < 12; ++i)
        if (n == NOMES[i]) return i;
    throw std::invalid_argument ("Nota desconhecida: '" + n + "'");
}

Acorde parseAcorde (const std::string& texto)
{
    static const std::map<std::string, std::string> sinonimos = {
        { "M7", "maj7" }, { "7M", "maj7" }, { "Maj7", "maj7" }, { "min", "m" }, { "-", "m" }, { "\xC2\xB0", "dim" },
        { "\xC2\xBA", "dim" }, { "o", "dim" }, { "+", "aug" }, { "m7(b5)", "m7b5" }, { "\xC3\xB8", "m7b5" },
        { "4", "sus4" }, { "sus", "sus4" }, { "7/4", "7sus4" }, { "min7", "m7" }, { "-7", "m7" },
        { "\xC2\xB0" "7", "dim7" }, { "\xC2\xBA" "7", "dim7" } };

    std::string t = texto;
    while (! t.empty() && (t.back() == ' ' || t.back() == '\t')) t.pop_back();
    while (! t.empty() && (t.front() == ' ' || t.front() == '\t')) t.erase (t.begin());
    if (t.empty()) throw std::invalid_argument ("Acorde vazio");
    int baixo = -1;
    auto barra = t.find ('/', 1);
    if (barra != std::string::npos)
    {
        std::string resto = t.substr (barra + 1);
        if (! resto.empty() && std::string ("ABCDEFG").find ((char) std::toupper ((unsigned char) resto[0])) != std::string::npos)
        {
            baixo = parseNota (resto);
            t = t.substr (0, barra);
        }
    }
    t[0] = (char) std::toupper ((unsigned char) t[0]);
    std::string raiz, tipo;
    if (t.size() >= 2 && (t[1] == '#' || t[1] == 'b')) { raiz = t.substr (0, 2); tipo = t.substr (2); }
    else { raiz = t.substr (0, 1); tipo = t.substr (1); }
    if (auto it = sinonimos.find (tipo); it != sinonimos.end()) tipo = it->second;
    if (indiceTipo (tipo) < 0) throw std::invalid_argument ("Tipo de acorde desconhecido: '" + tipo + "' em '" + texto + "'");
    return Acorde { parseNota (raiz), tipo, baixo };
}

static bool ehPreta (int n) { int p = mod12 (n); return p == 1 || p == 3 || p == 6 || p == 8 || p == 10; }

std::optional<Acorde> reconhecer (std::vector<int> notas, bool modoSingle)
{
    std::sort (notas.begin(), notas.end());
    notas.erase (std::unique (notas.begin(), notas.end()), notas.end());
    if (notas.empty()) return std::nullopt;

    if (modoSingle)
    {
        int raiz = mod12 (notas.back());
        bool pretas = false, brancas = false;
        for (size_t i = 0; i + 1 < notas.size(); ++i) (ehPreta (notas[i]) ? pretas : brancas) = true;
        if (pretas && brancas) return Acorde { raiz, "m7", -1 };
        if (pretas) return Acorde { raiz, "m", -1 };
        if (brancas) return Acorde { raiz, "7", -1 };
        return Acorde { raiz, "", -1 };
    }

    std::set<int> pcs;
    for (int n : notas) pcs.insert (mod12 (n));
    int notaBaixo = mod12 (notas.front());
    if (pcs.size() == 1) return Acorde { notaBaixo, "", -1 };
    if (pcs.size() == 2)
    {
        std::vector<int> v (pcs.begin(), pcs.end());
        std::sort (v.begin(), v.end(), [&] (int x, int y) { return mod12 (x - notaBaixo) < mod12 (y - notaBaixo); });
        int a = v[0], b = v[1];
        if (mod12 (b - a) == 7) return Acorde { a, "", -1 };
        if (mod12 (a - b) == 7) return Acorde { b, "", notaBaixo };
    }

    using Chave = std::tuple<int, int, int>;   // (faltando, raiz != baixo, preferência)
    std::optional<std::pair<Chave, Acorde>> exato, parcial;
    const auto& t = tipos();
    for (int raiz : pcs)
    {
        std::set<int> rel;
        for (int p : pcs) rel.insert (mod12 (p - raiz));
        for (size_t k = 0; k < t.size(); ++k)
        {
            std::set<int> conj;
            for (int i : t[k].second) conj.insert (mod12 (i));
            int baixo = notaBaixo != raiz ? notaBaixo : -1;
            Acorde ac { raiz, t[k].first, baixo };
            if (rel == conj)
            {
                Chave c { 0, raiz != notaBaixo, (int) k };
                if (! exato || c < exato->first) exato = std::make_pair (c, ac);
            }
            else if (std::includes (conj.begin(), conj.end(), rel.begin(), rel.end()))
            {
                Chave c { (int) (conj.size() - rel.size()), raiz != notaBaixo, (int) k };
                if (! parcial || c < parcial->first) parcial = std::make_pair (c, ac);
            }
        }
    }
    if (exato) return exato->second;
    if (parcial) return parcial->second;
    return std::nullopt;
}

static int papel (int pcFonte, const Acorde& alvo, bool soNotasDoAcorde)
{
    int t = alvo.terca(), q = alvo.quinta(), s = alvo.setima();
    auto mapa = [&] (int pc) -> int {
        switch (pc) { case 0: return 0; case 4: return t; case 7: return q; case 11: return s >= 0 ? s : 12; default: return -999; }
    };
    if (int m = mapa (pcFonte); m != -999) return m;
    if (soNotasDoAcorde)
    {
        std::vector<int> c { 0, t, q };
        if (s >= 0) c.push_back (s);
        return *std::min_element (c.begin(), c.end(), [&] (int x, int y) {
            return std::make_pair (std::abs (x - pcFonte), x) < std::make_pair (std::abs (y - pcFonte), y);
        });
    }
    bool menor = t == 3;
    if (pcFonte == 2) return 2;
    if (pcFonte == 5) return 5;
    if (pcFonte == 9) return (alvo.tem (9) || ! menor) ? 9 : 8;
    int ancora = 0, melhor = 99;
    for (int a : { 0, 4, 7, 11 })                 // mesma ordem do dict do Python: empate fica com o primeiro
        if (std::abs (a - pcFonte) < melhor) { melhor = std::abs (a - pcFonte); ancora = a; }
    return mapa (ancora) + (pcFonte - ancora);
}

int transporNota (int nota, Regra regra, int lo, int hi, const Acorde& alvo)
{
    if (regra == Regra::Bypass) return nota;
    int pc = nota % 12;
    int raiz = alvo.fundamental;

    if (regra == Regra::Fundamental || regra == Regra::Melodia)
    {
        int intervalo = papel (pc, alvo, false);
        if (regra == Regra::Fundamental && pc == 0 && alvo.baixo >= 0) intervalo = mod12 (alvo.baixo - raiz);
        int desloc = raiz <= 6 ? raiz : raiz - 12;
        int nova = nota + desloc + (intervalo - pc);
        while (nova > hi && nova - 12 >= 0) nova -= 12;
        while (nova < lo && nova + 12 <= 127) nova += 12;
        return nova;
    }
    // Acorde: troca de voz e escolhe a oitava mais próxima (faixa com folga de 4 semitons)
    int pcAlvo = mod12 (raiz + papel (pc, alvo, true));
    std::vector<int> opcoes, dentro;
    for (int o = 0; o < 11; ++o)
        if (o * 12 + pcAlvo <= 127) opcoes.push_back (o * 12 + pcAlvo);
    for (int n : opcoes)
        if (n >= lo - 4 && n <= hi + 4) dentro.push_back (n);
    const auto& lista = dentro.empty() ? opcoes : dentro;
    return *std::min_element (lista.begin(), lista.end(), [&] (int x, int y) {
        return std::make_pair (std::abs (x - nota), x) < std::make_pair (std::abs (y - nota), y);
    });
}

std::string nomeNota (int n) { return std::string (NOMES[mod12 (n)]) + std::to_string (n / 12 - 1); }
} // namespace er
