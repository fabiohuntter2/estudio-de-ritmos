#include "EstiloYamaha.h"
#include <algorithm>
#include <cctype>
#include <cmath>
#include <map>
#include <set>
#include <tuple>

namespace er
{
namespace
{
using Bytes = std::vector<uint8_t>;

const std::vector<std::pair<std::string, std::string>>& yamahaParaSecao()
{
    static const std::vector<std::pair<std::string, std::string>> m = {
        { "Intro A", "Intro A" }, { "Intro B", "Intro B" }, { "Intro C", "Intro C" },
        { "Main A", "Var A" }, { "Main B", "Var B" }, { "Main C", "Var C" }, { "Main D", "Var D" },
        { "Fill In AA", "Fill A" }, { "Fill In BB", "Fill B" }, { "Fill In CC", "Fill C" }, { "Fill In DD", "Fill D" },
        { "Fill In BA", "Break" },
        { "Ending A", "Final A" }, { "Ending B", "Final B" }, { "Ending C", "Final C" } };
    return m;
}

std::string codigoParaTipo (int c)
{
    static const std::map<int, std::string> m = {
        { 0x00, "" }, { 0x01, "6" }, { 0x02, "maj7" }, { 0x03, "maj7" }, { 0x04, "add9" }, { 0x05, "maj7" }, { 0x06, "6" },
        { 0x07, "aug" }, { 0x08, "m" }, { 0x09, "m6" }, { 0x0A, "m7" }, { 0x0B, "m7b5" }, { 0x0C, "m" }, { 0x0D, "m9" },
        { 0x0E, "m7" }, { 0x0F, "mmaj7" }, { 0x10, "mmaj7" }, { 0x11, "dim" }, { 0x12, "dim7" }, { 0x13, "7" },
        { 0x14, "7sus4" }, { 0x15, "7" }, { 0x16, "9" }, { 0x17, "7" }, { 0x18, "7" }, { 0x19, "7" }, { 0x1A, "7" },
        { 0x1B, "7" }, { 0x1C, "maj7" }, { 0x1D, "7" }, { 0x1E, "" }, { 0x1F, "" }, { 0x20, "sus4" }, { 0x21, "sus2" } };
    auto it = m.find (c);
    return it == m.end() ? "maj7" : it->second;
}

// Ordem igual ao dict TIPO_PARA_CODIGO do Python
const std::vector<std::pair<std::string, int>>& tipoParaCodigo()
{
    static const std::vector<std::pair<std::string, int>> v = {
        { "", 0x00 }, { "6", 0x01 }, { "maj7", 0x02 }, { "add9", 0x04 }, { "aug", 0x07 }, { "m", 0x08 }, { "m6", 0x09 },
        { "m7", 0x0A }, { "m7b5", 0x0B }, { "m9", 0x0D }, { "mmaj7", 0x0F }, { "dim", 0x11 }, { "dim7", 0x12 },
        { "7", 0x13 }, { "7sus4", 0x14 }, { "9", 0x16 }, { "sus4", 0x20 }, { "sus2", 0x21 } };
    return v;
}

struct Bloco { std::string tipo; Bytes corpo; };

std::vector<Bloco> blocos (const Bytes& d)
{
    std::vector<Bloco> out;
    size_t i = 0;
    while (i + 8 <= d.size())
    {
        std::string tipo (d.begin() + (long) i, d.begin() + (long) i + 4);
        uint32_t tam = ((uint32_t) d[i + 4] << 24) | ((uint32_t) d[i + 5] << 16) | ((uint32_t) d[i + 6] << 8) | d[i + 7];
        size_t ini = i + 8, fim = std::min (d.size(), ini + (size_t) tam);
        out.push_back ({ tipo, Bytes (d.begin() + (long) ini, d.begin() + (long) fim) });
        i += 8 + (size_t) tam;
    }
    return out;
}

std::pair<uint32_t, size_t> varlen (const Bytes& d, size_t i)
{
    uint32_t v = 0;
    for (int k = 0; k < 4; ++k)
    {
        if (i >= d.size()) break;
        uint8_t b = d[i++];
        v = (v << 7) | (b & 0x7F);
        if (! (b & 0x80)) break;
    }
    return { v, i };
}

std::string latin1Strip (const Bytes& d, size_t a, size_t b)
{
    std::string s (d.begin() + (long) a, d.begin() + (long) std::min (b, d.size()));
    auto esp = [] (unsigned char c) { return c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\v' || c == '\f'; };
    while (! s.empty() && esp ((unsigned char) s.back())) s.pop_back();
    while (! s.empty() && esp ((unsigned char) s.front())) s.erase (s.begin());
    return s;
}

struct Ev
{
    long long t;
    enum Tipo { On, Off, Pc, Cc, Marcador, Tempo, Compasso, Nome, Fim } tipo;
    int canal = 0, a = 0, b = 0;
    std::string texto;
};

std::vector<Ev> lerTrilha (const Bytes& d)
{
    std::vector<Ev> ev;
    size_t i = 0;
    long long t = 0;
    int status = 0;
    while (i < d.size())
    {
        auto [delta, j] = varlen (d, i);
        i = j;
        t += delta;
        if (i >= d.size()) break;
        uint8_t b = d[i];
        if (b & 0x80) { status = b; ++i; }
        if (status == 0xFF)
        {
            if (i >= d.size()) break;
            int tipoMeta = d[i++];
            auto [tam, k] = varlen (d, i);
            i = k;
            size_t ini = i;
            i += tam;
            status = 0;
            if (tipoMeta == 0x06) { Ev e { t, Ev::Marcador }; e.texto = latin1Strip (d, ini, ini + tam); ev.push_back (e); }
            else if (tipoMeta == 0x51 && tam == 3 && ini + 2 < d.size())
                ev.push_back ({ t, Ev::Tempo, 0, (d[ini] << 16) | (d[ini + 1] << 8) | d[ini + 2], 0 });
            else if (tipoMeta == 0x58 && tam >= 2 && ini + 1 < d.size())
                ev.push_back ({ t, Ev::Compasso, 0, d[ini], 1 << d[ini + 1] });
            else if (tipoMeta == 0x03) { Ev e { t, Ev::Nome }; e.texto = latin1Strip (d, ini, ini + tam); ev.push_back (e); }
            else if (tipoMeta == 0x2F) { ev.push_back ({ t, Ev::Fim }); break; }
        }
        else if (status == 0xF0 || status == 0xF7)
        {
            auto [tam, k] = varlen (d, i);
            i = k + tam;
            status = 0;
        }
        else
        {
            int alto = status & 0xF0, canal = status & 0x0F;
            if (alto == 0xC0 || alto == 0xD0)
            {
                if (i >= d.size()) break;
                int a = d[i++];
                if (alto == 0xC0) ev.push_back ({ t, Ev::Pc, canal, a, 0 });
            }
            else if (alto == 0x80 || alto == 0x90 || alto == 0xA0 || alto == 0xB0 || alto == 0xE0)
            {
                if (i + 1 >= d.size()) break;
                int a = d[i], b2 = d[i + 1];
                i += 2;
                if (alto == 0x90 && b2 > 0) ev.push_back ({ t, Ev::On, canal, a, b2 });
                else if (alto == 0x80 || alto == 0x90) ev.push_back ({ t, Ev::Off, canal, a, 0 });
                else if (alto == 0xB0) ev.push_back ({ t, Ev::Cc, canal, a, b2 });
            }
            else
                throw ErroEstilo ("MIDI inválido perto do byte " + std::to_string (i));
        }
    }
    return ev;
}

struct Zona { int a, b, ntr, tabela; bool baixo; int hk, lo, hi; };

struct Tab
{
    int origem = 0, destino = 0;
    std::string nome;
    bool raizesTocam[12] = { true, true, true, true, true, true, true, true, true, true, true, true };
    std::set<int> codigosMudos;
    int fonteRaiz = 0, fonteCodigo = 0x02;
    std::vector<Zona> zonas;
};

Tab lerTab (const Bytes& d, bool ctb2)
{
    Tab t;
    t.origem = d[0] & 0x0F;
    t.nome = latin1Strip (d, 1, 9);
    t.destino = d[9] & 0x0F;
    for (int r = 0; r < 12; ++r)
    {
        int byte = r < 8 ? d[12] : d[11], bit = r < 8 ? r : r - 8;
        t.raizesTocam[r] = (byte >> bit) & 1;
    }
    for (int c = 0; c < 0x22; ++c)
        if (! ((d[(size_t) (17 - c / 8)] >> (c % 8)) & 1)) t.codigosMudos.insert (c);
    t.fonteRaiz = d[18] % 12;
    t.fonteCodigo = d[19];
    if (! ctb2)
    {
        int ntr = d[20], ntt = d[21];
        int tabela = 3; bool baixo = false;
        if (ntt == 0) tabela = 0;
        else if (ntt == 1) tabela = 1;
        else if (ntt == 2) tabela = 2;
        else if (ntt == 3) { tabela = 1; baixo = true; }
        t.zonas.push_back ({ 0, 127, ntr, tabela, baixo, d[22] % 12, d[23], d[24] });
    }
    else
    {
        int midLo = d[20], midHi = d[21];
        int faixas[3][2] = { { 0, midLo - 1 }, { midLo, midHi }, { midHi + 1, 127 } };
        for (int z = 0; z < 3; ++z)
        {
            if (faixas[z][0] > faixas[z][1]) continue;
            size_t o = (size_t) (22 + 6 * z);
            int ntr = d[o], ntt = d[o + 1];
            t.zonas.push_back ({ faixas[z][0], faixas[z][1], ntr, ntt & 0x7F, (ntt & 0x80) != 0, d[o + 2] % 12, d[o + 3], d[o + 4] });
        }
    }
    return t;
}

struct Seg { std::vector<std::string> nomes; std::map<int, Tab> tabs; };

std::vector<Seg> lerCasm (const Bytes& d)
{
    std::vector<Seg> segs;
    for (auto& b : blocos (d))
    {
        if (b.tipo != "CSEG") continue;
        Seg seg;
        std::vector<std::pair<int, int>> cntt;     // ordem de inserção (dict do Python)
        for (auto& b2 : blocos (b.corpo))
        {
            if (b2.tipo == "Sdec")
            {
                std::string s (b2.corpo.begin(), b2.corpo.end());
                size_t p = 0;
                while (true)
                {
                    size_t q = s.find (',', p);
                    seg.nomes.push_back (latin1Strip (Bytes (s.begin() + (long) p, q == std::string::npos ? s.end() : s.begin() + (long) q), 0, 1u << 30));
                    if (q == std::string::npos) break;
                    p = q + 1;
                }
            }
            else if ((b2.tipo == "Ctab" && b2.corpo.size() >= 25) || (b2.tipo == "Ctb2" && b2.corpo.size() >= 40))
            {
                Tab tab = lerTab (b2.corpo, b2.tipo == "Ctb2");
                seg.tabs[tab.origem] = tab;
            }
            else if (b2.tipo == "Cntt" && b2.corpo.size() >= 2)
            {
                int ch = b2.corpo[0] & 0x0F;
                auto it = std::find_if (cntt.begin(), cntt.end(), [&] (auto& kv) { return kv.first == ch; });
                if (it != cntt.end()) it->second = b2.corpo[1];
                else cntt.push_back ({ ch, b2.corpo[1] });
            }
        }
        for (auto& [ch, v] : cntt)
        {
            auto it = seg.tabs.find (ch);
            if (it != seg.tabs.end() && it->second.zonas.size() == 1)
            {
                auto& z = it->second.zonas[0];
                z.tabela = v & 0x7F;
                z.baixo = z.baixo || (v & 0x80);
            }
        }
        segs.push_back (std::move (seg));
    }
    return segs;
}

Regra regraDe (int ntr, int tabela, bool baixo, bool bateria)
{
    if (bateria) return Regra::Bypass;
    if (ntr == 2) return Regra::Acorde;
    if (baixo && tabela != 2) return Regra::Fundamental;
    if (tabela == 0) return ntr == 1 ? Regra::Bypass : Regra::Melodia;
    if (tabela == 2) return Regra::Acorde;
    return Regra::Melodia;
}

Tab tabPadrao (int ch, const std::vector<ConfigPista>& padrao)
{
    Tab t;
    t.origem = t.destino = ch;
    const auto& cfg = padrao[(size_t) (ch - 8)];
    int tabela = 1, ntr = 0; bool baixo = false;
    switch (cfg.regra)
    {
        case Regra::Bypass: tabela = 0; ntr = 1; break;
        case Regra::Fundamental: tabela = 1; baixo = true; ntr = 0; break;
        case Regra::Acorde: tabela = 2; ntr = 1; break;
        case Regra::Melodia: tabela = 1; ntr = 0; break;
    }
    t.zonas.push_back ({ 0, 127, ntr, tabela, baixo, TECLA_ALTA_PADRAO, cfg.lo, cfg.hi });
    return t;
}

std::string minusculasEspacos (std::string m)
{
    for (auto& c : m)
    {
        c = (char) std::tolower ((unsigned char) c);
        if (c == '_' || c == '-') c = ' ';
    }
    std::string out;
    bool esp = true;
    for (char c : m)
    {
        if (std::isspace ((unsigned char) c)) { if (! esp) out += ' '; esp = true; }
        else { out += c; esp = false; }
    }
    while (! out.empty() && out.back() == ' ') out.pop_back();
    return out;
}
} // namespace

std::optional<std::string> normalizarSecao (const std::string& marcador)
{
    for (auto& [y, s] : yamahaParaSecao())
        if (y == marcador) return s;
    std::string m = minusculasEspacos (marcador);
    if (m == "break" || m == "fill in ba" || m == "fill ba") return std::string ("Break");
    struct Grupo { std::vector<std::string> prefixos; std::string destino, letras; };
    static const std::vector<Grupo> grupos = {
        { { "intro ", "intro" }, "Intro", "abc123" },
        { { "main ", "variation ", "var ", "var", "variation" }, "Var", "abcd1234" },
        { { "fill in ", "fill ", "fill" }, "Fill", "abcd1234" },
        { { "ending ", "ending", "end ", "final " }, "Final", "abc123" } };
    static const std::map<char, char> letra = { { 'a', 'A' }, { 'b', 'B' }, { 'c', 'C' }, { 'd', 'D' },
                                                { '1', 'A' }, { '2', 'B' }, { '3', 'C' }, { '4', 'D' } };
    for (auto& g : grupos)
        for (auto& p : g.prefixos)
            if (m.rfind (p, 0) == 0)
            {
                std::string resto = m.substr (p.size());
                while (! resto.empty() && resto.front() == ' ') resto.erase (resto.begin());
                while (! resto.empty() && resto.back() == ' ') resto.pop_back();
                if (resto.size() == 2 && resto[0] == resto[1]) resto = resto.substr (0, 1);
                if (resto.size() == 1 && g.letras.find (resto[0]) != std::string::npos)
                    return g.destino + " " + std::string (1, letra.at (resto[0]));
            }
    return std::nullopt;
}

bool pareceEstilo (const Bytes& d)
{
    return d.size() >= 4 && d[0] == 'M' && d[1] == 'T' && d[2] == 'h' && d[3] == 'd';
}

static std::string mensagemKorg (const Bytes& d)
{
    size_t oc31 = 0;
    for (size_t i = 0; i + 4 <= d.size(); ++i)
        if (d[i] == 'O' && d[i + 1] == 'C' && d[i + 2] == '3' && d[i + 3] == '1') ++oc31;
    return std::string ("Este arquivo parece um banco de estilos Korg Pa, um formato fechado da Korg")
        + (oc31 ? " e comprimido" : "") + ". Ainda nao e possivel abri-lo diretamente. Hoje funcionam: estilos "
          "Korg convertidos para Yamaha (.sty) e estilos gravados em MIDI no teclado (modo Sequencer). "
          "Mande este arquivo para analise: ele ajuda a decifrar o formato.";
}

std::shared_ptr<Ritmo> lerSty (const Bytes& dados, const std::string& nomeArquivo)
{
    if (! pareceEstilo (dados)) throw ErroEstilo (mensagemKorg (dados));
    auto bl = blocos (dados);
    if (bl.empty() || bl[0].corpo.size() < 6) throw ErroEstilo ("Cabeçalho MIDI inválido.");
    int div = (bl[0].corpo[4] << 8) | bl[0].corpo[5];
    if ((div & 0x8000) || div == 0) throw ErroEstilo ("Divisão de tempo SMPTE não suportada.");
    const Bytes* trilha = nullptr;
    const Bytes* casm = nullptr;
    for (auto& b : bl)
    {
        if (b.tipo == "MTrk" && trilha == nullptr) trilha = &b.corpo;
        if (b.tipo == "CASM" && casm == nullptr) casm = &b.corpo;
    }
    if (trilha == nullptr) throw ErroEstilo ("Estilo sem trilha MIDI.");
    auto segs = casm ? lerCasm (*casm) : std::vector<Seg>();
    auto ev = lerTrilha (*trilha);

    auto conv = [div] (long long tick) { return (tick * PPQ + div / 2) / div; };
    double bpm = 120.0;
    int num = 4, den = 4;
    std::string nomeTrilha;
    for (auto& e : ev)
    {
        if (e.tipo == Ev::Tempo && bpm == 120.0 && e.a > 0) bpm = std::round (60000000.0 / e.a * 100.0) / 100.0;
        else if (e.tipo == Ev::Compasso && num == 4 && den == 4) { num = e.a; den = e.b; }
        else if (e.tipo == Ev::Nome && nomeTrilha.empty() && e.t == 0) nomeTrilha = e.texto;
    }
    const int tc = ticksDoCompasso (num, den);
    long long fimTrilha = 0;
    for (auto& e : ev) fimTrilha = std::max (fimTrilha, e.t);

    struct Trecho { std::string nome; long long ini, fim; };
    std::vector<std::pair<long long, std::string>> marcadores;
    for (auto& e : ev) if (e.tipo == Ev::Marcador) marcadores.push_back ({ e.t, e.texto });
    std::vector<Trecho> trechos;
    for (size_t k = 0; k < marcadores.size(); ++k)
        trechos.push_back ({ marcadores[k].second, marcadores[k].first,
                             k + 1 < marcadores.size() ? marcadores[k + 1].first : fimTrilha });
    long long inicioSint = 0, fimSint = 0;
    for (auto& t : trechos) if (t.nome == "SInt") { inicioSint = t.ini; break; }
    for (auto& t : trechos) if (t.nome == "SInt") { fimSint = t.fim; break; }

    struct NotaBruta { long long on, off; bool temOff; int c, n, v; };
    std::vector<NotaBruta> brutas;
    std::map<std::pair<int, int>, std::vector<size_t>> abertas;
    for (auto& e : ev)
    {
        if (e.tipo == Ev::On)
        {
            abertas[{ e.canal, e.a }].push_back (brutas.size());
            brutas.push_back ({ e.t, 0, false, e.canal, e.a, e.b });
        }
        else if (e.tipo == Ev::Off)
        {
            auto& fila = abertas[{ e.canal, e.a }];
            if (! fila.empty())
            {
                brutas[fila.front()].off = e.t;
                brutas[fila.front()].temOff = true;
                fila.erase (fila.begin());
            }
        }
    }

    auto r = std::make_shared<Ritmo>();
    r->nome = ! nomeArquivo.empty() ? nomeArquivo : (! nomeTrilha.empty() ? nomeTrilha : "Estilo Yamaha");
    r->bpm = bpm;
    r->pistas = pistasPadrao();
    for (auto& n : nomesSecoes()) r->secoes[n] = Secao();
    r->definirCompasso (num, den);
    const auto padrao = pistasPadrao();

    auto tabsDaSecao = [&] (const std::string& nomeY) -> const std::map<int, Tab>* {
        for (auto& s : segs)
            if (std::find (s.nomes.begin(), s.nomes.end(), nomeY) != s.nomes.end()) return &s.tabs;
        return segs.empty() ? nullptr : &segs[0].tabs;
    };
    auto tabOuPadrao = [&] (const std::map<int, Tab>* tabs, int ch) -> std::optional<Tab> {
        if (! segs.empty())
        {
            if (tabs != nullptr) { auto it = tabs->find (ch); if (it != tabs->end()) return it->second; }
            return std::nullopt;
        }
        if (ch >= 8 && ch <= 15) return tabPadrao (ch, padrao);
        return std::nullopt;
    };

    bool cfgDefinida[8] = {};
    std::set<std::string> jaLidas;
    for (auto& tr : trechos)
    {
        auto secaoOpt = normalizarSecao (tr.nome);
        if (! secaoOpt || jaLidas.count (*secaoOpt)) continue;
        const std::string secao = *secaoOpt;
        jaLidas.insert (secao);
        Secao& sec = r->secoes[secao];
        sec.compassos = (int) std::max<long long> (1, (conv (tr.fim) - conv (tr.ini) + tc / 2) / tc);
        auto* tabs = tabsDaSecao (tr.nome);
        std::map<int, std::vector<Nota>> porCanal;
        for (auto& nb : brutas)
            if (tr.ini <= nb.on && nb.on < tr.fim)
            {
                long long d = (nb.temOff ? conv (nb.off) : conv (tr.fim)) - conv (nb.on);
                porCanal[nb.c].push_back ({ (int) (conv (nb.on) - conv (tr.ini)), (int) std::max<long long> (1, d), nb.n, nb.v });
            }
        for (auto& [ch, notasCanal] : porCanal)
        {
            auto tab = tabOuPadrao (tabs, ch);
            if (! tab || tab->destino < 8 || tab->destino > 15) continue;
            int pista = tab->destino - 8;
            bool bateria = tab->destino == 8 || tab->destino == 9;
            std::vector<std::string> tiposMudos;
            for (auto& [tp, cod] : tipoParaCodigo())
                if (tab->codigosMudos.count (cod)) tiposMudos.push_back (tp);
            std::vector<int> raizesMudas;
            for (int x = 0; x < 12; ++x) if (! tab->raizesTocam[x]) raizesMudas.push_back (x);
            for (auto& z : tab->zonas)
            {
                std::vector<Nota> notas;
                for (auto& n : notasCanal) if (z.a <= n.nota && n.nota <= z.b) notas.push_back (n);
                if (notas.empty()) continue;
                int lo = z.lo, hi = z.hi;
                if (! (lo < hi)) { lo = 0; hi = 127; }
                Camada cam;
                cam.pista = pista; cam.notas = notas; cam.regra = regraDe (z.ntr, z.tabela, z.baixo, bateria);
                cam.lo = lo; cam.hi = hi;
                cam.fonte = Acorde { tab->fonteRaiz, codigoParaTipo (tab->fonteCodigo), -1 };
                cam.teclaAlta = z.hk; cam.tiposMudos = tiposMudos; cam.raizesMudas = raizesMudas; cam.nome = tab->nome;
                if (! cfgDefinida[pista] || secao == "Var A")
                {
                    auto& cfg = r->pistas[(size_t) pista];
                    cfg.regra = cam.regra; cfg.lo = lo; cfg.hi = hi;
                    if (! tab->nome.empty())
                    {
                        auto base = padrao[(size_t) pista].nome;
                        cfg.nome = base.substr (0, base.find (" (")) + " (" + tab->nome + ")";
                    }
                    cfgDefinida[pista] = true;
                }
                sec.camadas.push_back (std::move (cam));
            }
        }
    }

    // camadas "simples" viram notas normais
    for (auto& nome : nomesSecoes())
    {
        Secao& sec = r->secoes[nome];
        std::vector<Camada> resto;
        for (auto& cam : sec.camadas)
        {
            const auto& cfg = r->pistas[(size_t) cam.pista];
            bool simples = cam.tiposMudos.empty() && cam.raizesMudas.empty() && cam.fonte.fundamental == 0
                           && cam.fonte.tipo == "maj7" && cam.teclaAlta == TECLA_ALTA_PADRAO && cam.regra == cfg.regra
                           && cam.lo == cfg.lo && cam.hi == cfg.hi;
            if (simples)
            {
                auto& lista = sec.notasDaPista (cam.pista);
                lista.insert (lista.end(), cam.notas.begin(), cam.notas.end());
                std::stable_sort (lista.begin(), lista.end(), [] (const Nota& a, const Nota& b) {
                    return a.ini != b.ini ? a.ini < b.ini : a.nota < b.nota;
                });
            }
            else resto.push_back (cam);
        }
        sec.camadas = std::move (resto);
    }

    // timbres e volumes da seção SInt
    const std::map<int, Tab> vazio;
    const auto& tabs0 = segs.empty() ? vazio : segs[0].tabs;
    for (auto& e : ev)
    {
        if (! (inicioSint <= e.t && e.t < std::max (fimSint, inicioSint + 1)) || (e.tipo != Ev::Pc && e.tipo != Ev::Cc)) continue;
        auto it = tabs0.find (e.canal);
        int dest = it != tabs0.end() ? it->second.destino : e.canal;
        if (dest < 8 || dest > 15) continue;
        if (e.tipo == Ev::Pc) r->pistas[(size_t) (dest - 8)].programa = e.a;
        else if (e.a == 7) r->pistas[(size_t) (dest - 8)].volume = std::round (e.b / 127.0 * 10000.0) / 10000.0;
    }
    bool algo = false;
    for (auto& [n, s] : r->secoes) algo = algo || ! s.vazia();
    if (! algo) throw ErroEstilo ("Nenhuma seção reconhecida no arquivo (marcadores Intro/Main/Variation/Fill/Ending).");
    return r;
}
} // namespace er
