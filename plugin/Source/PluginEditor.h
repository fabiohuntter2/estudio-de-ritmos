#pragma once
#include <juce_audio_processors/juce_audio_processors.h>
#include "PluginProcessor.h"

class EstudioRitmosEditor : public juce::AudioProcessorEditor, private juce::Timer
{
public:
    explicit EstudioRitmosEditor (EstudioRitmosProcessor&);
    ~EstudioRitmosEditor() override;
    void paint (juce::Graphics&) override;
    void resized() override;

private:
    void timerCallback() override;
    void abrirRitmo();
    void mostrarAjuda();

    EstudioRitmosProcessor& proc;
    juce::LookAndFeel_V4 visual;

    juce::Label titulo, nomeRitmo, lblAcorde, lblSecao, lblProxima, lblBpm, lblInfo, lblSplit, lblModo, lblSeq, lblAcordeTxt;
    juce::TextButton btAbrir { "Abrir ritmo..." }, btExemplo { "Exemplo" }, btAjuda { "Ajuda" };
    juce::TextButton btPlay { "INICIAR" }, btSync { "Sync Start" };
    juce::ToggleButton tgSeguir { "Seguir play do Cubase" }, tgAutoFill { "Auto Fill" }, tgSeq { "Sequencia automatica" };
    juce::ComboBox cbSplit, cbModo;
    juce::TextEditor txtSeq, txtAcorde;
    std::vector<std::unique_ptr<juce::TextButton>> botoesSecao;
    std::vector<juce::String> nomesBotoes;

    using BA = juce::AudioProcessorValueTreeState::ButtonAttachment;
    using CA = juce::AudioProcessorValueTreeState::ComboBoxAttachment;
    std::unique_ptr<BA> atSeguir, atAutoFill;
    std::unique_ptr<CA> atSplit, atModo;
    std::unique_ptr<juce::FileChooser> seletor;

    EstadoUI ultimo;
    juce::Rectangle<int> areaTempos;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (EstudioRitmosEditor)
};
