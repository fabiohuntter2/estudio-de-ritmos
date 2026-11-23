#pragma once
#include <juce_audio_processors/juce_audio_processors.h>
#include <bitset>
#include "nucleo/Motor.h"

struct Comando
{
    enum Tipo { Pedir, IniciarParar, Sync, Acorde, Sequencia, PararTudo } tipo;
    std::string v;
};

struct EstadoUI
{
    er::EstadoMotor motor;
    double bpm = 120.0;
    bool hostTocando = false, seguindoHost = false;
    std::string nomeRitmo, erro, compasso = "4/4", origem = "ritmo";
    std::vector<std::string> secoesComNotas;
};

class EstudioRitmosProcessor : public juce::AudioProcessor
{
public:
    EstudioRitmosProcessor();
    ~EstudioRitmosProcessor() override = default;

    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    void releaseResources() override {}
    bool isBusesLayoutSupported (const BusesLayout& layouts) const override;
    void processBlock (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;
    using AudioProcessor::processBlock;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }

    const juce::String getName() const override { return "Estudio de Ritmos"; }
    bool acceptsMidi() const override { return true; }
    bool producesMidi() const override { return true; }
    bool isMidiEffect() const override { return false; }
    double getTailLengthSeconds() const override { return 0.0; }

    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram (int) override {}
    const juce::String getProgramName (int) override { return "Padrão"; }
    void changeProgramName (int, const juce::String&) override {}

    void getStateInformation (juce::MemoryBlock& destData) override;
    void setStateInformation (const void* data, int sizeInBytes) override;

    // ---- chamadas da interface (thread da mensagem)
    void enviarComando (Comando c);
    bool carregarRitmoDeTexto (const juce::String& json, juce::String& erro);
    bool carregarEstilo (const juce::MemoryBlock& dados, const juce::String& nome, juce::String& erro);   // .sty
    bool carregarArquivo (const juce::File& f, juce::String& erro);                                     // .ritmo ou .sty
    EstadoUI estadoUI() const;

    juce::AudioProcessorValueTreeState parametros;
    static const juce::StringArray& nomesSecaoParam();
    static const std::map<int, std::string>& teclasDeControle();   // canal 16

private:
    static juce::AudioProcessorValueTreeState::ParameterLayout criarParametros();
    void tratarEntrada (const juce::MidiMessage& m, int amostra, int n, juce::MidiBuffer& saida);
    void aplicarComando (const Comando& c);
    void iniciarAlinhado (double ppq, double ppqCompasso);
    void reconhecerMaoEsquerda();

    er::Motor motor;
    juce::String ritmoJson;                                   // guardado no projeto do Cubase
    juce::MemoryBlock estiloDados;                            // ou o .sty original (guardado em base64)
    juce::String estiloNome;
    void publicarRitmo (std::shared_ptr<er::Ritmo> r, const char* origem);

    juce::CriticalSection lockComandos, lockEstado, lockRitmo;
    std::vector<Comando> comandos;
    std::shared_ptr<const er::Ritmo> ritmoPendente;
    EstadoUI estado;

    double sr = 44100.0;
    double tickInicio = 0.0;           // posição (em ticks, fracionária) da amostra 0 do bloco
    double tps = 0.0;                  // ticks por amostra
    int amostraAtual = 0, nAmostras = 0;
    juce::MidiBuffer* saidaAtual = nullptr;
    bool hostTocandoAntes = false, tocandoPeloHost = false;
    double ppqEsperado = -1.0;
    int ultimaSecaoParam = 0;
    std::bitset<128> presas;
    bool acordePendente = false;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (EstudioRitmosProcessor)
};
