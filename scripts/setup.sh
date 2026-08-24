#!/bin/bash

# ==============================================================
#  AI Agent - Telegram Bot Setup Script
#  Supports: macOS & Linux (Ubuntu/Debian)
# ==============================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

print_banner() {
    echo -e "${CYAN}"
    echo "  ╔══════════════════════════════════════════╗"
    echo "  ║        AI Agent - Telegram Bot           ║"
    echo "  ║          Installer & Setup               ║"
    echo "  ╚══════════════════════════════════════════╝"
    echo -e "${NC}"
}

info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC}   $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
step()    { echo -e "\n${BOLD}${CYAN}>>> $1${NC}"; }

# -------------------------------------------------------
# 1. Detect OS
# -------------------------------------------------------
detect_os() {
    step "Mendeteksi sistem operasi..."
    OS=""
    if [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
        success "macOS terdeteksi"
    elif [[ -f /etc/debian_version ]]; then
        OS="debian"
        success "Debian/Ubuntu terdeteksi"
    elif [[ -f /etc/redhat-release ]]; then
        OS="redhat"
        success "RedHat/CentOS terdeteksi"
    else
        error "Sistem operasi tidak didukung. Gunakan macOS atau Linux (Debian/Ubuntu)."
    fi
}

# -------------------------------------------------------
# 2. Check Python 3.10+
# -------------------------------------------------------
check_python() {
    step "Memeriksa Python..."
    if ! command -v python3 &>/dev/null; then
        error "Python3 tidak ditemukan. Install Python 3.10+ terlebih dahulu.\n  macOS : brew install python3\n  Ubuntu: sudo apt install python3"
    fi

    PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PYTHON_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
    PYTHON_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")

    if [[ "$PYTHON_MAJOR" -lt 3 ]] || { [[ "$PYTHON_MAJOR" -eq 3 ]] && [[ "$PYTHON_MINOR" -lt 10 ]]; }; then
        error "Butuh Python 3.10+, ditemukan Python $PYTHON_VERSION"
    fi

    success "Python $PYTHON_VERSION ditemukan"
}

# -------------------------------------------------------
# 3. Setup Virtual Environment
# -------------------------------------------------------
setup_venv() {
    step "Menyiapkan Virtual Environment..."
    if [[ -d "env" ]]; then
        warn "Folder 'env' sudah ada, melewati pembuatan venv."
    else
        python3 -m venv env
        success "Virtual environment dibuat di folder 'env'"
    fi

    # Activate
    source env/bin/activate
    success "Virtual environment aktif"

    # Upgrade pip diam-diam
    pip install --upgrade pip -q
}

# -------------------------------------------------------
# 4. Install Python Dependencies
# -------------------------------------------------------
install_dependencies() {
    step "Menginstall Python dependencies..."
    if [[ ! -f "requirements.txt" ]]; then
        error "File requirements.txt tidak ditemukan!"
    fi

    pip install --no-proxy -r requirements.txt -q
    success "Semua dependencies berhasil diinstall"
}

# -------------------------------------------------------
# 5. Install Ollama
# -------------------------------------------------------
install_ollama() {
    step "Memeriksa Ollama..."
    if command -v ollama &>/dev/null; then
        OLLAMA_VER=$(ollama --version 2>/dev/null | head -1)
        success "Ollama sudah terinstall: $OLLAMA_VER"
        return
    fi

    info "Ollama belum terinstall. Menginstall sekarang..."

    if [[ "$OS" == "macos" ]]; then
        if command -v brew &>/dev/null; then
            brew install ollama -q
            success "Ollama berhasil diinstall via Homebrew"
        else
            warn "Homebrew tidak ditemukan. Download Ollama manual dari: https://ollama.com/download"
            read -p "Tekan Enter setelah Ollama terinstall, atau Ctrl+C untuk batal..."
        fi
    elif [[ "$OS" == "debian" || "$OS" == "redhat" ]]; then
        curl -fsSL https://ollama.com/install.sh | sh
        success "Ollama berhasil diinstall"
    fi
}

# -------------------------------------------------------
# 6. Start Ollama Service
# -------------------------------------------------------
start_ollama() {
    step "Memastikan Ollama service berjalan..."

    if curl -s http://localhost:11434 &>/dev/null; then
        success "Ollama sudah berjalan di port 11434"
        return
    fi

    info "Menjalankan Ollama service..."
    if [[ "$OS" == "macos" ]]; then
        # macOS: jalankan sebagai background process
        ollama serve &>/dev/null &
    else
        # Linux: pakai systemctl jika tersedia
        if command -v systemctl &>/dev/null; then
            sudo systemctl enable ollama --now 2>/dev/null || ollama serve &>/dev/null &
        else
            ollama serve &>/dev/null &
        fi
    fi

    # Tunggu sampai siap (maks 15 detik)
    info "Menunggu Ollama siap..."
    for i in {1..15}; do
        if curl -s http://localhost:11434 &>/dev/null; then
            success "Ollama service berjalan"
            return
        fi
        sleep 1
    done

    warn "Ollama belum merespons. Lanjutkan, tapi pastikan Ollama berjalan sebelum menjalankan bot."
}

# -------------------------------------------------------
# 7. Pull AI Model (Qwen)
# -------------------------------------------------------
pull_model() {
    step "Mendownload AI Model Qwen..."
    info "Model: qwen2.5:3b (ringan, ~2GB, cocok untuk server biasa)"
    info "Jika ingin model lebih besar, edit bot.py dan ganti nama model."
    echo ""

    # Cek apakah model sudah ada
    if ollama list 2>/dev/null | grep -q "qwen"; then
        success "Model Qwen sudah tersedia"
        ollama list | grep qwen
        return
    fi

    warn "Mulai download model (~2GB). Ini bisa memakan waktu beberapa menit..."
    echo ""

    # Pull model qwen2.5:3b (lebih kecil & lebih update dari qwen)
    ollama pull qwen2.5:3b

    success "Model Qwen berhasil didownload"
}

# -------------------------------------------------------
# 8. Siapkan .env dari template
# -------------------------------------------------------
setup_env() {
    step "Menyiapkan file konfigurasi..."

    if [[ -f ".env" ]]; then
        success "File .env sudah ada. Melewati."
        return
    fi

    cp .env.example .env
    success "File .env dibuat dari .env.example"
    info "Jalankan 'make dev' — wizard akan memandu setup token bot dan login Google."
}

# -------------------------------------------------------
# 9. Final Summary
# -------------------------------------------------------
print_summary() {
    echo ""
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║         Instalasi Selesai!               ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${BOLD}Langkah selanjutnya:${NC}"
    echo ""
    echo -e "  ${CYAN}1.${NC} Jalankan bot (wizard setup otomatis berjalan pertama kali):"
    echo -e "     ${YELLOW}make dev${NC}"
    echo ""
    echo -e "  ${CYAN}2.${NC} Ganti model AI di .env jika diperlukan:"
    echo -e "     ${YELLOW}OLLAMA_MODEL=qwen2.5:7b${NC}  (lebih pintar, butuh RAM lebih besar)"
    echo ""
}

# -------------------------------------------------------
# MAIN
# -------------------------------------------------------
print_banner

# Pastikan script dijalankan dari root folder project
if [[ ! -f "requirements.txt" ]]; then
    error "Jalankan script ini dari root folder project (di mana requirements.txt berada)"
fi

detect_os
check_python
setup_venv
install_dependencies
install_ollama
start_ollama
pull_model
setup_env
print_summary
