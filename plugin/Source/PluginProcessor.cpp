#include "PluginProcessor.h"
#include "PluginEditor.h"
#include "BinaryData.h"
#include "nucleo/EstiloYamaha.h"
#include <cmath>

using namespace er;

// ---------------------------------------------------------------- parâmetros
const juce::StringArray& EstudioRitmosProcessor::nomesSecaoParam()
{
    static const juce::StringArray n { "-", "Intro A", "Intro B", "Intro C", "Var A", "Var B", "Var C", "Var D",
                                       "Fill", "Break", "Final A", "Final B", "Final C" };
    return n;
}

// Teclas de controle no canal MIDI 16 (números MIDI; no Cubase C1 = 36)
const std::map<int, std::string>& EstudioRitmosProcessor::teclasDeControle()
{
    static const std::map<int, std::string> m = {
        { 36, "Intro A" }, { 37, "Intro B" }, { 38, "Intro C" },
        { 40, "Var A" }, { 41, "Var B" }, { 42, "Var C" }, { 43, "Var D" },
        { 45, "Fill" }, { 46, "Break" },
        { 48, "Final A" }, { 49, "Final B" }, { 50, "Final C" },
        { 52, "INICIAR/PARAR" }, { 53, "SYNC" } };
    return m;
}

static juce::StringArray nomesSplit()
{
    juce::StringArray s;
    for (int n = 36; n <= 72; ++n) s.add (juce::String (nomeNota (n)) + " (" + juce::String (n) + ")");
    return s;
}

juce::AudioProcessorValueTreeState::ParameterLayout EstudioRitmosProcessor::criarParametros()
{
    std::vector<std::unique_ptr<juce::RangedAudioParameter>> p;
    p.push_back (std::make_unique<juce::AudioParameterChoice> (juce::ParameterID { "secao", 1 }, "Secao", nomesSecaoParam(), 0));
    p.push_back (std::make_unique<juce::AudioParameterBool> (juce::ParameterID { "autoFill", 1 }, "Auto Fill", true));
    p.push_back (std::make_unique<juce::AudioParameterBool> (juce::ParameterID { "seguirHost", 1 }, "Seguir play do host", true));
    p.push_back (std::make_unique<juce::AudioParameterChoice> (juce::ParameterID { "split", 1 }, "Split", nomesSplit(), 54 - 36));
    p.push_back (std::make_unique<juce::AudioParameterChoice> (juce::ParameterID { "modo", 1 }, "Modo de acorde",
                                                               juce::StringArray { "Fingered", "Single Finger", "Fingered On Bass" }, 0));
    return { p.begin(), p.end() };
}

EstudioRitmosProcessor::EstudioRitmosProcessor()
    : AudioProcessor (BusesProperties().withOutput ("Saida", juce::AudioChannelSet::stereo(), true)),
      parametros (*this, nullptr, "PARAMETROS", criarParametros())
{
    motor.setSaida ([this] (const Evento& e) {
        int s = tps > 0 ? (int) std::floor (((double) e.tick - tickInicio) / tps) : 0;
        s = juce::jlimit (0, juce::jmax (0, nAmostras - 1), juce::jmax (s, amostraAtual));
        juce::MidiMessage m;
        switch (e.tipo)
        {
            case Evento::NoteOn: m = juce::MidiMessage::noteOn (e.canal + 1, e.d1, (juce::uint8) e.d2); break;
            case Evento::NoteOff: m = juce::MidiMessage::noteOff (e.canal + 1, e.d1); break;
            case Evento::ControlChange: m = juce::MidiMessage::controllerEvent (e.canal + 1, e.d1, e.d2); break;
            case Evento::ProgramChange: m = juce::MidiMessage::programChange (e.canal + 1, e.d1); break;
        }
        saidaAtual->addEvent (m, s);
    });
    estado.motor.var = motor.varAtual;
    juce::String erro;
    carregarRitmoDeTexto (juce::String::fromUTF8 (BinaryData::Arrocha_Demo_ritmo, BinaryData::Arrocha_Demo_ritmoSize), erro);
}

bool EstudioRitmosProcessor::isBusesLayoutSupported (const BusesLayout& l) const
{
    auto out = l.getMainOutputChannelSet();
    return out == juce::AudioChannelSet::stereo() || out == juce::AudioChannelSet::mono();
}

void EstudioRitmosProcessor::prepareToPlay (double sampleRate, int)
{
    sr = sampleRate > 0 ? sampleRate : 44100.0;
}

// ---------------------------------------------------------------- ritmo / estado
void EstudioRitmosProcessor::publicarRitmo (std::shared_ptr<er::Ritmo> r, const char* origem)
{
    {
        const juce::ScopedLock sl (lockRitmo);
        ritmoPendente = r;
    }
    const juce::ScopedLock sl (lockEstado);
    estado.nomeRitmo = r->nome;
    estado.erro.clear();
    estado.origem = origem;
    estado.compasso = std::to_string (r->compassoNum) + "/" + std::to_string (r->compassoDen);
    estado.secoesComNotas.clear();
    for (auto& n : nomesSecoes())
        if (! r->vazia (n)) estado.secoesComNotas.push_back (n);
}

bool EstudioRitmosProcessor::carregarRitmoDeTexto (const juce::String& json, juce::String& erro)
{
    try
    {
        auto r = Ritmo::deJson (json.toStdString());
        {
            const juce::ScopedLock sl (lockRitmo);
            ritmoJson = json;
            estiloDados.reset();
            estiloNome.clear();
        }
        publicarRitmo (r, "ritmo");
        return true;
    }
    catch (const std::exception& e)
    {
        erro = juce::String::fromUTF8 (e.what());
        return false;
    }
}

bool EstudioRitmosProcessor::carregarEstilo (const juce::MemoryBlock& dados, const juce::String& nome, juce::String& erro)
{
    try
    {
        std::vector<uint8_t> v ((const uint8_t*) dados.getData(), (const uint8_t*) dados.getData() + dados.getSize());
        auto r = lerSty (v, nome.toStdString());
        {
            const juce::ScopedLock sl (lockRitmo);
            estiloDados = dados;
            estiloNome = nome;
            ritmoJson.clear();
        }
        publicarRitmo (r, "sty");
        return true;
    }
    catch (const std::exception& e)
    {
        erro = juce::String::fromUTF8 (e.what());
        return false;
    }
}

bool EstudioRitmosProcessor::carregarArquivo (const juce::File& f, juce::String& erro)
{
    if (! f.existsAsFile()) { erro = "Arquivo não encontrado."; return false; }
    if (f.hasFileExtension ("ritmo")) return carregarRitmoDeTexto (f.loadFileAsString(), erro);
    juce::MemoryBlock mb;
    f.loadFileAsData (mb);
    return carregarEstilo (mb, f.getFileNameWithoutExtension(), erro);
}

void EstudioRitmosProcessor::getStateInformation (juce::MemoryBlock& dest)
{
    juce::ValueTree raiz ("EstudioRitmos");
    {
        const juce::ScopedLock sl (lockRitmo);
        if (estiloDados.getSize() > 0)
        {
            raiz.setProperty ("estilo", estiloDados.toBase64Encoding(), nullptr);
            raiz.setProperty ("estiloNome", estiloNome, nullptr);
        }
        else
            raiz.setProperty ("ritmo", ritmoJson, nullptr);
    }
    raiz.appendChild (parametros.copyState(), nullptr);
    juce::MemoryOutputStream os (dest, false);
    raiz.writeToStream (os);
}

void EstudioRitmosProcessor::setStateInformation (const void* data, int size)
{
    auto raiz = juce::ValueTree::readFromData (data, (size_t) size);
    if (! raiz.isValid() || ! raiz.hasType ("EstudioRitmos")) return;
    juce::String erro;
    auto estilo = raiz.getProperty ("estilo").toString();
    auto json = raiz.getProperty ("ritmo").toString();
    if (estilo.isNotEmpty())
    {
        juce::MemoryBlock mb;
        if (mb.fromBase64Encoding (estilo)) carregarEstilo (mb, raiz.getProperty ("estiloNome").toString(), erro);
    }
    else if (json.isNotEmpty())
        carregarRitmoDeTexto (json, erro);
    auto p = raiz.getChildWithName (parametros.state.getType());
    if (p.isValid()) parametros.replaceState (p);
}

// ---------------------------------------------------------------- comandos da interface
void EstudioRitmosProcessor::enviarComando (Comando c)
{
    const juce::ScopedLock sl (lockComandos);
    comandos.push_back (std::move (c));
}

EstadoUI EstudioRitmosProcessor::estadoUI() const
{
    const juce::ScopedLock sl (lockEstado);
    return estado;
}

void EstudioRitmosProcessor::iniciarAlinhado (double ppq, double ppqCompasso)
{
    double dentro = juce::jmax (0.0, (ppq - ppqCompasso) * PPQ);
    if (dentro >= COMPASSO) dentro = std::fmod (dentro, (double) COMPASSO);
    if (motor.tocando || motor.armado) motor.parar();
    motor.iniciar ((long long) std::ceil (dentro));
    tickInicio = dentro;
}

void EstudioRitmosProcessor::aplicarComando (const Comando& c)
{
    const bool eraParado = ! motor.tocando;
    switch (c.tipo)
    {
        case Comando::Pedir: motor.pedir (c.v); break;
        case Comando::IniciarParar:
            if (motor.tocando || motor.armado) { motor.parar(); tocandoPeloHost = false; }
            else motor.iniciar();
            break;
        case Comando::Sync:
            if (! motor.tocando) motor.armarSync (! motor.armado);
            break;
        case Comando::Acorde:
            try { motor.definirAcorde (parseAcorde (c.v)); } catch (...) {}
            break;
        case Comando::Sequencia:
        {
            std::vector<Acorde> seq;
            try
            {
                for (auto& s : juce::StringArray::fromTokens (juce::String (c.v), " ", ""))
                    if (s.isNotEmpty()) seq.push_back (parseAcorde (s.toStdString()));
            }
            catch (...) { seq.clear(); }
            motor.definirSequencia (seq);
            break;
        }
        case Comando::PararTudo: motor.parar(); tocandoPeloHost = false; break;
    }
    if (eraParado && motor.tocando)                 // começou agora: o tick 0 cai nesta amostra
        tickInicio = (double) motor.pos - amostraAtual * tps;
}

// ---------------------------------------------------------------- MIDI de entrada
void EstudioRitmosProcessor::reconhecerMaoEsquerda()
{
    std::vector<int> notas;
    for (int n = 0; n < 128; ++n)
        if (presas[(size_t) n]) notas.push_back (n);
    int modo = ((juce::AudioParameterChoice*) parametros.getParameter ("modo"))->getIndex();
    if (auto ac = reconhecer (notas, modo == 1))
    {
        if (modo == 0) ac->baixo = -1;          // Fingered: inversão toca como posição fundamental
        const bool eraParado = ! motor.tocando;
        motor.definirAcorde (*ac);
        if (eraParado && motor.tocando)
            tickInicio = (double) motor.pos - amostraAtual * tps;
    }
}

void EstudioRitmosProcessor::tratarEntrada (const juce::MidiMessage& m, int amostra, int, juce::MidiBuffer& saida)
{
    int split = 36 + ((juce::AudioParameterChoice*) parametros.getParameter ("split"))->getIndex();

    if (m.getChannel() == 16 && m.isNoteOn())
    {
        auto it = teclasDeControle().find (m.getNoteNumber());
        if (it != teclasDeControle().end())
        {
            if (it->second == "INICIAR/PARAR") aplicarComando ({ Comando::IniciarParar, "" });
            else if (it->second == "SYNC") aplicarComando ({ Comando::Sync, "" });
            else aplicarComando ({ Comando::Pedir, it->second });
        }
        return;
    }
    if (m.getChannel() == 16 && m.isNoteOff()) return;

    if (m.isNoteOnOrOff() && m.getNoteNumber() < split)
    {
        // o reconhecimento é feito depois de todas as notas do mesmo instante (acorde inteiro de uma vez)
        if (m.isNoteOn()) { presas.set ((size_t) m.getNoteNumber()); acordePendente = true; }
        else presas.reset ((size_t) m.getNoteNumber());            // memória: o acorde continua
        return;
    }
    saida.addEvent (m, amostra);                                    // mão direita e controles passam direto
}

// ---------------------------------------------------------------- áudio
void EstudioRitmosProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer& midi)
{
    juce::ScopedNoDenormals nd;
    buffer.clear();
    const int n = buffer.getNumSamples();
    juce::MidiBuffer entrada;
    entrada.swapWith (midi);          // `midi` agora é a saída
    saidaAtual = &midi;
    nAmostras = n;
    amostraAtual = 0;


    // ritmo novo vindo da interface
    {
        const juce::ScopedTryLock tl (lockRitmo);
        if (tl.isLocked() && ritmoPendente)
        {
            motor.setRitmo (ritmoPendente);
            ritmoPendente.reset();
            tocandoPeloHost = false;
        }
    }
    if (motor.ritmo() == nullptr) { saidaAtual = nullptr; return; }

    // relógio do host
    double bpm = motor.ritmo()->bpm;
    bool hostTocando = false;
    double ppq = 0.0, ppqCompasso = 0.0;
    bool temPpq = false;
    if (auto* ph = getPlayHead())
        if (auto pos = ph->getPosition())
        {
            if (auto b = pos->getBpm()) bpm = *b;
            hostTocando = pos->getIsPlaying();
            if (auto q = pos->getPpqPosition()) { ppq = *q; temPpq = true; }
            if (auto qb = pos->getPpqPositionOfLastBarStart()) ppqCompasso = *qb;
            else if (temPpq) ppqCompasso = std::floor (ppq / 4.0) * 4.0;
        }
    tps = bpm / 60.0 * PPQ / sr;

    motor.autoFill = parametros.getRawParameterValue ("autoFill")->load() > 0.5f;
    const bool seguir = parametros.getRawParameterValue ("seguirHost")->load() > 0.5f;

    // sincronia com o play/stop do Cubase
    if (seguir && hostTocando && temPpq)
    {
        if (! hostTocandoAntes || (tocandoPeloHost && ppqEsperado >= 0 && std::abs (ppq - ppqEsperado) > 0.05))
        {
            iniciarAlinhado (ppq, ppqCompasso);
            tocandoPeloHost = true;
        }
    }
    else if (seguir && ! hostTocando && hostTocandoAntes && tocandoPeloHost)
    {
        motor.parar();
        tocandoPeloHost = false;
    }
    if (! motor.tocando) tickInicio = (double) motor.pos;

    // comandos da interface
    {
        std::vector<Comando> cmds;
        {
            const juce::ScopedTryLock tl (lockComandos);
            if (tl.isLocked()) cmds.swap (comandos);
        }
        for (auto& c : cmds)
        {
            if (c.tipo == Comando::IniciarParar && seguir && hostTocando && temPpq && ! motor.tocando)
            {
                iniciarAlinhado (ppq, ppqCompasso);       // com o Cubase tocando: entra alinhado ao compasso
                tocandoPeloHost = true;
                continue;
            }
            aplicarComando (c);
        }
    }

    // automação do parâmetro "Secao"
    {
        int idx = ((juce::AudioParameterChoice*) parametros.getParameter ("secao"))->getIndex();
        if (idx != ultimaSecaoParam)
        {
            ultimaSecaoParam = idx;
            if (idx > 0) motor.pedir (nomesSecaoParam()[idx].toStdString());
        }
    }

    // percorre o bloco, parando em cada MIDI de entrada (acorde na hora certa)
    auto avancarAte = [&] (int amostra) {
        if (motor.tocando)
            motor.avancar ((long long) std::ceil (tickInicio + amostra * tps));
    };
    int amostraDoGrupo = -1;
    for (const auto meta : entrada)
    {
        int s = juce::jlimit (0, juce::jmax (0, n - 1), meta.samplePosition);
        if (s != amostraDoGrupo)
        {
            if (acordePendente) { reconhecerMaoEsquerda(); acordePendente = false; }
            avancarAte (s);
            amostraAtual = amostraDoGrupo = s;
        }
        tratarEntrada (meta.getMessage(), s, n, midi);
    }
    if (acordePendente) { reconhecerMaoEsquerda(); acordePendente = false; }
    avancarAte (n);
    amostraAtual = 0;

    tickInicio += n * tps;
    if (! motor.tocando) tickInicio = (double) motor.pos;
    ppqEsperado = temPpq ? ppq + n * bpm / 60.0 / sr : -1.0;
    hostTocandoAntes = hostTocando;
    saidaAtual = nullptr;

    {
        const juce::ScopedTryLock tl (lockEstado);
        if (tl.isLocked())
        {
            estado.motor = motor.estado();
            estado.bpm = bpm;
            estado.hostTocando = hostTocando;
            estado.seguindoHost = tocandoPeloHost;
        }
    }
}

juce::AudioProcessorEditor* EstudioRitmosProcessor::createEditor() { return new EstudioRitmosEditor (*this); }

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter() { return new EstudioRitmosProcessor(); }
