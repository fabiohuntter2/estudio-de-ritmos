// Estilos Yamaha (.sty/.prs/.sst, SFF1 e SFF2) -> Ritmo. Porta fiel de nucleo/estilo_yamaha.py.
// Também aceita estilos em MIDI comum com marcadores Korg ("Variation 1", "Fill 2", "Ending 1"...).
#pragma once
#include "Ritmo.h"
#include <cstdint>
#include <optional>
#include <stdexcept>

namespace er
{
struct ErroEstilo : std::runtime_error { using std::runtime_error::runtime_error; };

std::optional<std::string> normalizarSecao (const std::string& marcador);

// Lança ErroEstilo com mensagem explicativa (inclusive para bancos Korg em formato fechado).
std::shared_ptr<Ritmo> lerSty (const std::vector<uint8_t>& dados, const std::string& nome);

bool pareceEstilo (const std::vector<uint8_t>& dados);    // começa com MThd
} // namespace er
