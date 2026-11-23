#include "Ritmo.h"
#include <juce_core/juce_core.h>
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

const Secao& Ritmo::secao (const std::string& n) const
{
    static const Secao vazia {};
    auto it = secoes.find (n);
    return it == secoes.end() ? vazia : it->second;
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
                {
                    std::vector<Nota> notas;
                    if (auto* arr = kv.value.getArray())
                        for (auto& n : *arr)
                            if (auto* q = n.getArray(); q != nullptr && q->size() == 4)
                                notas.push_back ({ (int) (*q)[0], (int) (*q)[1], (int) (*q)[2], (int) (*q)[3] });
                    s.pistas.emplace_back (kv.name.toString().getIntValue(), std::move (notas));
                }
        }
        r->secoes[nome] = std::move (s);
    }
    return r;
}
} // namespace er
