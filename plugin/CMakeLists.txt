cmake_minimum_required(VERSION 3.22)
project(EstudioRitmos VERSION 0.1.0)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(APPLE)
    set(CMAKE_OSX_ARCHITECTURES "arm64;x86_64" CACHE STRING "" FORCE)
    set(CMAKE_OSX_DEPLOYMENT_TARGET "10.13" CACHE STRING "" FORCE)
endif()
if(MSVC)
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
endif()

# JUCE: usa uma cópia local (JUCE_PATH) ou baixa a versão 8.0.12
set(JUCE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/../../JUCE" CACHE PATH "Pasta do JUCE (opcional; sem ela o CMake baixa o JUCE 8.0.12)")
if(EXISTS "${JUCE_PATH}/CMakeLists.txt")
    add_subdirectory("${JUCE_PATH}" JUCE)
else()
    include(FetchContent)
    FetchContent_Declare(JUCE GIT_REPOSITORY https://github.com/juce-framework/JUCE.git GIT_TAG 8.0.12 GIT_SHALLOW ON)
    FetchContent_MakeAvailable(JUCE)
endif()

# ------------------------------------------------------------------ plugin
juce_add_plugin(EstudioRitmos
    COMPANY_NAME "Estudio de Ritmos"
    PRODUCT_NAME "Estudio de Ritmos"
    BUNDLE_ID "com.estudioderitmos.plugin"
    PLUGIN_MANUFACTURER_CODE Estr
    PLUGIN_CODE ErRt
    FORMATS VST3 Standalone
    IS_SYNTH TRUE
    NEEDS_MIDI_INPUT TRUE
    NEEDS_MIDI_OUTPUT TRUE
    IS_MIDI_EFFECT FALSE
    EDITOR_WANTS_KEYBOARD_FOCUS FALSE
    VST3_CATEGORIES Instrument Generator
    COPY_PLUGIN_AFTER_BUILD FALSE)

juce_add_binary_data(EstudioRitmosDados SOURCES "Recursos/Arrocha Demo.ritmo")

set(NUCLEO Source/nucleo/Acordes.cpp Source/nucleo/Ritmo.cpp Source/nucleo/Motor.cpp Source/nucleo/EstiloYamaha.cpp)

target_sources(EstudioRitmos PRIVATE
    Source/PluginProcessor.cpp
    Source/PluginEditor.cpp
    ${NUCLEO})

target_compile_definitions(EstudioRitmos PUBLIC
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
    JUCE_VST3_CAN_REPLACE_VST2=0
    JUCE_DISPLAY_SPLASH_SCREEN=0)

target_link_libraries(EstudioRitmos
    PRIVATE EstudioRitmosDados juce::juce_audio_utils juce::juce_audio_processors
    PUBLIC juce::juce_recommended_config_flags juce::juce_recommended_lto_flags juce::juce_recommended_warning_flags)

# ------------------------------------------------------------------ testes do núcleo (linha de comando)
juce_add_console_app(TestesNucleo PRODUCT_NAME "TestesNucleo")
target_sources(TestesNucleo PRIVATE Testes/TestesNucleo.cpp ${NUCLEO})
target_compile_definitions(TestesNucleo PRIVATE JUCE_WEB_BROWSER=0 JUCE_USE_CURL=0)
target_link_libraries(TestesNucleo PRIVATE juce::juce_core PUBLIC juce::juce_recommended_config_flags)

# ------------------------------------------------------------------ host de teste (carrega o .vst3)
juce_add_console_app(HostDeTeste PRODUCT_NAME "HostDeTeste")
target_sources(HostDeTeste PRIVATE Testes/HostDeTeste.cpp)
target_compile_definitions(HostDeTeste PRIVATE JUCE_PLUGINHOST_VST3=1 JUCE_WEB_BROWSER=0 JUCE_USE_CURL=0)
target_link_libraries(HostDeTeste PRIVATE juce::juce_audio_processors juce::juce_audio_utils PUBLIC juce::juce_recommended_config_flags)
