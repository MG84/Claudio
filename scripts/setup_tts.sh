#!/bin/bash
# ═══════════════════════════════════════════════════════════
#  Setup Qwen3-TTS via MLX sul Mac (fuori Docker)
#  Esegui questo script una volta sola sul tuo Mac.
# ═══════════════════════════════════════════════════════════

set -e

TTS_DIR="$HOME/.claudio-tts"

echo "═══════════════════════════════════════════"
echo "  Qwen3-TTS Setup per Claudio"
echo "═══════════════════════════════════════════"

# Check macOS + Apple Silicon
if [[ "$(uname)" != "Darwin" ]]; then
    echo "ERROR: Questo script è solo per macOS"
    exit 1
fi

# Check ffmpeg
if ! command -v ffmpeg &>/dev/null; then
    echo "Installando ffmpeg..."
    brew install ffmpeg
fi

# Create TTS directory
mkdir -p "$TTS_DIR"
cd "$TTS_DIR"

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "Creando virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

# Install mlx-tts-api
if [ ! -d "mlx-tts-api" ]; then
    echo "Clonando mlx-tts-api..."
    git clone https://github.com/MeeTasu/mlx-tts-api.git
fi

cd mlx-tts-api

echo "Installando dipendenze..."
pip install -r requirements.txt

echo ""
echo "═══════════════════════════════════════════"
echo "  Setup completato!"
echo "═══════════════════════════════════════════"
echo ""
echo "  Per avviare il server TTS:"
echo "    cd $TTS_DIR/mlx-tts-api"
echo "    source ../.venv/bin/activate"
echo "    python server.py"
echo ""
echo "  Il server partirà su http://0.0.0.0:8080"
echo "  Il modello verrà scaricato al primo uso (~2GB)"
echo ""
echo "  Per registrare la tua voce (voice cloning):"
echo "    curl -X POST http://localhost:8080/v1/voices \\"
echo "      -F 'audio=@tuo_vocale.wav' \\"
echo "      -F 'name=marco' \\"
echo "      -F 'ref_text=Trascrizione del vocale' \\"
echo "      -F 'language=Italian'"
echo ""
echo "  Per autostart, esegui:"
echo "    bash $(dirname "$0")/install_tts_service.sh"
echo ""
