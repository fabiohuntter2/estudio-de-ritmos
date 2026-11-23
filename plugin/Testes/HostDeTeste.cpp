// Host de teste: carrega o .vst3 compilado, simula o Cubase (tempo, play/stop, acordes) e grava o MIDI de saída.
//   HostDeTeste <plugin.vst3> <cenario> <tamanho_do_bloco> <saida.jsonl>
// Cenários: cubase | interno | relocar | estado | semplayhead
#include <juce_audio_processors/juce_audio_processors.h>
#include <iostream>
#include <fstream>

struct PlayHeadSimulado : juce::AudioPlayHead
{
    double bpm = 136.0, sr = 48000.0;
    bool tocando = false;
    juce::int64 amostra = 0;     // posição do host
    bool comPpq = true;

    juce::Optional<PositionInfo> getPosition() const override
    {
        PositionInfo p;
        p.setBpm (bpm);
        p.setIsPlaying (tocando);
        p.setTimeInSamples (amostra);
        p.setTimeSignature (TimeSignature { 4, 4 });
        if (comPpq)
        {
            double ppq = (double) amostra / sr * bpm / 60.0;
            p.setPpqPosition (ppq);
            p.setPpqPositionOfLastBarStart (std::floor (ppq / 4.0) * 4.0);
        }
        return p;
    }
};

struct Entrada { juce::int64 amostra; juce::MidiMessage m; };

static void escrever (std::ostream& os, juce::int64 s, const juce::MidiMessage& m)
{
    const char* t = m.isNoteOn() ? "on" : m.isNoteOff() ? "off" : m.isController() ? "cc" : m.isProgramChange() ? "pc" : "outro";
    int d1 = m.isNoteOnOrOff() ? m.getNoteNumber() : m.isController() ? m.getControllerNumber() : m.isProgramChange() ? m.getProgramChangeNumber() : 0;
    int d2 = m.isNoteOn() ? m.getVelocity() : m.isController() ? m.getControllerValue() : 0;
    os << "[" << s << ",\"" << t << "\"," << (m.getChannel() - 1) << "," << d1 << "," << d2 << "]\n";
}

int main (int argc, char** argv)
{
    juce::ScopedJuceInitialiser_GUI juceInit;
    if (argc < 5) { std::cerr << "uso: HostDeTeste <plugin> <cenario> <bloco> <saida>\n"; return 1; }
    juce::String caminho (argv[1]), cenario (argv[2]);
    int bloco = juce::String (argv[3]).getIntValue();
    std::ofstream saida (argv[4]);

    juce::AudioPluginFormatManager fm;
    fm.addFormat (std::make_unique<juce::VST3PluginFormat>());
    juce::OwnedArray<juce::PluginDescription> tipos;
    for (auto* f : fm.getFormats()) f->findAllTypesForFile (tipos, caminho);
    if (tipos.isEmpty()) { std::cerr << "plugin não encontrado\n"; return 2; }
    std::cerr << "Plugin: " << tipos[0]->name << " | instrumento=" << tipos[0]->isInstrument
              << " | categoria=" << tipos[0]->category << "\n";

    const double sr = 48000.0;
    juce::String erro;
    auto plugin = fm.createPluginInstance (*tipos[0], sr, bloco, erro);
    if (! plugin) { std::cerr << "erro ao criar: " << erro << "\n"; return 3; }
    std::cerr << "acceptsMidi=" << plugin->acceptsMidi() << " producesMidi=" << plugin->producesMidi()
              << " parametros=" << plugin->getParameters().size() << " saidas=" << plugin->getTotalNumOutputChannels() << "\n";
    for (auto* p : plugin->getParameters()) std::cerr << "  param: " << p->getName (64) << " = " << p->getCurrentValueAsText() << "\n";

    PlayHeadSimulado ph;
    ph.sr = sr;
    plugin->setPlayHead (&ph);
    plugin->setPlayConfigDetails (0, 2, sr, bloco);
    plugin->prepareToPlay (sr, bloco);

    const double tps = 136.0 / 60.0 * 480.0 / sr;
    auto amostraDoTick = [&] (double tick) { return (juce::int64) std::floor (tick / tps); };
    std::vector<Entrada> entradas;
    auto acorde = [&] (double tick, std::initializer_list<int> notas, double fimTick) {
        for (int n : notas)
        {
            entradas.push_back ({ amostraDoTick (tick), juce::MidiMessage::noteOn (1, n, (juce::uint8) 90) });
            entradas.push_back ({ amostraDoTick (fimTick) - 10, juce::MidiMessage::noteOff (1, n) });
        }
    };
    auto tecla = [&] (double tick, int nota) {
        entradas.push_back ({ amostraDoTick (tick), juce::MidiMessage::noteOn (16, nota, (juce::uint8) 100) });
        entradas.push_back ({ amostraDoTick (tick) + 100, juce::MidiMessage::noteOff (16, nota) });
    };

    const double C = 1920;
    juce::int64 total = amostraDoTick (12 * C);
    juce::int64 pararHost = amostraDoTick (10 * C) + 77;
    juce::int64 relocarEm = -1, relocarPara = 0;

    if (cenario == "cubase" || cenario == "relocar" || cenario == "semplayhead")
    {
        ph.tocando = true;
        acorde (0, { 43, 48, 52 }, C);                // C (G2 C3 E3, abaixo do split)
        acorde (C, { 45, 48, 52 }, 3 * C);            // Am
        tecla (4000, 41);                             // Var B (com virada)
        acorde (3 * C, { 43, 47, 50, 53 }, 6 * C);    // G7
        acorde (6 * C, { 40, 43, 48 }, 12 * C);       // C/E
        entradas.push_back ({ amostraDoTick (5 * C), juce::MidiMessage::noteOn (1, 72, (juce::uint8) 80) });  // mão direita
        entradas.push_back ({ amostraDoTick (5 * C) + 500, juce::MidiMessage::noteOff (1, 72) });
        if (cenario == "relocar") { relocarEm = amostraDoTick (4 * C) + 1000; relocarPara = amostraDoTick (8 * C); }
        if (cenario == "semplayhead") { ph.comPpq = false; plugin->setPlayHead (nullptr); }
    }
    else if (cenario == "interno")
    {
        ph.tocando = false;                           // Cubase parado: o plugin toca sozinho
        tecla (100, 53);                              // Sync Start
        acorde (C / 2, { 50, 53, 57 }, 4 * C);        // Dm -> começa aqui
        tecla (3 * C, 48);                            // Final A
        pararHost = -1;
    }
    else if (cenario == "estado")
    {
        juce::MemoryBlock mb;
        auto achar = [] (juce::AudioPluginInstance& pl, const juce::String& nome) -> juce::AudioProcessorParameter* {
            for (auto* p : pl.getParameters()) if (p->getName (64) == nome) return p;
            return nullptr;
        };
        achar (*plugin, "Auto Fill")->setValueNotifyingHost (0.0f);
        achar (*plugin, "Split")->setValueNotifyingHost (0.6f);
        achar (*plugin, "Modo de acorde")->setValueNotifyingHost (1.0f);
        plugin->getStateInformation (mb);
        auto outro = fm.createPluginInstance (*tipos[0], sr, bloco, erro);
        outro->setStateInformation (mb.getData(), (int) mb.getSize());
        bool ok = true;
        for (auto nome : { "Secao", "Auto Fill", "Seguir play do host", "Split", "Modo de acorde" })
        {
            auto a = achar (*plugin, nome)->getCurrentValueAsText(), b = achar (*outro, nome)->getCurrentValueAsText();
            std::cerr << "  estado " << nome << ": " << a << " -> " << b << "\n";
            ok &= a == b;
        }
        std::cerr << "estado: " << mb.getSize() << " bytes, " << (ok ? "OK" : "FALHA") << "\n";
        return ok ? 0 : 4;
    }
    std::sort (entradas.begin(), entradas.end(), [] (auto& a, auto& b) { return a.amostra < b.amostra; });

    juce::AudioBuffer<float> audio (2, bloco);
    juce::int64 pos = 0;
    size_t ie = 0;
    int maxAudio = 0;
    while (pos < total)
    {
        int n = (int) juce::jmin<juce::int64> (bloco, total - pos);
        if (pararHost >= 0 && pos >= pararHost) ph.tocando = false;
        if (relocarEm >= 0 && pos >= relocarEm) { ph.amostra = relocarPara; relocarEm = -1; }
        juce::MidiBuffer midi;
        while (ie < entradas.size() && entradas[ie].amostra < pos + n)
        {
            midi.addEvent (entradas[ie].m, (int) juce::jmax<juce::int64> (0, entradas[ie].amostra - pos));
            ++ie;
        }
        audio.setSize (2, n, false, false, true);
        audio.clear();
        plugin->processBlock (audio, midi);
        for (int c = 0; c < 2; ++c) maxAudio = juce::jmax (maxAudio, (int) (audio.getMagnitude (c, 0, n) * 1000));
        for (const auto meta : midi)
            escrever (saida, pos + meta.samplePosition, meta.getMessage());
        pos += n;
        ph.amostra += n;
    }
    std::cerr << "fim: " << pos << " amostras, audio max=" << maxAudio << "\n";
    plugin->releaseResources();
    return 0;
}
