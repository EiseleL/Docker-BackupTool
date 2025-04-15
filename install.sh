#!/bin/bash
# Installationsskript für Docker Backup Tool
set -e
CONFIG_DIR="$HOME/.docker_backup_tool"
SCRIPT_NAME="docker-backuptool"
INSTALL_PATH="/usr/local/bin/$SCRIPT_NAME"

# Erstelle Config-Ordner, falls nicht vorhanden
mkdir -p "$CONFIG_DIR"

# Kopiere main.py in den Config-Ordner
cp main.py "$CONFIG_DIR/main.py"
chmod +x "$CONFIG_DIR/main.py"

# Erstelle Wrapper-Skript im /usr/local/bin
cat << 'EOF' | sudo tee "$INSTALL_PATH" > /dev/null
#!/bin/bash
python3 "$HOME/.docker_backup_tool/main.py" "$@"
EOF
sudo chmod +x "$INSTALL_PATH"

echo "Installation abgeschlossen. Starte das Tool mit: $SCRIPT_NAME"