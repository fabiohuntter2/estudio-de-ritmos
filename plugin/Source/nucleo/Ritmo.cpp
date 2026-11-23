#include "Ritmo.h"
#include <juce_core/juce_core.h>
#include <algorithm>
#include <stdexcept>

namespace er
{
const std::vector<std::string>& nomesSecoes()
{
    static const std::vector<std::string> n = { "Intro A", "Intro B", "Intro C", "Var A", "Var B", "Var C", "Var D",
                                                "Fill A", "Fill B", "Fill C", "Fill D", "Break",
                                                "Final A", "Final B", "Final C" };
    return n;
}

std::vector<ConfigPista> pistasPadrao()
{
    auto p = [] (const char* nome, int canal, Regra r, int lo, int hi, int prog, double vol) {
        ConfigPista c;
        c.nome = juce::String::fromUTF8 (nome).toStdString();
        c.canal = canal; c.regra = r; c.lo = lo; c.hi = hi; c.programa = prog; c.volume = vol;
        return c;
    };
    return { p ("Rhythm 1 (Percuss\xc3\xa3o)", 8, Regra::Bypass, 0, 127, -1, 0.8),
             p ("Rhythm 2 (Bateria)", 9, Regra::Bypass, 0, 127, -1, 0.8),
             p ("Bass (Baixo)", 10, Regra::Fundamental, 28, 52, 33, 0.8),
             p ("Chord 1 (Viol\xc3\xa3o)", 11, Regra::Acorde, 52, 76, 25, 0.8),
             p ("Chord 2 (Piano)", 12, Regra::Acorde, 55, 84, 0, 0.6),
             p ("Pad (Cordas)", 13, Regra::Acorde, 48, 79, 48, 0.5),
             p ("Phrase 1 (Sanfona)", 14, Regra::Melodia, 60, 88, 21, 0.7),
             p ("Phrase 2 (Metais)", 15, Regra::Melodia, 55, 84, 61, 0.6) };
}

bool Camada::tipoMudo (const std::string& t) const
{
    return std::find (tiposMudos.begin(), tiposMudos.end(), t) != tiposMudos.end();
}

bool Camada::raizMuda (int r) const
{
    return std::find (raizesMudas.begin(), raizesMudas.end(), r) != raizesMudas.end();
}

bool Secao::vazia() const
{
    for (auto& p : pistas) if (! p.second.empty()) return false;
    for (auto& c : camadas) if (! c.notas.empty()) return false;
    return true;
}

std::vector<Nota>& Secao::notasDaPista (int pista)
{
    for (auto& p : pistas) if (p.first == pista) return p.second;
    pistas.emplace_back (pista, std::vector<Nota>());
    return pistas.back().second;
}

bool Secao::camadaToca (const Camada& cam, const Acorde& ac) const
{
    if (cam.raizMuda (ac.fundamental)) return false;
    if (! cam.tipoMudo (ac.tipo)) return true;
    std::vector<const Camada*> irmas;
    for (auto& c : camadas)
        if (c.pista == cam.pista && ! c.raizMuda (ac.fundamental)) irmas.push_back (&c);
    for (auto* c : irmas)
        if (! c->tipoMudo (ac.tipo)) return false;
    bool menor = ac.terca() == 3;
    for (auto* c : irmas)
        if ((c->fonte.terca() == 3) == menor) return c == &cam;
    return ! irmas.empty() && irmas.front() == &cam;
}

void Ritmo::definirCompasso (int num, int den)
{
    compassoNum = num;
    compassoDen = den;
    for (auto& [n, s] : secoes) s.tc = ticksCompasso();
}

const Secao& Ritmo::secao (const std::string& n) const
{
    static const Secao vazia {};
    auto it = secoes.find (n);
    return it == secoes.end() ? vazia : it->second;
}

static std::vector<Nota> lerNotas (const juce::var& v)
{
    std::vector<Nota> notas;
    if (auto* arr = v.getArray())
        for (auto& n : *arr)
            if (auto* q = n.getArray(); q != nullptr && q->size() == 4)
                notas.push_back ({ (int) (*q)[0], (int) (*q)[1], (int) (*q)[2], (int) (*q)[3] });
    return notas;
}

std::shared_ptr<Ritmo> Ritmo::deJson (const std::string& texto)
{
    juce::var raiz;
    auto res = juce::JSON::parse (juce::String::fromUTF8 (texto.c_str()), raiz);
    if (res.failed() || ! raiz.isObject())
        throw std::runtime_error ("Arquivo de ritmo inválido: " + res.getErrorMessage().toStdString());

    auto r = std::make_shared<Ritmo>();
    r->nome = raiz.getProperty ("nome", "Sem nome").toString().toStdString();
    r->bpm = (double) raiz.getProperty ("bpm", 120.0);
    if (auto* c = raiz.getProperty ("compasso", {}).getArray(); c != nullptr && c->size() == 2)
    {
        r->compassoNum = juce::jmax (1, (int) (*c)[0]);
        r->compassoDen = juce::jmax (1, (int) (*c)[1]);
    }

    auto* pistas = raiz.getProperty ("pistas", {}).getArray();
    if (pistas == nullptr || pistas->size() != 8)
        throw std::runtime_error ("O ritmo precisa ter 8 pistas.");
    for (auto& p : *pistas)
    {
        ConfigPista c;
        c.nome = p.getProperty ("nome", "").toString().toStdString();
        c.canal = juce::jlimit (0, 15, (int) p.getProperty ("canal", 0));
        c.regra = regraDeTexto (p.getProperty ("regra", "bypass").toString().toStdString());
        if (auto* f = p.getProperty ("faixa", {}).getArray(); f != nullptr && f->size() == 2)
        {
            c.lo = (int) (*f)[0];
            c.hi = (int) (*f)[1];
        }
        auto prog = p.getProperty ("programa", {});
        c.programa = prog.isVoid() || prog.isUndefined() ? -1 : (int) prog;
        c.volume = (double) p.getProperty ("volume", 0.8);
        c.mudo = (bool) p.getProperty ("mudo", false);
        if (auto* m = p.getProperty ("mapa", {}).getDynamicObject())
            for (auto& kv : m->getProperties())
                c.mapa[kv.name.toString().getIntValue()] = (int) kv.value;
        r->pistas.push_back (std::move (c));
    }

    auto secs = raiz.getProperty ("secoes", {});
    for (auto& nome : nomesSecoes())
    {
        Secao s;
        auto sv = secs.getProperty (juce::Identifier (juce::String (nome)), {});
        if (sv.isObject())
        {
            s.compassos = juce::jmax (1, (int) sv.getProperty ("compassos", 1));
            if (auto* obj = sv.getProperty ("pistas", {}).getDynamicObject())
                for (auto& kv : obj->getProperties())
                    s.pistas.emplace_back (kv.name.toString().getIntValue(), lerNotas (kv.value));
            if (auto* cams = sv.getProperty ("camadas", {}).getArray())
                for (auto& cv : *cams)
                {
                    Camada c;
                    c.pista = juce::jlimit (0, 7, (int) cv.getProperty ("pista", 0));
                    c.notas = lerNotas (cv.getProperty ("notas", {}));
                    c.regra = regraDeTexto (cv.getProperty ("regra", "bypass").toString().toStdString());
                    if (auto* f = cv.getProperty ("faixa", {}).getArray(); f != nullptr && f->size() == 2)
                    {
                        c.lo = (int) (*f)[0];
                        c.hi = (int) (*f)[1];
                    }
                    if (auto* f = cv.getProperty ("fonte", {}).getArray(); f != nullptr && f->size() == 2)
                        c.fonte = Acorde { (int) (*f)[0], (*f)[1].toString().toStdString(), -1 };
                    c.teclaAlta = (int) cv.getProperty ("tecla_alta", TECLA_ALTA_PADRAO);
                    if (auto* t = cv.getProperty ("tipos_mudos", {}).getArray())
                        for (auto& x : *t) c.tiposMudos.push_back (x.toString().toStdString());
                    if (auto* t = cv.getProperty ("raizes_mudas", {}).getArray())
                        for (auto& x : *t) c.raizesMudas.push_back ((int) x);
                    c.nome = cv.getProperty ("nome", "").toString().toStdString();
                    s.camadas.push_back (std::move (c));
                }
        }
        r->secoes[nome] = std::move (s);
    }
    r->definirCompasso (r->compassoNum, r->compassoDen);
    return r;
}
} // namespace er
