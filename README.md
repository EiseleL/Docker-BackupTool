# Docker Backup Tool

Ein plattformübergreifendes CLI-Tool für komfortable Docker-Backups, Wiederherstellung und Git-Integration.

## Features
- **Voll-Backup:** Sichert laufende Container als Image (.tar) inkl. Konfiguration
- **Konfigurations-Backup:** Sichert Container-Konfiguration und Volumes platzsparend als JSON + .tar.gz
- **Automatische Wiederherstellung:** Erkennt Backup-Typ und stellt Container, Konfiguration und Volumes wieder her
- **Git-Integration:** Backups können in beliebig viele Git-Repositories versioniert werden
- **Repository-Verwaltung:** Repos hinzufügen, löschen, auswählen, synchronisieren
- **Plattformübergreifend:** Funktioniert auf macOS, Linux und Windows (mit WSL)

- **Einfache Deinstallation:** Entfernt alle Programmdateien und Einstellungen

## Voraussetzungen
- Python 3.8 oder neuer
- Docker installiert und lauffähig
- Git installiert (für Git-Features)

## Installation
1. **Repository klonen**
   ```sh
   git clone https://github.com/EiseleL/Docker-BackupTool.git
   cd docker-backup-tool
   ```
2. **Abhängigkeiten installieren**
   ```sh
   pip install InquirerPy
   ```
   oder
   ```sh
   pip install -r requirements.txt
   ```
3. **Installationsskript ausführen**
   ```sh
   ./install.sh
   ```
   oder
   ```sh
   sh install.sh
   ```
   Das Skript kopiert die aktuelle main.py in den Config-Ordner (`~/.docker_backup_tool`) und erstellt/überschreibt den Befehl `docker-backuptool`.

## Nutzung

Starte das Tool mit:
```sh
docker-backuptool
# oder (im Projektordner)
python main.py
```

## Deinstallation
Im Tool unter Einstellungen → „Software deinstallieren“ wählen. Es werden alle Programmdateien, die Konfiguration und der Befehl `docker-backuptool` entfernt.

## Hinweise
- Für Windows wird WSL empfohlen.
- Für private Git-Repos wird ein Personal Access Token benötigt.
- Backups werden standardmäßig im Home-Verzeichnis unter `docker_backups` gespeichert (anpassbar im Tool).
- Konfigurations-Backups enthalten keine Daten außerhalb von Volumes!
- Nach der Installation kann der ursprüngliche Download-Ordner gelöscht werden.

## Lizenz
MIT License

---
Letztes Update: 15. April 2025
