#!/bin/bash
# Build the public novamind-bench repo from private saas-bench source.
#
# Usage:
#   cd projects/saas-bench
#   bash scripts/build_public.sh [--skip-binary]
#
# This script:
# 1. Generates static documentation from TOOL_DOCS/TABLE_DOCS
# 2. Builds the PyInstaller binary (unless --skip-binary)
# 3. Assembles the public/ directory with everything needed
# 4. Copies novamind_api Python package for agent use

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PUBLIC_DIR="$PROJECT_DIR/public"
SRC_DIR="$PROJECT_DIR/src"

SKIP_BINARY=false
if [[ "${1:-}" == "--skip-binary" ]]; then
    SKIP_BINARY=true
fi

echo "========================================"
echo "Building NovaMind Bench (public repo)"
echo "========================================"
echo "Project dir: $PROJECT_DIR"
echo "Public dir:  $PUBLIC_DIR"
echo ""

# 0. Purge stale bytecode (CRITICAL for editable/src installs)
# uv sync --reinstall-package does NOT clear .pyc files. Python may load
# old compiled bytecode instead of recompiling from updated .py sources.
echo "🧹 Purging __pycache__ bytecode..."
find "$PROJECT_DIR/src" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find "$PROJECT_DIR/src" -name "*.pyc" -delete 2>/dev/null || true
echo "✅ Bytecode cache cleared"
echo ""

# 1. Generate documentation
echo "📝 Generating documentation..."
cd "$PROJECT_DIR"
uv run python scripts/generate_public_docs.py --output "$PUBLIC_DIR/docs"
echo ""

# 2. Build PyInstaller binary
if [ "$SKIP_BINARY" = false ]; then
    echo "🔨 Building PyInstaller binary..."

    # Ensure pyinstaller is available
    uv pip install pyinstaller 2>/dev/null || true

    mkdir -p "$PUBLIC_DIR/bin"

    # Determine platform
    PLATFORM=$(uname -s | tr '[:upper:]' '[:lower:]')
    ARCH=$(uname -m)
    BINARY_NAME="novamind-server-${PLATFORM}-${ARCH}"

    cd "$PROJECT_DIR"
    uv run pyinstaller \
        --onefile \
        --name "$BINARY_NAME" \
        --distpath "$PUBLIC_DIR/bin" \
        --workpath "/tmp/pyinstaller-build" \
        --specpath "/tmp/pyinstaller-build" \
        --hidden-import saas_bench \
        --hidden-import saas_bench.config \
        --hidden-import saas_bench.database \
        --hidden-import saas_bench.simulation \
        --hidden-import saas_bench.tools \
        --hidden-import saas_bench.api_server \
        --hidden-import saas_bench.environment \
        --hidden-import saas_bench.event_logger \
        --hidden-import saas_bench.shocks \
        --hidden-import saas_bench.enterprise \
        --hidden-import saas_bench.customer_llm \
        --hidden-import saas_bench.personas \
        --hidden-import saas_bench.db_protection \
        --hidden-import saas_bench.docs_generator \
        --hidden-import saas_bench.novamind_cli \
        --hidden-import saas_bench.server_entry \
        --hidden-import numpy \
        --paths "$SRC_DIR" \
        "$SRC_DIR/saas_bench/server_entry.py"

    chmod +x "$PUBLIC_DIR/bin/$BINARY_NAME"
    echo "✅ Binary: $PUBLIC_DIR/bin/$BINARY_NAME"
    echo ""
else
    echo "⏭️  Skipping binary build (--skip-binary)"
    echo ""
fi

# 3. Copy novamind_api package (the Python client agents use)
echo "📦 Copying novamind_api package..."
NOVAMIND_API_SRC="$SRC_DIR/saas_bench/novamind_api"
NOVAMIND_API_DST="$PUBLIC_DIR/novamind_api"

rm -rf "$NOVAMIND_API_DST"
cp -r "$NOVAMIND_API_SRC" "$NOVAMIND_API_DST"
# Remove __pycache__
find "$NOVAMIND_API_DST" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
echo "✅ novamind_api → $NOVAMIND_API_DST"

# 4. Copy simulator instructions
echo "📄 Copying simulator instructions..."
cp "$SRC_DIR/saas_bench/agents/simulator_instructions.md" "$PUBLIC_DIR/docs/simulator-instructions.md" 2>/dev/null || true

# 5. Create install.sh
echo "📝 Creating install.sh..."
cat > "$PUBLIC_DIR/install.sh" << 'INSTALL_EOF'
#!/bin/bash
# NovaMind Bench — Quick Install
#
# Downloads the correct binary for your platform and makes it executable.
#
# Usage:
#   bash install.sh
#   # or
#   curl -fsSL <repo-url>/install.sh | bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="$SCRIPT_DIR/bin"

PLATFORM=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)
BINARY_NAME="novamind-server-${PLATFORM}-${ARCH}"
BINARY_PATH="$BIN_DIR/$BINARY_NAME"

echo "NovaMind Bench — Install"
echo "========================"
echo "Platform: $PLATFORM ($ARCH)"

if [ -f "$BINARY_PATH" ]; then
    chmod +x "$BINARY_PATH"
    chmod +x "$SCRIPT_DIR/novamind-operation"
    echo "✅ Binary found: $BINARY_PATH"
    echo "✅ CLI ready: $SCRIPT_DIR/novamind-operation"
    echo ""
    echo "Add to PATH:"
    echo "  export PATH=\"$SCRIPT_DIR:\$PATH\""
    echo ""
    echo "Quick start:"
    echo "  novamind-operation new-session --days 365"
    echo "  novamind-operation next-day"
else
    echo "❌ Binary not found for your platform: $BINARY_NAME"
    echo "   Available binaries:"
    ls "$BIN_DIR"/ 2>/dev/null || echo "   (none found in $BIN_DIR/)"
    echo ""
    echo "   You may need to build from source or download the correct binary."
    exit 1
fi
INSTALL_EOF
chmod +x "$PUBLIC_DIR/install.sh"

# 6. Create .gitignore for public repo
cat > "$PUBLIC_DIR/.gitignore" << 'GITIGNORE_EOF'
# Session data
sessions/

# Python
__pycache__/
*.pyo
.venv/

# OS
.DS_Store
Thumbs.db

# Editor
*.swp
*.swo
*~
GITIGNORE_EOF

echo ""
echo "========================================"
echo "✅ Build complete!"
echo "========================================"
echo ""
echo "Public repo structure:"
find "$PUBLIC_DIR" -type f | sort | head -50
echo ""
echo "To test:"
echo "  cd $PUBLIC_DIR"
echo "  ./novamind-operation new-session"
echo "  ./novamind-operation next-day"
