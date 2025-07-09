#!/bin/bash

# --- Config ---
APP_NAME=$(basename "$PWD" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
FORMAL_NAME=$(basename "$PWD" | sed 's/-/ /g')
VENV_NAME="venv"
PYTHON_VERSION=${1:-python3}
BRIEFCASE_SUPPORT=true
GUI_SUPPORT=true

echo "📁 Setting up Python app project: $FORMAL_NAME"

# --- Create virtual environment ---
if [ ! -d "$VENV_NAME" ]; then
  echo "🐍 Creating virtual environment..."
  $PYTHON_VERSION -m venv "$VENV_NAME" || {
    echo "❌ Failed to create virtualenv. Try: sudo apt install python3-venv"
    exit 1
  }
fi

# --- Activate environment ---
source "$VENV_NAME/bin/activate"
echo "✅ Activated virtualenv: $VENV_NAME"

# --- Check pip exists ---
if [ ! -x "$VENV_NAME/bin/pip" ]; then
  echo "❌ pip not found in virtualenv."
  echo "Try: sudo apt install python3-pip python3-venv"
  exit 1
fi

# --- Install base packages ---
echo "📦 Installing dependencies..."
pip install --upgrade pip setuptools wheel

pip install requests || {
  echo "❌ Failed to install 'requests'. Check your internet connection or Python setup."
  exit 1
}

if $GUI_SUPPORT; then
  pip install PySide6 || {
    echo "❌ Failed to install PySide6. You may need to upgrade pip or install build tools."
    exit 1
  }
fi

if $BRIEFCASE_SUPPORT; then
  pip install briefcase || {
    echo "❌ Failed to install Briefcase."
    exit 1
  }
fi

# --- Create project scaffold ---
mkdir -p "src/$APP_NAME"
touch "src/$APP_NAME/__init__.py"
touch "src/$APP_NAME/__main__.py"

# --- Create pyproject.toml if needed ---
if [ ! -f pyproject.toml ]; then
  echo "📝 Creating pyproject.toml..."
  cat > pyproject.toml <<EOF
[tool.briefcase]
project_name = "$FORMAL_NAME"
bundle = "com.example.$APP_NAME"
version = "0.1.0"
description = "Python app created with setup script"
license = "MIT"
requires = ["requests", "PySide6"]

[tool.briefcase.app.$APP_NAME]
sources = ["src/$APP_NAME"]
resources = []
long_description = """
This is a cross-platform Python app named $FORMAL_NAME.
"""
EOF
fi

# --- Add default project docs ---
[ ! -f LICENSE ] && echo "MIT License" > LICENSE
[ ! -f README.md ] && echo "# $FORMAL_NAME" > README.md
[ ! -f CHANGELOG.md ] && echo -e "# Changelog\n\n## 0.1.0 - Initial setup" > CHANGELOG.md

echo "🎉 Python app environment ready!"
echo "Run: source $VENV_NAME/bin/activate"
