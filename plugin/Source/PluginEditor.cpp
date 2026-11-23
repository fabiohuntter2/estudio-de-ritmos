#include "PluginEditor.h"
#include "BinaryData.h"

namespace
{
const juce::Colour FUNDO (0xff1e1f24), PAINEL (0xff2a2c33), GRADE (0xff3a3d46), TEXTO (0xffe8e8ea),
                   TEXTO2 (0xffa0a3ad), ACENTO (0xfff0a830), PROX (0xff6b5320), VERDE (0xff4cc38a), VERMELHO (0xffe5534b);

juce::String u (const char* s) { return juce::String::fromUTF8 (s); }
}

EstudioRitmosEditor::EstudioRitmosEditor (EstudioRitmosProcessor& p) : AudioProcessorEditor (&p), proc (p)
{
    visual.setColourScheme ({ PAINEL, FUNDO, GRADE, GRADE, TEXTO, ACENTO, juce::Colours::black, GRADE, TEXTO });
    setLookAndFeel (&visual);

    auto rotulo = [this] (juce::Label& l, const juce::String& t, float tam, juce::Colour c, bool negrito = false) {
        l.setText (t, juce::dontSendNotification);
        l.setFont (juce::FontOptions (tam, negrito ? juce::Font::bold : juce::Font::plain));
        l.setColour (juce::Label::textColourId, c);
        addAndMakeVisible (l);
    };
    rotulo (titulo, u ("Estúdio de Ritmos"), 20.f, ACENTO, true);
    rotulo (nomeRitmo, "", 15.f, TEXTO);
    rotulo (lblAcorde, u ("—"), 64.f, ACENTO, true);
    rotulo (lblSecao, "Parado", 18.f, TEXTO, true);
    rotulo (lblProxima, "", 13.f, TEXTO2);
    rotulo (lblBpm, "", 15.f, TEXTO);
    rotulo (lblInfo, u ("Saída MIDI: pistas nos canais 9 a 16 → Kontakt. Mão esquerda abaixo do split faz o acorde. "
                        "Canal 16 = teclas de controle (Ajuda)."), 12.f, TEXTO2);
    rotulo (lblSplit, "Split:", 13.f, TEXTO);
    rotulo (lblModo, "Modo:", 13.f, TEXTO);
    rotulo (lblSeq, "", 13.f, TEXTO);
    rotulo (lblAcordeTxt, "Acorde:", 13.f, TEXTO);
    lblInfo.setJustificationType (juce::Justification::topLeft);

    for (auto* b : { &btAbrir, &btExemplo, &btAjuda, &btPlay, &btSync })
        addAndMakeVisible (*b);
    btPlay.setColour (juce::TextButton::buttonColourId, VERDE);
    btPlay.setColour (juce::TextButton::textColourOffId, juce::Colours::black);

    btAbrir.onClick = [this] { abrirRitmo(); };
    btExemplo.onClick = [this] {
        juce::String erro;
        proc.carregarRitmoDeTexto (juce::String::fromUTF8 (BinaryData::Arrocha_Demo_ritmo, BinaryData::Arrocha_Demo_ritmoSize), erro);
    };
    btAjuda.onClick = [this] { mostrarAjuda(); };
    btPlay.onClick = [this] { proc.enviarComando ({ Comando::IniciarParar, "" }); };
    btSync.onClick = [this] { proc.enviarComando ({ Comando::Sync, "" }); };

    for (auto* t : { &tgSeguir, &tgAutoFill, &tgSeq })
    {
        t->setColour (juce::ToggleButton::textColourId, TEXTO);
        t->setColour (juce::ToggleButton::tickColourId, ACENTO);
        addAndMakeVisible (*t);
    }
    tgSeq.setButtonText (u ("Sequência automática (1 acorde por compasso)"));
    atSeguir = std::make_unique<BA> (proc.parametros, "seguirHost", tgSeguir);
    atAutoFill = std::make_unique<BA> (proc.parametros, "autoFill", tgAutoFill);

    auto* split = (juce::AudioParameterChoice*) proc.parametros.getParameter ("split");
    cbSplit.addItemList (split->choices, 1);
    cbModo.addItemList ({ "Fingered", "Single Finger", "Fingered On Bass" }, 1);
    addAndMakeVisible (cbSplit);
    addAndMakeVisible (cbModo);
    atSplit = std::make_unique<CA> (proc.parametros, "split", cbSplit);
    atModo = std::make_unique<CA> (proc.parametros, "modo", cbModo);

    for (auto* t : { &txtSeq, &txtAcorde })
    {
        t->setColour (juce::TextEditor::backgroundColourId, GRADE);
        t->setColour (juce::TextEditor::textColourId, TEXTO);
        t->setFont (juce::FontOptions (15.f));
        addAndMakeVisible (*t);
    }
    txtSeq.setText ("C Am F G7");
    txtSeq.onReturnKey = [this] { if (tgSeq.getToggleState()) proc.enviarComando ({ Comando::Sequencia, txtSeq.getText().toStdString() }); };
    tgSeq.onClick = [this] {
        proc.enviarComando ({ Comando::Sequencia, tgSeq.getToggleState() ? txtSeq.getText().toStdString() : std::string() });
    };
    txtAcorde.setTextToShowWhenEmpty ("ex.: Am7 + Enter", TEXTO2);
    txtAcorde.onReturnKey = [this] {
        try
        {
            er::parseAcorde (txtAcorde.getText().toStdString());
            proc.enviarComando ({ Comando::Acorde, txtAcorde.getText().toStdString() });
            txtAcorde.clear();
        }
        catch (const std::exception& e) { lblInfo.setText (u (e.what()), juce::dontSendNotification); }
    };

    nomesBotoes = { "Intro A", "Intro B", "Intro C", "Var A", "Var B", "Var C", "Var D", "Fill", "Break",
                    "Final A", "Final B", "Final C" };
    for (auto& nome : nomesBotoes)
    {
        auto b = std::make_unique<juce::TextButton> (nome);
        b->onClick = [this, nome] { proc.enviarComando ({ Comando::Pedir, nome.toStdString() }); };
        addAndMakeVisible (*b);
        botoesSecao.push_back (std::move (b));
    }

    setResizable (true, true);
    setResizeLimits (760, 500, 1400, 900);
    setSize (860, 540);
    startTimerHz (30);
}

EstudioRitmosEditor::~EstudioRitmosEditor()
{
    stopTimer();
    setLookAndFeel (nullptr);
}

void EstudioRitmosEditor::abrirRitmo()
{
    seletor = std::make_unique<juce::FileChooser> (u ("Abrir ritmo ou estilo (Estúdio de Ritmos .ritmo, Yamaha .sty/.prs/.sst, Korg em MIDI)"),
                                                   juce::File(), "*.ritmo;*.sty;*.STY;*.prs;*.sst;*.mid");
    seletor->launchAsync (juce::FileBrowserComponent::openMode | juce::FileBrowserComponent::canSelectFiles,
                          [this] (const juce::FileChooser& fc) {
                              auto f = fc.getResult();
                              if (! f.existsAsFile()) return;
                              juce::String erro;
                              if (! proc.carregarArquivo (f, erro))
                                  juce::AlertWindow::showMessageBoxAsync (juce::MessageBoxIconType::WarningIcon,
                                                                          "Abrir ritmo", erro);
                          });
}

void EstudioRitmosEditor::mostrarAjuda()
{
    juce::String t = u ("COMO LIGAR NO CUBASE\n"
                        "1. Coloque o Estúdio de Ritmos numa faixa de instrumento e grave/toque os acordes nela.\n"
                        "2. Crie uma faixa de instrumento com o Kontakt (multi com canais 9 a 16 ou uma faixa por pista).\n"
                        "3. Na faixa do Kontakt, Entrada MIDI = 'Estudio de Ritmos - MIDI Out', monitor ligado.\n\n"
                        "TECLAS DE CONTROLE (canal MIDI 16; no Cubase C1 = 36)\n");
    for (auto& [nota, acao] : EstudioRitmosProcessor::teclasDeControle())
        t << "  " << nota << " (" << juce::String (er::nomeNota (nota - 12)) << " no Cubase) = " << juce::String (acao) << "\n";
    t << u ("\nA troca de seção também pode ser automatizada pelo parâmetro 'Secao'.\n"
            "Abre ritmos .ritmo (programa Estúdio de Ritmos), estilos Yamaha .sty/.prs/.sst (SFF1 e SFF2)\n"
            "e estilos Korg em MIDI. O ritmo/estilo fica salvo dentro do projeto.");
    juce::AlertWindow::showMessageBoxAsync (juce::MessageBoxIconType::InfoIcon, "Ajuda", t);
}

void EstudioRitmosEditor::timerCallback()
{
    auto e = proc.estadoUI();
    const auto& m = e.motor;
    lblAcorde.setText (juce::String::fromUTF8 (m.acorde.c_str()), juce::dontSendNotification);
    nomeRitmo.setText ((e.origem == "sty" ? u ("Estilo: ") : u ("Ritmo: ")) + juce::String::fromUTF8 (e.nomeRitmo.c_str())
                           + "   (" + juce::String (e.compasso) + ")", juce::dontSendNotification);
    if (m.tocando)
    {
        lblSecao.setText (juce::String (m.secao) + "   compasso " + juce::String (m.compasso), juce::dontSendNotification);
        lblProxima.setText (m.proxima.empty() ? "" : u ("próxima: ") + juce::String (m.proxima), juce::dontSendNotification);
        btPlay.setButtonText ("PARAR");
        btPlay.setColour (juce::TextButton::buttonColourId, VERMELHO);
    }
    else
    {
        lblSecao.setText (m.armado ? u ("Aguardando acorde…") : u ("Parado — ") + juce::String (m.var)
                              + (m.intro.empty() ? "" : u ("  (com ") + juce::String (m.intro) + ")"),
                          juce::dontSendNotification);
        lblProxima.setText ("", juce::dontSendNotification);
        btPlay.setButtonText (m.armado ? "DESARMAR" : "INICIAR");
        btPlay.setColour (juce::TextButton::buttonColourId, m.armado ? VERMELHO : VERDE);
    }
    lblBpm.setText (juce::String (e.bpm, 1) + " BPM" + (e.seguindoHost ? u ("  ·  seguindo o Cubase") : juce::String()),
                    juce::dontSendNotification);
    btSync.setColour (juce::TextButton::buttonColourId, m.armado ? ACENTO : GRADE);

    for (size_t i = 0; i < botoesSecao.size(); ++i)
    {
        auto& nome = nomesBotoes[i];
        bool ativo = m.tocando && (m.secao == nome.toStdString() || (nome == "Fill" && m.secao.rfind ("Fill", 0) == 0));
        bool prox = (m.tocando && m.proxima == nome.toStdString()) || (! m.tocando && (m.var == nome.toStdString() || m.intro == nome.toStdString()));
        bool existe = nome == "Fill" || std::find (e.secoesComNotas.begin(), e.secoesComNotas.end(), nome.toStdString()) != e.secoesComNotas.end();
        auto& b = *botoesSecao[i];
        b.setColour (juce::TextButton::buttonColourId, ativo ? ACENTO : (prox ? PROX : GRADE));
        b.setColour (juce::TextButton::textColourOffId, ativo ? juce::Colours::black : (existe ? TEXTO : TEXTO2.withAlpha (0.5f)));
    }
    ultimo = e;
    repaint (areaTempos);
}

void EstudioRitmosEditor::paint (juce::Graphics& g)
{
    g.fillAll (FUNDO);
    g.setColour (PAINEL);
    g.fillRoundedRectangle (getLocalBounds().reduced (8).withTrimmedTop (48).toFloat(), 8.f);
    for (int k = 0; k < 4; ++k)
    {
        bool on = ultimo.motor.tocando && ultimo.motor.tempo == k + 1;
        g.setColour (on ? ACENTO : GRADE);
        g.fillEllipse ((float) areaTempos.getX() + k * 40.f, (float) areaTempos.getY(), 28.f, 28.f);
    }
    g.setColour (TEXTO2);
    g.setFont (juce::FontOptions (12.f));
    auto r = botoesSecao.empty() ? juce::Rectangle<int>() : botoesSecao[0]->getBounds();
    g.drawText ("INTRO", r.getX(), r.getY() - 18, 80, 16, juce::Justification::left);
    g.drawText (u ("VARIAÇÃO"), botoesSecao[3]->getX(), r.getY() - 18, 100, 16, juce::Justification::left);
    g.drawText ("VIRADA", botoesSecao[7]->getX(), botoesSecao[7]->getY() - 18, 80, 16, juce::Justification::left);
    g.drawText ("FINAL", botoesSecao[9]->getX(), botoesSecao[9]->getY() - 18, 80, 16, juce::Justification::left);
}

void EstudioRitmosEditor::resized()
{
    auto a = getLocalBounds().reduced (12);
    auto topo = a.removeFromTop (36);
    titulo.setBounds (topo.removeFromLeft (200));
    btAjuda.setBounds (topo.removeFromRight (70).reduced (2));
    btExemplo.setBounds (topo.removeFromRight (90).reduced (2));
    btAbrir.setBounds (topo.removeFromRight (160).reduced (2));
    nomeRitmo.setBounds (topo);
    a.removeFromTop (12);
    a.reduce (10, 6);

    auto esq = a.removeFromLeft (250);
    lblAcorde.setBounds (esq.removeFromTop (80));
    lblSecao.setBounds (esq.removeFromTop (26));
    lblProxima.setBounds (esq.removeFromTop (20));
    esq.removeFromTop (8);
    areaTempos = esq.removeFromTop (30).withWidth (160);
    lblBpm.setBounds (esq.removeFromTop (26));
    esq.removeFromTop (8);
    auto la = esq.removeFromTop (28);
    lblAcordeTxt.setBounds (la.removeFromLeft (60));
    txtAcorde.setBounds (la.withWidth (150));
    esq.removeFromTop (10);
    tgSeguir.setBounds (esq.removeFromTop (24));
    tgAutoFill.setBounds (esq.removeFromTop (24));

    a.removeFromLeft (16);
    auto linha1 = a.removeFromTop (54);
    btPlay.setBounds (linha1.removeFromLeft (linha1.getWidth() - 140).reduced (2));
    btSync.setBounds (linha1.reduced (4, 2));
    a.removeFromTop (28);
    const int w = 62, h = 54, gap = 6;
    auto grupo = [&] (int ini, int qtd, int x, int y) {
        for (int k = 0; k < qtd; ++k)
            botoesSecao[(size_t) (ini + k)]->setBounds (x + k * (w + gap), y, w, h);
    };
    int x0 = a.getX(), y0 = a.getY();
    grupo (0, 3, x0, y0);                     // Intro
    grupo (3, 4, x0 + 3 * (w + gap) + 20, y0); // Var
    int y1 = y0 + h + 30;
    grupo (7, 2, x0, y1);                     // Fill, Break
    grupo (9, 3, x0 + 3 * (w + gap) + 20, y1); // Final
    a.removeFromTop (2 * h + 44);

    auto ls = a.removeFromTop (28);
    lblSplit.setBounds (ls.removeFromLeft (44));
    cbSplit.setBounds (ls.removeFromLeft (110));
    ls.removeFromLeft (16);
    lblModo.setBounds (ls.removeFromLeft (46));
    cbModo.setBounds (ls.removeFromLeft (130));
    a.removeFromTop (8);
    tgSeq.setBounds (a.removeFromTop (24));
    txtSeq.setBounds (a.removeFromTop (28).withWidth (320));
    a.removeFromTop (8);
    lblInfo.setBounds (a.removeFromTop (48));
}
