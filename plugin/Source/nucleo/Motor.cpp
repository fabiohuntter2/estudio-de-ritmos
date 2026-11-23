#include "Motor.h"
#include <algorithm>
#include <set>

namespace er
{
static std::string letra (const std::string& s)
{
    auto p = s.find_last_of (' ');
    return p == std::string::npos ? "A" : s.substr (p + 1);
}
static bool comeca (const std::string& s, const char* p) { return s.rfind (p, 0) == 0; }

void Motor::setRitmo (std::shared_ptr<const Ritmo> r)
{
    parar();
    ritmoAtual = std::move (r);
}

bool Motor::vazia (const std::string& n) const { return ! ritmoAtual || ritmoAtual->vazia (n); }

void Motor::enviar (Evento::Tipo t, int canal, int d1, int d2)
{
    if (saida) saida ({ pos, t, canal, d1, d2 });
}

EstadoMotor Motor::estado() const
{
    EstadoMotor e;
    e.tocando = tocando; e.armado = armado; e.secao = secao; e.var = varAtual; e.intro = introEscolhida;
    e.proxima = fila.empty() ? "" : fila.front();
    e.acorde = acorde ? acorde->nome() : "—";
    long long rel = pos - inicioSecao;
    e.compasso = tocando ? (int) (rel / tc()) + 1 : 0;
    e.tempo = tocando ? (int) ((rel % tc()) / PPQ) + 1 : 0;
    return e;
}

// ---------------------------------------------------------------- comandos
void Motor::iniciar (long long posInicial)
{
    if (tocando || ! ritmoAtual) return;
    armado = false;
    pos = 0;
    fila.clear();
    std::string primeira = varAtual;
    if (! introEscolhida.empty() && ! vazia (introEscolhida))
    {
        primeira = introEscolhida;
        fila = { varAtual };
    }
    for (auto& p : ritmoAtual->pistas)
    {
        if (p.programa >= 0) enviar (Evento::ProgramChange, p.canal, p.programa, 0);
        enviar (Evento::ControlChange, p.canal, 7, (int) (p.volume * 127));
    }
    seqIdx = 0;
    proximoDaSequencia();
    pos = posInicial;
    entrar (primeira, 0, posInicial);
    trocaNoCompasso = false;
    tocando = true;
    introEscolhida.clear();
}

void Motor::parar()
{
    tocando = false;
    armado = false;
    if (ritmoAtual) todasOff();
    secao.clear();
    fila.clear();
}

void Motor::armarSync (bool ligado)
{
    if (! tocando) armado = ligado;
}

void Motor::pedir (const std::string& nome)
{
    if (! ritmoAtual) return;
    if (! tocando)
    {
        if (comeca (nome, "Var")) varAtual = nome;
        else if (comeca (nome, "Intro")) introEscolhida = introEscolhida == nome ? "" : nome;
        return;
    }
    const std::string atual = secao;
    if (comeca (nome, "Var"))
    {
        bool mesma = nome == varAtual;
        varAtual = nome;
        if (comeca (atual, "Fill") || comeca (atual, "Break") || comeca (atual, "Intro"))
        {
            std::vector<std::string> f;
            for (auto& s : fila) if (! comeca (s, "Var")) f.push_back (s);
            f.push_back (nome);
            fila = f;
            return;
        }
        std::string fill = "Fill " + letra (nome);
        if (autoFill && ! vazia (fill)) viradaAgora ({ fill, nome });
        else if (! mesma) { fila = { nome }; trocaNoCompasso = true; }
    }
    else if (comeca (nome, "Fill"))
    {
        std::string fill = nome != "Fill" ? nome : "Fill " + letra (varAtual);
        if (! vazia (fill)) viradaAgora ({ fill, varAtual });
    }
    else if (nome == "Break")
    {
        if (! vazia ("Break")) viradaAgora ({ "Break", varAtual });
    }
    else if (comeca (nome, "Final"))
    {
        if (! vazia (nome)) { fila = { nome }; trocaNoCompasso = true; }
    }
    else if (comeca (nome, "Intro"))
    {
        if (! vazia (nome)) { fila = { nome, varAtual }; trocaNoCompasso = true; }
    }
}

void Motor::viradaAgora (std::vector<std::string> f)
{
    long long rel = pos - inicioSecao;
    long long inicioCompasso = inicioSecao + (rel / tc()) * tc();
    if (pos - inicioCompasso > tc() - PPQ / 2)
    {
        fila = f;
        trocaNoCompasso = true;
        return;
    }
    fila.assign (f.begin() + 1, f.end());
    trocaNoCompasso = false;
    entrar (f.front(), inicioCompasso, pos);
}

bool Motor::definirAcorde (const Acorde& ac)
{
    bool mudou = ! acorde || *acorde != ac;
    acorde = ac;
    if (armado && ! tocando) { iniciar(); return true; }
    if (tocando && mudou) retocar();
    return false;
}

void Motor::definirSequencia (std::vector<Acorde> seq)
{
    sequencia = std::move (seq);
    seqIdx = 0;
}

void Motor::proximoDaSequencia()
{
    if (sequencia.empty()) return;
    const Acorde& ac = sequencia[seqIdx % sequencia.size()];
    ++seqIdx;
    if (! acorde || *acorde != ac)
    {
        acorde = ac;
        retocar();
    }
}

// ---------------------------------------------------------------- núcleo
void Motor::entrar (const std::string& nome, long long inicio, long long aPartir)
{
    secao = nome;
    inicioSecao = inicio;
    eventos.clear();
    const Secao& sec = ritmoAtual->secao (nome);
    for (auto& [i, notas] : sec.pistas)
    {
        if (i < 0 || i >= (int) ritmoAtual->pistas.size()) continue;
        for (auto& n : notas)
            if (n.ini < sec.ticks()) eventos.push_back ({ inicio + n.ini, i, n, nullptr, &sec });
    }
    for (auto& cam : sec.camadas)
    {
        if (cam.pista < 0 || cam.pista >= (int) ritmoAtual->pistas.size()) continue;
        for (auto& n : cam.notas)
            if (n.ini < sec.ticks()) eventos.push_back ({ inicio + n.ini, cam.pista, n, &cam, &sec });
    }
    std::stable_sort (eventos.begin(), eventos.end(), [] (const Agendado& a, const Agendado& b) {
        if (a.tick != b.tick) return a.tick < b.tick;
        if (a.pista != b.pista) return a.pista < b.pista;
        return a.n.nota < b.n.nota;
    });
    if (aPartir < 0) aPartir = inicio;
    evIdx = 0;
    while (evIdx < eventos.size() && eventos[evIdx].tick < aPartir) ++evIdx;
}

int Motor::notaSaida (int pista, int fonte, const Camada* cam) const
{
    const auto& cfg = ritmoAtual->pistas[(size_t) pista];
    const Acorde& ac = acorde ? *acorde : acordePadrao();
    int n = cam == nullptr ? transporNota (fonte, cfg.regra, cfg.lo, cfg.hi, ac)
                           : transporNota (fonte, cam->regra, cam->lo, cam->hi, ac, cam->fonte, cam->teclaAlta);
    return std::clamp (cfg.notaSaida (n), 0, 127);
}

void Motor::ligar (int pista, int fonte, int vel, long long off, const Camada* cam, const Secao* sec)
{
    const auto& cfg = ritmoAtual->pistas[(size_t) pista];
    if (cfg.mudo) return;
    if (cam != nullptr && ! sec->camadaToca (*cam, acorde ? *acorde : acordePadrao())) return;
    int n = notaSaida (pista, fonte, cam);
    auto it = std::find_if (soando.begin(), soando.end(), [&] (const Soando& s) { return s.canal == cfg.canal && s.nota == n; });
    if (it != soando.end()) enviar (Evento::NoteOff, cfg.canal, n, 0);
    enviar (Evento::NoteOn, cfg.canal, n, std::clamp (vel, 1, 127));
    Soando novo { cfg.canal, n, off, pista, fonte, vel, cam, sec };
    if (it != soando.end()) *it = novo;     // mantém a posição (como o dict do Python)
    else soando.push_back (novo);
}

void Motor::desligar (size_t idx)
{
    enviar (Evento::NoteOff, soando[idx].canal, soando[idx].nota, 0);
    soando.erase (soando.begin() + (long) idx);
}

void Motor::todasOff()
{
    while (! soando.empty()) desligar (0);
    std::set<int> canais;
    for (auto& p : ritmoAtual->pistas) canais.insert (p.canal);
    for (int c : canais) enviar (Evento::ControlChange, c, 123, 0);
}

void Motor::retocar()
{
    const Acorde& ac = acorde ? *acorde : acordePadrao();
    auto copia = soando;
    for (auto& s : copia)
    {
        auto achar = [&] { return std::find_if (soando.begin(), soando.end(), [&] (const Soando& x) { return x.canal == s.canal && x.nota == s.nota; }); };
        if (s.cam != nullptr && ! s.sec->camadaToca (*s.cam, ac))
        {
            auto it = achar();                       // camada deixou de valer para este acorde
            if (it != soando.end()) desligar ((size_t) (it - soando.begin()));
            continue;
        }
        Regra regra = s.cam != nullptr ? s.cam->regra : ritmoAtual->pistas[(size_t) s.pista].regra;
        if (regra != Regra::Fundamental && regra != Regra::Acorde) continue;
        auto it = achar();
        if (it == soando.end()) continue;
        desligar ((size_t) (it - soando.begin()));
        if (regra == Regra::Acorde && s.off - pos > SEMI / 2)
            ligar (s.pista, s.fonte, std::max (1, (int) (s.vel * 0.85)), s.off, s.cam, s.sec);
    }
}

void Motor::fronteira (bool fimSecao)
{
    proximoDaSequencia();
    if (! fila.empty() && (fimSecao || trocaNoCompasso))
    {
        std::string prox = fila.front();
        fila.erase (fila.begin());
        while (vazia (prox) && ! fila.empty()) { prox = fila.front(); fila.erase (fila.begin()); }
        if (vazia (prox)) prox = varAtual;
        trocaNoCompasso = false;
        entrar (prox, pos);
    }
    else if (fimSecao)
    {
        if (comeca (secao, "Final"))
        {
            tocando = false;
            todasOff();
            secao.clear();
            return;
        }
        entrar (secao, pos);
    }
}

void Motor::avancar (long long ate)
{
    while (tocando && pos < ate)
    {
        const Secao& sec = ritmoAtual->secao (secao);
        long long fimSecao = inicioSecao + sec.ticks();
        long long rel = pos - inicioSecao;
        long long proxCompasso = inicioSecao + (rel / tc() + 1) * tc();
        long long limite = std::min ({ ate, fimSecao, proxCompasso });

        for (;;)
        {
            long long offTick = -1;
            size_t offIdx = 0;
            for (size_t k = 0; k < soando.size(); ++k)
                if (soando[k].off < limite && (offTick < 0 || soando[k].off < offTick)) { offTick = soando[k].off; offIdx = k; }
            long long onTick = evIdx < eventos.size() ? eventos[evIdx].tick : -1;
            if (onTick >= limite) onTick = -1;
            if (offTick < 0 && onTick < 0) break;
            if (onTick < 0 || (offTick >= 0 && offTick <= onTick))
            {
                pos = std::max (pos, offTick);
                desligar (offIdx);
            }
            else
            {
                const Agendado ag = eventos[evIdx++];
                pos = std::max (pos, ag.tick);
                ligar (ag.pista, ag.n.nota, ag.n.vel, ag.tick + ag.n.dur, ag.cam, ag.sec);
            }
        }
        pos = limite;
        if (pos == proxCompasso || pos == fimSecao) fronteira (pos >= fimSecao);
    }
}
} // namespace er
