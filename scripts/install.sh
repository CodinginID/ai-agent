#!/bin/bash

# ==============================================================
#  AI Agent — One-line Installer
#  Usage: curl -fsSL https://raw.githubusercontent.com/CodinginID/ai-agent/main/install.sh | bash
# ==============================================================

set -e

REPO="CodinginID/ai-agent"
IMAGE="ghcr.io/${REPO,,}"
VERSION="${AI_AGENT_VERSION:-latest}"
INSTALL_DIR="${AI_AGENT_DIR:-$HOME/ai-agent}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC}   $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
step()    { echo -e "\n${BOLD}${CYAN}>>> $1${NC}"; }

print_banner() {
    echo -e "${CYAN}"
    echo "  ╔══════════════════════════════════════════╗"
    echo "  ║        AI Agent — Telegram Bot           ║"
    echo "  ║            Quick Installer               ║"
    echo "  ╚══════════════════════════════════════════╝"
    echo -e "${NC}"
}

# ── Cek dependencies ──────────────────────────────────────────────────────────
check_deps() {
    step "Memeriksa dependencies..."

    if ! command -v docker &>/dev/null; then
        error "Docker tidak ditemukan.\n  Install: https://docs.docker.com/engine/install/\n  Ubuntu : curl -fsSL https://get.docker.com | sh"
    fi
    success "Docker $(docker --version | cut -d' ' -f3 | tr -d ',')"

    if ! docker compose version &>/dev/null; then
        error "Docker Compose plugin tidak ditemukan. Update Docker ke versi terbaru."
    fi
    success "Docker Compose $(docker compose version --short)"

    if ! command -v curl &>/dev/null; then
        error "curl tidak ditemukan. Install: apt install curl"
    fi
}

# ── Buat direktori instalasi ─────────────────────────────────────────────────
setup_dir() {
    step "Menyiapkan direktori: $INSTALL_DIR"

    if [[ -d "$INSTALL_DIR" ]]; then
        warn "Direktori $INSTALL_DIR sudah ada."
        read -rp "  Lanjutkan dan timpa konfigurasi? [y/N]: " OVERWRITE
        [[ "${OVERWRITE,,}" == "y" ]] || error "Instalasi dibatalkan."
    fi

    mkdir -p "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    success "Direktori siap: $INSTALL_DIR"
}

# ── Download file konfigurasi ─────────────────────────────────────────────────
download_configs() {
    step "Mendownload konfigurasi..."

    BASE_URL="https://raw.githubusercontent.com/${REPO}/main"

    curl -fsSL "$BASE_URL/docker-compose.yml" -o docker-compose.yml
    success "docker-compose.yml"

    curl -fsSL "$BASE_URL/.env.example" -o .env.example
    success ".env.example"
}

# ── Setup .env ────────────────────────────────────────────────────────────────
setup_env() {
    step "Konfigurasi..."

    if [[ -f ".env" ]]; then
        warn "File .env sudah ada. Melewati konfigurasi ulang."
        return
    fi

    cp .env.example .env

    echo ""
    echo -e "${YELLOW}  Untuk mendapatkan Token Telegram Bot:${NC}"
    echo "  1. Buka Telegram → cari @BotFather"
    echo "  2. Ketik /newbot dan ikuti instruksinya"
    echo "  3. Copy token yang diberikan"
    echo ""

    read -rp "  Masukkan Telegram Bot Token: " BOT_TOKEN
    if [[ -n "$BOT_TOKEN" ]]; then
        sed -i.bak "s|TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=$BOT_TOKEN|" .env && rm -f .env.bak
        success "Token disimpan"
    else
        warn "Token kosong. Edit .env sebelum menjalankan bot."
    fi

    echo ""
    echo -e "${YELLOW}  (Opsional) Batasi akses ke Telegram user ID tertentu.${NC}"
    echo "  Kosongkan = semua orang bisa pakai bot."
    echo ""
    read -rp "  ADMIN_USER_IDS (pisah koma, atau Enter untuk skip): " ADMIN_IDS
    if [[ -n "$ADMIN_IDS" ]]; then
        sed -i.bak "s|ADMIN_USER_IDS=.*|ADMIN_USER_IDS=$ADMIN_IDS|" .env && rm -f .env.bak
        success "Admin IDs disimpan"
    fi
}

# ── Pull image & jalankan ─────────────────────────────────────────────────────
start_services() {
    step "Mendownload AI model dan menjalankan bot..."
    info "Image: $IMAGE:$VERSION"
    info "Proses pertama kali memerlukan ~5-10 menit (download model AI ~2GB)"
    echo ""

    # Update image reference di docker-compose.yml ke versi yang dipilih
    sed -i.bak "s|image: ghcr.io/codinginid/ai-agent:latest|image: $IMAGE:$VERSION|g" docker-compose.yml && rm -f docker-compose.yml.bak

    docker compose pull
    docker compose up -d

    success "Semua service berjalan"
}

# ── Ringkasan ──────────────────────────────────────────────────────────────────
print_summary() {
    echo ""
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║         Instalasi Selesai!               ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  Direktori : ${BOLD}$INSTALL_DIR${NC}"
    echo ""
    echo -e "  ${CYAN}Perintah yang berguna:${NC}"
    echo ""
    echo -e "  ${YELLOW}cd $INSTALL_DIR${NC}"
    echo -e "  ${YELLOW}docker compose logs -f bot${NC}    # lihat log"
    echo -e "  ${YELLOW}docker compose restart bot${NC}    # restart bot"
    echo -e "  ${YELLOW}docker compose down${NC}           # hentikan semua"
    echo -e "  ${YELLOW}docker compose pull && docker compose up -d${NC}  # update ke versi terbaru"
    echo ""
    echo -e "  Kirim ${BOLD}/start${NC} ke bot Telegram kamu untuk mulai."
    echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────
print_banner
check_deps
setup_dir
download_configs
setup_env
start_services
print_summary
