#!/bin/bash
# PostgreSQL backup script
# Usage: scripts/backup.sh [--local-only] [--s3-only]

set -e

# --- Configuration ---
DB_HOST="${DB_HOST:-localhost}"
DB_USER="${DB_USER:-postgres}"
DB_NAME="${DB_NAME:-octopus}"
BACKUP_DIR="/backups"
S3_BUCKET="s3://backups/octopus"
S3_PREFIX="postgresql"

# --- Parse arguments ---
LOCAL_ONLY=false
S3_ONLY=false

for arg in "$@"; do
  case "$arg" in
    --local-only)
      LOCAL_ONLY=true
      ;;
    --s3-only)
      S3_ONLY=true
      ;;
    --help|-h)
      echo "Usage: $0 [--local-only] [--s3-only]"
      echo ""
      echo "Options:"
      echo "  --local-only  Only perform local backup, skip S3 upload"
      echo "  --s3-only     Only perform S3 operations (cleanup), skip local backup"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

# --- Logging ---
LOG_FILE="${BACKUP_DIR}/backup_$(date +%Y-%m-%d_%H-%M-%S).log"

log() {
  local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
  echo "$msg"
  echo "$msg" >> "$LOG_FILE"
}

log_error() {
  log "ERROR: $1"
}

# --- Timestamps ---
DATE=$(date +%Y%m%d_%H%M%S)
SQL_FILE="${BACKUP_DIR}/backup_${DATE}.sql"
GZ_FILE="${BACKUP_DIR}/backup_${DATE}.sql.gz"

# --- Functions ---

backup_local() {
  log "Starting local backup of database '${DB_NAME}' on host '${DB_HOST}'..."

  # Ensure backup directory exists
  mkdir -p "$BACKUP_DIR"

  # Dump database
  log "Running pg_dump..."
  pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" > "$SQL_FILE"

  # Compress
  log "Compressing with gzip..."
  gzip "$SQL_FILE"

  local size
  size=$(du -h "$GZ_FILE" | cut -f1)
  log "Local backup saved: ${GZ_FILE} (${size})"
}

upload_to_s3() {
  if [ -z "$AWS_ACCESS_KEY_ID" ]; then
    log "AWS_ACCESS_KEY_ID not set, skipping S3 upload."
    return 0
  fi

  if ! command -v aws &> /dev/null; then
    log "aws CLI not found, skipping S3 upload."
    return 0
  fi

  log "Uploading to S3: ${S3_BUCKET}/${S3_PREFIX}/backup_${DATE}.sql.gz..."
  aws s3 cp "$GZ_FILE" "${S3_BUCKET}/${S3_PREFIX}/backup_${DATE}.sql.gz"
  log "S3 upload complete."
}

cleanup_local() {
  log "Cleaning up local backups older than 30 days..."
  find "$BACKUP_DIR" -name "*.sql.gz" -mtime +30 -delete
  log "Local cleanup complete."
}

cleanup_s3() {
  if [ -z "$AWS_ACCESS_KEY_ID" ]; then
    log "AWS_ACCESS_KEY_ID not set, skipping S3 cleanup."
    return 0
  fi

  if ! command -v aws &> /dev/null; then
    log "aws CLI not found, skipping S3 cleanup."
    return 0
  fi

  log "Cleaning up S3 objects older than 30 days..."
  aws s3 rm "$S3_BUCKET/${S3_PREFIX}/" --recursive --older-than 30D
  log "S3 cleanup complete."
}

# --- Main ---

# S3-only mode: just cleanup
if [ "$S3_ONLY" = true ]; then
  cleanup_s3
  log "S3-only cleanup finished."
  exit 0
fi

# Local backup + S3 upload
backup_local

if [ "$LOCAL_ONLY" = true ]; then
  log "Local-only mode: skipping S3 operations."
  exit 0
fi

# S3 upload
upload_to_s3

# Cleanup old backups (both local and S3)
cleanup_local
cleanup_s3

log "Backup workflow finished."
