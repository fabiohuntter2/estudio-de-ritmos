# Estúdio de Ritmos

Criação de ritmos para teclado arranjador: transforma loops de bateria em MIDI, monta ritmos de
8 pistas com seções (Intro, Variações A–D, Viradas, Break, Final) e toca como um teclado —
a mão esquerda faz o acorde e o ritmo acompanha.

| Pasta | O que é |
|---|---|
| `programa/` | Programa (Python): importar loop → MIDI, programar seções, tocar, exportar MIDI/WAV, VST por pista. Veja `programa/LEIA-ME.txt`. |
| `plugin/` | Plugin **VST3** (C++/JUCE) para Cubase e outras DAWs: toca `.ritmo` e **estilos Yamaha `.sty`** sincronizado com o projeto e manda as 8 pistas em MIDI para o Kontakt. Veja `plugin/LEIA-ME-PLUGIN.txt`. |

**Formatos:** `.ritmo` (próprio) · Yamaha `.sty/.prs/.sst` (SFF1/SFF2, com CASM: camadas maior/menor,
acorde-fonte, High Key, limites, zonas SFF2) · estilos Korg em MIDI. Bancos binários Korg Pa (`.STY`)
e Pa5X (`.STG`) são identificados, mas ainda não abrem (formato fechado).

## Baixar o plugin pronto
Aba **Actions** → execução mais recente com ✅ → seção *Artifacts* →
`EstudioRitmos-VST3-Windows` (ou `-Mac`).

## Testes automáticos (rodam a cada envio)
1. Programa Python: 39 testes (acordes, detecção de bateria, tocador, exportação, som).
2. Motor C++ comparado ao Python, evento por evento (inclui estilo Yamaha real, valsa 3/4 com camadas e estilo Korg em MIDI).
3. O `.vst3` carregado num host que simula o Cubase (tempo, play/stop, acordes, salto de posição),
   em 4 tamanhos de buffer, conferido contra o motor Python (±1 amostra).
4. pluginval (validador de plugins), nível máximo.

Licenças: JUCE 8 (plano Starter gratuito até US$ 20 mil/ano de receita), VST3 SDK (MIT).
