#!/usr/bin/env python3
import os
import sys
import subprocess
import datetime
import json
from pathlib import Path
import shutil
import tempfile

# Prüfe, ob Docker installiert ist und läuft
def check_docker():
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            print("Fehler: Docker ist nicht gestartet oder nicht korrekt installiert.")
            sys.exit(1)
    except FileNotFoundError:
        print("Fehler: Docker ist nicht installiert. Bitte installiere Docker.")
        sys.exit(1)
    except Exception as e:
        print(f"Fehler beim Prüfen von Docker: {e}")
        sys.exit(1)

try:
    from InquirerPy import inquirer
except ImportError:
    RED = "\033[91m"
    END = "\033[0m"
    print(f"{RED}Fehler: Das Python-Paket 'InquirerPy' ist nicht installiert!{END}")
    print("\nBitte installiere es auf macOS wie folgt:")
    print("1. Empfohlen: pipx verwenden (falls noch nicht installiert):")
    print("   brew install pipx && pipx ensurepath")
    print("2. Dann:")
    print("   pipx install InquirerPy")
    print("\nAlternativ in einer eigenen virtuellen Umgebung:")
    print("   python3 -m venv venv && source venv/bin/activate && pip install InquirerPy")
    print("\nWeitere Infos: https://github.com/kazhala/InquirerPy")
    sys.exit(1)

CONFIG_FILE = os.path.expanduser("~/.docker_backup_tool_config.json")

def is_git_installed():
    return subprocess.run(["git", "--version"], capture_output=True).returncode == 0

def git_config_menu(config):
    if not is_git_installed():
        print("Git ist nicht installiert. Bitte installiere Git, um diese Funktion zu nutzen.")
        input("[Enter] für Zurück...")
        return
    repo_url = inquirer.text(message="Git-Repository-URL angeben (z.B. https://github.com/user/repo.git):").execute()
    username = inquirer.text(message="Git-Benutzername (optional):").execute()
    email = inquirer.text(message="Git-E-Mail (optional):").execute()
    token = inquirer.secret(message="Personal Access Token (optional, für private Repos):").execute()
    # Token prüfen
    if repo_url and username and token:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(repo_url)
        netloc = f"{username}:{token}@{parsed.hostname}"
        if parsed.port:
            netloc += f":{parsed.port}"
        repo_url_with_token = urlunparse((parsed.scheme, netloc, parsed.path, '', '', ''))
        # Teste Token mit git ls-remote
        print("Prüfe Token...")
        test_result = subprocess.run(["git", "ls-remote", repo_url_with_token], capture_output=True)
        if test_result.returncode != 0:
            print("Fehler: Token ungültig oder keine Berechtigung für das Repo!")
            input("[Enter] für Zurück...")
            return
        else:
            print("Token erfolgreich geprüft.")
    config["git_repo"] = repo_url
    config["git_user"] = username
    config["git_email"] = email
    config["git_token"] = token
    save_config(config)
    print("Git-Konfiguration gespeichert.")
    input("[Enter] für Zurück...")
    return  # Nach Abschluss ins Hauptmenü

def git_commit_and_push(backup_path, config, repo_idx, files_to_add=None):
    repos = config.get("git_repos", [])
    if not is_git_installed() or not repos or repo_idx >= len(repos):
        return
    repo = repos[repo_idx]
    repo_url = repo["repo_url"]
    # Token in die URL einbauen, falls vorhanden
    if repo.get("git_token") and repo.get("git_user"):
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(repo_url)
        netloc = f"{repo['git_user']}:{repo['git_token']}@{parsed.hostname}"
        if parsed.port:
            netloc += f":{parsed.port}"
        repo_url_with_token = urlunparse((parsed.scheme, netloc, parsed.path, '', '', ''))
    else:
        repo_url_with_token = repo_url
    # Initialisiere Repo, falls nicht vorhanden
    if not os.path.exists(os.path.join(backup_path, ".git")):
        subprocess.run(["git", "init"], cwd=backup_path)
        subprocess.run(["git", "remote", "add", "origin", repo_url_with_token], cwd=backup_path)
    else:
        subprocess.run(["git", "remote", "set-url", "origin", repo_url_with_token], cwd=backup_path)
    if repo.get("git_user"):
        subprocess.run(["git", "config", "user.name", repo["git_user"]], cwd=backup_path)
    if repo.get("git_email"):
        subprocess.run(["git", "config", "user.email", repo["git_email"]], cwd=backup_path)
    # Nur gezielt die gewünschten Dateien hinzufügen
    if files_to_add:
        subprocess.run(["git", "add"] + files_to_add, cwd=backup_path)
    else:
        subprocess.run(["git", "add", "."], cwd=backup_path)
    subprocess.run(["git", "commit", "-m", f"Backup {datetime.datetime.now().isoformat()}"], cwd=backup_path)
    subprocess.run(["git", "branch", "-M", "main"], cwd=backup_path)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=backup_path)

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {"backup_path": str(Path.home() / "docker_backups")}


def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)


def select_action():
    return inquirer.select(
        message="Aktion wählen:",
        choices=[
            {"name": "Container snapshoten", "value": "backup"},
            {"name": "Wiederherstellen", "value": "restore"},
            {"name": "Einstellungen", "value": "settings"},
            {"name": "Beenden", "value": "exit"}
        ]
    ).execute()


def list_running_containers():
    result = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True)
    containers = result.stdout.strip().split("\n") if result.stdout.strip() else []
    return containers


def backup_container(container_name, backup_path, config=None, repo_idx=None):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    image_name = f"snapshot_{container_name}_{timestamp}"
    archive_name = f"{timestamp}_{container_name}.tar"
    archive_path = os.path.join(backup_path, str(datetime.datetime.now().year), str(datetime.datetime.now().month))
    os.makedirs(archive_path, exist_ok=True)
    # Commit
    subprocess.run(["docker", "commit", container_name, image_name], check=True)
    # Save
    archive_full_path = os.path.join(archive_path, archive_name)
    subprocess.run(["docker", "save", "-o", archive_full_path, image_name], check=True)
    # Optional: Remove temp image
    subprocess.run(["docker", "rmi", image_name], check=True)
    # Dateigröße anzeigen
    size_mb = os.path.getsize(archive_full_path) / (1024 * 1024)
    print(f"Backup gespeichert: {archive_full_path} ({size_mb:.2f} MB)")
    # Nachfragen, ob auf Git hochgeladen werden soll
    upload = False
    if config and config.get("git_repos") and repo_idx is not None:
        upload = inquirer.confirm(message="Backup ins Git-Repository hochladen?", default=True).execute()
    if upload and repo_idx is not None:
        git_commit_and_push(backup_path, config, repo_idx)

def config_backup_container(container_name, backup_path, config=None, repo_idx=None):
    import json as _json
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    archive_name = f"{timestamp}_{container_name}_config.tar"
    archive_path = os.path.join(backup_path, str(datetime.datetime.now().year), str(datetime.datetime.now().month))
    os.makedirs(archive_path, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        # Inspect Container
        result = subprocess.run(["docker", "inspect", container_name], capture_output=True, text=True)
        if result.returncode != 0:
            print("Fehler beim Auslesen der Container-Konfiguration.")
            return
        config_data = _json.loads(result.stdout)[0]
        # Speichere das Original-Image (nicht das evtl. temporäre Snapshot-Image)
        original_image = config_data.get("Config", {}).get("Image", "")
        # Volumes sichern
        volumes = config_data['Mounts']
        volume_archives = []
        for v in volumes:
            if v['Type'] == 'volume':
                vol_name = v['Name']
                vol_tar = os.path.join(tmpdir, f"{vol_name}.tar.gz")
                try:
                    subprocess.run([
                        "docker", "run", "--rm", "-v", f"{vol_name}:/data", "-v", f"{tmpdir}:/backup", "alpine",
                        "sh", "-c", f"tar czf /backup/{vol_name}.tar.gz -C /data ."
                    ], check=True)
                    if os.path.exists(vol_tar):
                        volume_archives.append(os.path.basename(vol_tar))
                    else:
                        print(f"Warnung: Volume-Archiv {vol_tar} wurde nicht erstellt!")
                except Exception as e:
                    print(f"Fehler beim Sichern des Volumes {vol_name}: {e}")
        # Schreibe Info-Text und Config-JSON ins temp dir
        info = {
            "info": "Dies ist ein platzsparendes Konfigurations-Backup. Es enthält KEINE Container-Daten außer den Volumes! Nur die Einstellungen, das verwendete Image und die Volumes werden gespeichert. Beim Wiederherstellen wird das Image erneut aus dem Internet geladen. Daten, die nicht in Volumes liegen, gehen verloren! Für vollständige Datensicherung bitte Volumes separat sichern.",
            "backup_time": timestamp,
            "container_name": container_name,
            "image": original_image,
            "config": config_data,
            "volumes": volume_archives
        }
        config_json_path = os.path.join(tmpdir, "config.json")
        with open(config_json_path, "w") as f:
            _json.dump(info, f, indent=2)
        # Erstelle das Archiv
        archive_full_path = os.path.join(archive_path, archive_name)
        subprocess.run(["tar", "cf", archive_full_path, "-C", tmpdir, "."], check=True)
        print(f"Konfigurations-Backup gespeichert: {archive_full_path}")
        print(f"Gesicherte Volumes: {', '.join(volume_archives) if volume_archives else 'Keine Volumes gefunden!'}")
        print("\nINFO: Dieses Backup enthält die Einstellungen, das verwendete Image und die Volumes.\n" \
              "Beim Wiederherstellen wird das Image erneut geladen. Daten, die nicht in Volumes liegen, gehen verloren!")
        # Nachfragen, ob auf Git hochgeladen werden soll
        upload = False
        if config and config.get("git_repos") and repo_idx is not None:
            upload = inquirer.confirm(message="Backup ins Git-Repository hochladen?", default=True).execute()
        if upload and repo_idx is not None:
            files_to_add = [os.path.basename(archive_full_path)]
            git_commit_and_push(archive_path, config, repo_idx, files_to_add=files_to_add)
            print("Backup-Archiv wurde ins Git-Repository hochgeladen.")

def config_restore_backup(config):
    import json as _json
    backup_path = config["backup_path"]
    # Suche alle *_config.json Backups
    config_backups = []
    for year in os.listdir(backup_path):
        year_path = os.path.join(backup_path, year)
        if not os.path.isdir(year_path):
            continue
        for month in os.listdir(year_path):
            month_path = os.path.join(year_path, month)
            if not os.path.isdir(month_path):
                continue
            for file in os.listdir(month_path):
                if file.endswith("_config.json"):
                    config_backups.append(os.path.join(year, month, file))
    if not config_backups:
        print("Keine Konfigurations-Backups gefunden.")
        input("[Enter] für Hauptmenü...")
        return
    choices = [{"name": b, "value": b} for b in config_backups] + [{"name": "Zurück", "value": "Zurück"}]
    backup_choice = inquirer.select(message="Konfigurations-Backup wählen (STRG+C für Hauptmenü):", choices=choices).execute()
    if backup_choice == "Zurück":
        return
    full_backup_path = os.path.join(backup_path, backup_choice)
    with open(full_backup_path, "r") as f:
        info = _json.load(f)
    image = info.get("image")
    container_name = info.get("container_name")
    config_data = info.get("config")
    volume_archives = info.get("volumes", [])
    print(f"Stelle Container '{container_name}' mit Image '{image}' wieder her...")
    # Image laden
    subprocess.run(["docker", "pull", image], check=True)
    # Entferne ggf. alten Container
    subprocess.run(["docker", "rm", "-f", container_name], check=False)
    # Volumes wiederherstellen
    archive_dir = os.path.dirname(full_backup_path)
    for vol_tar in volume_archives:
        vol_name = vol_tar.split(f"_{container_name}_")[-1].replace(".tar.gz", "")
        # Volume anlegen (falls nicht vorhanden)
        subprocess.run(["docker", "volume", "create", vol_name], check=False)
        # Daten ins Volume extrahieren
        vol_tar_path = os.path.join(archive_dir, vol_tar)
        if os.path.exists(vol_tar_path):
            subprocess.run([
                "docker", "run", "--rm", "-v", f"{vol_name}:/data", "-v", f"{archive_dir}:/backup", "alpine",
                "sh", "-c", f"tar xzf /backup/{vol_tar} -C /data"
            ], check=True)
            print(f"Volume {vol_name} wiederhergestellt aus {vol_tar}.")
        else:
            print(f"Warnung: Volume-Archiv {vol_tar} nicht gefunden, Volume bleibt leer!")
    # Starte neuen Container mit gespeicherter Config
    run_cmd = ["docker", "run", "-d", "--name", container_name]
    # Ports
    port_bindings = config_data['HostConfig'].get('PortBindings', {})
    for container_port, bindings in port_bindings.items():
        if bindings:
            for binding in bindings:
                host_port = binding.get("HostPort")
                if host_port:
                    run_cmd += ["-p", f"{host_port}:{container_port.split('/')[0]}"]
    # Env
    for env in config_data['Config'].get('Env', []):
        run_cmd += ["-e", env]
    # Labels
    for k, v in config_data['Config'].get('Labels', {}).items():
        run_cmd += ["--label", f"{k}={v}"]
    # Netzwerke (optional, Standard: bridge)
    networks = list(config_data['NetworkSettings']['Networks'].keys())
    for net in networks:
        run_cmd += ["--network", net]
    # Restart-Policy
    restart = config_data['HostConfig'].get('RestartPolicy', {})
    if restart.get('Name'):
        run_cmd += ["--restart", restart['Name']]
    # Volumes an den Container mounten
    for v in config_data['Mounts']:
        if v['Type'] == 'volume':
            run_cmd += ["-v", f"{v['Name']}:{v['Destination']}"]
    run_cmd.append(image)
    subprocess.run(run_cmd, check=True)
    print(f"Container '{container_name}' wurde aus Konfigurations-Backup wiederhergestellt.")
    print("\nINFO: Einstellungen, Image und Volumes wurden wiederhergestellt. Daten, die nicht in Volumes lagen, sind verloren!")
    input("[Enter] für Hauptmenü...")

def backup_menu(config):
    try:
        mode = inquirer.select(
            message="Backup-Modus wählen:",
            choices=[
                {"name": "Voll-Backup (Image sichern)", "value": "full"},
                {"name": "Konfigurations-Backup (Einstellungen + Volumes, kein Image)", "value": "config"},
                {"name": "Zurück", "value": "Zurück"}
            ]
        ).execute()
        if mode == "Zurück":
            return
        containers = list_running_containers()
        if not containers:
            print("Keine laufenden Container gefunden.")
            input("[Enter] für Zurück zum Hauptmenü...")
            return
        choices = [{"name": c, "value": c} for c in containers] + [{"name": "Zurück", "value": "Zurück"}]
        container = inquirer.select(message="Container wählen (STRG+C für Hauptmenü):", choices=choices).execute()
        if container == "Zurück":
            return
        repo_idx = None
        if config.get("git_repos"):
            repo_choices = [
                {"name": f"{r['repo_url']} (User: {r['git_user']})", "value": i}
                for i, r in enumerate(config["git_repos"])
            ] + [{"name": "Kein Git-Upload", "value": None}]
            repo_idx = inquirer.select(message="In welches Git-Repo hochladen?", choices=repo_choices).execute()
        if mode == "full":
            backup_container(container, config["backup_path"], config, repo_idx)
            input("Backup abgeschlossen. [Enter] für Hauptmenü...")
        elif mode == "config":
            config_backup_container(container, config["backup_path"], config, repo_idx)
            input("Konfigurations-Backup abgeschlossen. [Enter] für Hauptmenü...")
    except KeyboardInterrupt:
        print("\nZurück zum Hauptmenü...")
    return

def uninstall_software():
    import getpass
    bin_path = "/usr/local/bin/docker-backuptool"
    config_dir = os.path.expanduser("~/.docker_backup_tool")
    config_file = os.path.expanduser("~/.docker_backup_tool_config.json")
    errors = []
    # Lösche Symlink/Datei im bin
    if os.path.exists(bin_path):
        try:
            os.remove(bin_path)
            print("/usr/local/bin/docker-backuptool entfernt.")
        except PermissionError:
            print("Keine Berechtigung. Passwort wird für sudo benötigt...")
            password = getpass.getpass("Bitte Admin-Passwort eingeben: ")
            cmd = f'echo "{password}" | sudo -S rm "{bin_path}"'
            result = subprocess.run(cmd, shell=True)
            if result.returncode == 0:
                print("/usr/local/bin/docker-backuptool mit sudo entfernt.")
            else:
                errors.append("Fehler beim Entfernen von /usr/local/bin/docker-backuptool mit sudo.")
        except Exception as e:
            errors.append(f"Fehler beim Entfernen von /usr/local/bin/docker-backuptool: {e}")
    # Lösche config file
    if os.path.exists(config_file):
        try:
            os.remove(config_file)
            print("Konfigurationsdatei entfernt.")
        except Exception as e:
            errors.append(f"Fehler beim Entfernen der Konfigurationsdatei: {e}")
    # Lösche config dir (inkl. main.py)
    if os.path.exists(config_dir):
        try:
            shutil.rmtree(config_dir)
            print("Konfigurationsordner entfernt.")
        except Exception as e:
            errors.append(f"Fehler beim Entfernen des Konfigurationsordners: {e}")
    if not errors:
        print("Docker Backup Tool wurde vollständig deinstalliert.")
        print("Bitte beachten: Die Backups bleiben erhalten, aber die Software ist deinstalliert.")
        print("Wenn du die Backups nicht mehr benötigst, lösche den Ordner ~/.docker_backup_tool.")
        sys.exit(0)
    else:
        print("Folgende Fehler sind aufgetreten:")
        for err in errors:
            print("-", err)
        sys.exit(1)

def git_pull_repo(config):
    if not is_git_installed() or not config.get("git_repo"):
        print("Git ist nicht konfiguriert.")
        input("[Enter] für Hauptmenü...")
        return
    backup_path = config["backup_path"]
    if not os.path.exists(os.path.join(backup_path, ".git")):
        print("Kein Git-Repository initialisiert. Bitte zuerst ein Backup machen und Git konfigurieren.")
        input("[Enter] für Hauptmenü...")
        return
    print("Synchronisiere mit Git-Repository...")
    result = subprocess.run(["git", "pull"], cwd=backup_path)
    if result.returncode == 0:
        print("Synchronisierung erfolgreich.")
    else:
        print("Fehler bei der Synchronisierung.")
    input("[Enter] für Hauptmenü...")

def git_menu(config):
    while True:
        choice = inquirer.select(
            message="Git-Einstellungen:",
            choices=[
                {"name": "Repository hinzufügen", "value": "add"},
                {"name": "Repository löschen", "value": "delete"},
                {"name": "Repositories auflisten", "value": "list"},
                {"name": "Mit Git-Server abgleichen (Pull & Push)", "value": "sync"},
                {"name": "Zurück", "value": "back"}
            ]
        ).execute()
        if choice == "add":
            repo_url = inquirer.text(message="Git-Repository-URL (z.B. https://github.com/user/repo.git):").execute()
            username = inquirer.text(message="Git-Benutzername:").execute()
            email = inquirer.text(message="Git-E-Mail (optional):").execute()
            token = inquirer.secret(message="Personal Access Token (optional, für private Repos):").execute()
            # Token prüfen
            if repo_url and username and token:
                from urllib.parse import urlparse, urlunparse
                parsed = urlparse(repo_url)
                netloc = f"{username}:{token}@{parsed.hostname}"
                if parsed.port:
                    netloc += f":{parsed.port}"
                repo_url_with_token = urlunparse((parsed.scheme, netloc, parsed.path, '', '', ''))
                print("Prüfe Token...")
                test_result = subprocess.run(["git", "ls-remote", repo_url_with_token], capture_output=True)
                if test_result.returncode != 0:
                    print("Fehler: Token ungültig oder keine Berechtigung für das Repo!")
                    input("[Enter] für Zurück...")
                    continue
                else:
                    print("Token erfolgreich geprüft.")
            repo_entry = {
                "repo_url": repo_url,
                "git_user": username,
                "git_email": email,
                "git_token": token
            }
            config.setdefault("git_repos", []).append(repo_entry)
            save_config(config)
            print("Repository hinzugefügt.")
            input("[Enter] für Zurück...")
        elif choice == "delete":
            repos = config.get("git_repos", [])
            if not repos:
                print("Keine Repositories gespeichert.")
                input("[Enter] für Zurück...")
                continue
            repo_choices = [
                {"name": f"{r['repo_url']} ({r['git_user']})", "value": i}
                for i, r in enumerate(repos)
            ] + [{"name": "Abbrechen", "value": None}]
            idx = inquirer.select(message="Repository zum Löschen wählen:", choices=repo_choices).execute()
            if idx is not None:
                del config["git_repos"][idx]
                save_config(config)
                print("Repository gelöscht.")
                input("[Enter] für Zurück...")
        elif choice == "list":
            repos = config.get("git_repos", [])
            if not repos:
                print("Keine Repositories gespeichert.")
            else:
                print("Gespeicherte Repositories:")
                for r in repos:
                    print(f"- {r['repo_url']} (User: {r['git_user']})")
            input("[Enter] für Zurück...")
        elif choice == "sync":
            git_sync_repo(config)
        elif choice == "back":
            return

# Neue Funktion für Sync (Pull & Push)
def git_sync_repo(config):
    if not is_git_installed() or not config.get("git_repos"):
        print("Git ist nicht konfiguriert.")
        input("[Enter] für Zurück...")
        return
    backup_path = config["backup_path"]
    repo_choices = [
        {"name": f"{r['repo_url']} (User: {r['git_user']})", "value": i}
        for i, r in enumerate(config["git_repos"])
    ]
    repo_idx = inquirer.select(message="Welches Git-Repo synchronisieren?", choices=repo_choices).execute()
    repo = config["git_repos"][repo_idx]
    repo_url = repo["repo_url"]
    # Token in die URL einbauen, falls vorhanden
    if repo.get("git_token") and repo.get("git_user"):
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(repo_url)
        netloc = f"{repo['git_user']}:{repo['git_token']}@{parsed.hostname}"
        if parsed.port:
            netloc += f":{parsed.port}"
        repo_url_with_token = urlunparse((parsed.scheme, netloc, parsed.path, '', '', ''))
    else:
        repo_url_with_token = repo_url
    # Initialisiere Repo, falls nicht vorhanden
    if not os.path.exists(os.path.join(backup_path, ".git")):
        subprocess.run(["git", "init"], cwd=backup_path)
        subprocess.run(["git", "remote", "add", "origin", repo_url_with_token], cwd=backup_path)
    else:
        subprocess.run(["git", "remote", "set-url", "origin", repo_url_with_token], cwd=backup_path)
    if repo.get("git_user"):
        subprocess.run(["git", "config", "user.name", repo["git_user"]], cwd=backup_path)
    if repo.get("git_email"):
        subprocess.run(["git", "config", "user.email", repo["git_email"]], cwd=backup_path)
    print("Hole Änderungen vom Git-Server (git pull)...")
    pull_result = subprocess.run(["git", "pull"], cwd=backup_path)
    if pull_result.returncode == 0:
        print("Pull erfolgreich.")
    else:
        print("Fehler beim Pull.")
    print("Übertrage lokale Änderungen zum Git-Server (git push)...")
    subprocess.run(["git", "add", "."], cwd=backup_path)
    subprocess.run(["git", "commit", "-m", f"Sync {datetime.datetime.now().isoformat()}"] , cwd=backup_path)
    push_result = subprocess.run(["git", "push", "-u", "origin", "main"], cwd=backup_path)
    if push_result.returncode == 0:
        print("Push erfolgreich.")
    else:
        print("Fehler beim Push.")
    input("[Enter] für Zurück...")

def settings_menu(config):
    try:
        choice = inquirer.select(
            message="Einstellungen (STRG+C für Hauptmenü):",
            choices=[
                {"name": "Backup-Pfad ändern", "value": "path"},
                {"name": "Git-Repositories verwalten", "value": "git"},
                {"name": "Git-Repository synchronisieren", "value": "gitpull"},
                {"name": "Software deinstallieren", "value": "uninstall"},
                {"name": "Zurück", "value": "back"}
            ]
        ).execute()
        if choice == "path":
            new_path = inquirer.text(message=f"Backup-Pfad angeben (aktuell: {config['backup_path']}):").execute()
            if new_path:
                config["backup_path"] = new_path
                save_config(config)
                print(f"Backup-Pfad gespeichert: {new_path}")
                input("[Enter] für Hauptmenü...")
        elif choice == "git":
            git_menu(config)
        elif choice == "gitpull":
            git_pull_repo(config)
        elif choice == "uninstall":
            uninstall_software()
            input("[Enter] für Hauptmenü...")
        # Bei "back" einfach zurück
    except KeyboardInterrupt:
        print("\nZurück zum Hauptmenü...")
    return


def list_backups(backup_path):
    backups = []
    for year in os.listdir(backup_path):
        year_path = os.path.join(backup_path, year)
        if not os.path.isdir(year_path):
            continue
        for month in os.listdir(year_path):
            month_path = os.path.join(year_path, month)
            if not os.path.isdir(month_path):
                continue
            for file in os.listdir(month_path):
                if file.endswith(".tar"):
                    backups.append(os.path.join(year, month, file))
    return backups

def get_container_ports(container_name):
    result = subprocess.run([
        "docker", "inspect", container_name,
        "--format", '{{json .HostConfig.PortBindings}}'
    ], capture_output=True, text=True)
    import json as _json
    try:
        port_bindings = _json.loads(result.stdout)
        ports = []
        if port_bindings:
            for container_port, bindings in port_bindings.items():
                if bindings:
                    for binding in bindings:
                        host_port = binding.get("HostPort")
                        if host_port:
                            ports.append((host_port, container_port.split("/")[0]))
        return ports
    except Exception:
        return []

def get_container_config(container_name):
    import json as _json
    result = subprocess.run(["docker", "inspect", container_name], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    info = _json.loads(result.stdout)[0]
    config = {}
    # Ports
    config['ports'] = []
    port_bindings = info['HostConfig'].get('PortBindings', {})
    for container_port, bindings in port_bindings.items():
        if bindings:
            for binding in bindings:
                host_port = binding.get("HostPort")
                if host_port:
                    config['ports'].append((host_port, container_port.split("/")[0]))
    # Env
    config['env'] = info['Config'].get('Env', [])
    # Labels
    config['labels'] = info['Config'].get('Labels', {})
    # Networks
    config['networks'] = list(info['NetworkSettings']['Networks'].keys())
    # Restart policy
    restart = info['HostConfig'].get('RestartPolicy', {})
    if restart.get('Name'):
        config['restart'] = restart['Name']
    else:
        config['restart'] = None
    return config

def restore_backup(config):
    try:
        backup_path = config["backup_path"]
        # Sammle alle Backups (Voll-Backup .tar und Konfig-Backup _config.tar)
        all_backups = []
        for year in os.listdir(backup_path):
            year_path = os.path.join(backup_path, year)
            if not os.path.isdir(year_path):
                continue
            for month in os.listdir(year_path):
                month_path = os.path.join(year_path, month)
                if not os.path.isdir(month_path):
                    continue
                for file in os.listdir(month_path):
                    if file.endswith(".tar"):
                        all_backups.append(os.path.join(year, month, file))
        if not all_backups:
            print("Keine Backups gefunden.")
            input("[Enter] für Hauptmenü...")
            return
        choices = [{"name": b, "value": b} for b in all_backups] + [{"name": "Zurück", "value": "Zurück"}]
        backup_choice = inquirer.select(message="Backup wählen (STRG+C für Hauptmenü):", choices=choices).execute()
        if backup_choice == "Zurück":
            return
        full_backup_path = os.path.join(backup_path, backup_choice)
        if full_backup_path.endswith("_config.tar"):
            import tarfile
            import json as _json
            with tempfile.TemporaryDirectory() as tmpdir:
                with tarfile.open(full_backup_path, "r") as tar:
                    tar.extractall(tmpdir)
                config_json_path = os.path.join(tmpdir, "config.json")
                if not os.path.exists(config_json_path):
                    print("Fehler: config.json im Archiv nicht gefunden!")
                    input("[Enter] für Hauptmenü...")
                    return
                with open(config_json_path, "r") as f:
                    info = _json.load(f)
                image = info.get("image")
                container_name = info.get("container_name")
                config_data = info.get("config")
                volume_archives = info.get("volumes", [])
                print(f"Stelle Container '{container_name}' mit Image '{image}' wieder her...")
                # Prüfe, ob das Image lokal existiert
                local_images = subprocess.run(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"], capture_output=True, text=True)
                local_images_list = local_images.stdout.splitlines()
                if image not in local_images_list:
                    print(f"Image '{image}' nicht lokal gefunden. Versuche, es aus dem Internet zu laden...")
                    pull_result = subprocess.run(["docker", "pull", image])
                    if pull_result.returncode != 0:
                        print(f"Fehler: Image '{image}' konnte nicht geladen werden. Bitte prüfe, ob das Image öffentlich verfügbar ist oder führe ein Voll-Backup/Restore durch.")
                        input("[Enter] für Hauptmenü...")
                        return
                # Auswahl: existierenden Container ersetzen oder neuen erstellen
                running = list_running_containers()
                choices = [{"name": c, "value": c} for c in running] + [{"name": f"Neuen Container '{container_name}' erstellen", "value": None}]
                target_container = inquirer.select(message="Welcher Container soll ersetzt werden?", choices=choices).execute()
                if target_container:
                    subprocess.run(["docker", "rm", "-f", target_container], check=False)
                # Volumes wiederherstellen
                for vol_tar in volume_archives:
                    vol_name = vol_tar.replace(".tar.gz", "")
                    subprocess.run(["docker", "volume", "create", vol_name], check=False)
                    vol_tar_path = os.path.join(tmpdir, vol_tar)
                    if os.path.exists(vol_tar_path):
                        subprocess.run([
                            "docker", "run", "--rm", "-v", f"{vol_name}:/data", "-v", f"{tmpdir}:/backup", "alpine",
                            "sh", "-c", f"tar xzf /backup/{vol_tar} -C /data"
                        ], check=True)
                        print(f"Volume {vol_name} wiederhergestellt aus {vol_tar}.")
                    else:
                        print(f"Warnung: Volume-Archiv {vol_tar} nicht gefunden, Volume bleibt leer!")
                # Container starten wie gehabt
                run_cmd = ["docker", "run", "-d", "--name", container_name]
                port_bindings = config_data['HostConfig'].get('PortBindings', {})
                for container_port, bindings in port_bindings.items():
                    if bindings:
                        for binding in bindings:
                            host_port = binding.get("HostPort")
                            if host_port:
                                run_cmd += ["-p", f"{host_port}:{container_port.split('/')[0]}"]
                for env in config_data['Config'].get('Env', []):
                    run_cmd += ["-e", env]
                for k, v in config_data['Config'].get('Labels', {}).items():
                    run_cmd += ["--label", f"{k}={v}"]
                networks = list(config_data['NetworkSettings']['Networks'].keys())
                for net in networks:
                    run_cmd += ["--network", net]
                restart = config_data['HostConfig'].get('RestartPolicy', {})
                if restart.get('Name'):
                    run_cmd += ["--restart", restart['Name']]
                for v in config_data['Mounts']:
                    if v['Type'] == 'volume':
                        run_cmd += ["-v", f"{v['Name']}:{v['Destination']}"]
                run_cmd.append(image)
                subprocess.run(run_cmd, check=True)
                print(f"Container '{container_name}' wurde aus Konfigurations-Backup wiederhergestellt.")
                print("\nINFO: Einstellungen, Image und Volumes wurden wiederhergestellt. Daten, die nicht in Volumes lagen, sind verloren!")
                input("[Enter] für Hauptmenü...")
        elif full_backup_path.endswith(".tar"):
            # Voll-Backup (Image)
            filename = os.path.basename(full_backup_path)
            try:
                _, container_name = filename.split("_", 1)
                container_name = container_name.rsplit(".tar", 1)[0].split("_", 1)[1]
            except Exception:
                print("Konnte Containernamen nicht aus Dateiname extrahieren.")
                input("[Enter] für Hauptmenü...")
                return
            running = list_running_containers()
            run_choices = [{"name": c, "value": c} for c in running] + [{"name": f"Neuen Container '{container_name}' erstellen", "value": None}]
            target_container = inquirer.select(message="Welcher Container soll ersetzt werden?", choices=run_choices).execute()
            orig_config = None
            if target_container:
                orig_config = get_container_config(target_container)
                subprocess.run(["docker", "rm", "-f", target_container], check=False)
            subprocess.run(["docker", "volume", "prune", "-f"], check=False)
            subprocess.run(["docker", "load", "-i", full_backup_path], check=True)
            result = subprocess.run(["docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}"], capture_output=True, text=True)
            images = [img for img in result.stdout.splitlines() if container_name in img]
            if not images:
                print("Kein passendes Image gefunden.")
                input("[Enter] für Hauptmenü...")
                return
            image = images[0]
            run_cmd = ["docker", "run", "-d", "--name", container_name]
            if orig_config:
                for host_port, container_port in orig_config['ports']:
                    run_cmd += ["-p", f"{host_port}:{container_port}"]
                for env in orig_config['env']:
                    run_cmd += ["-e", env]
                for k, v in orig_config['labels'].items():
                    run_cmd += ["--label", f"{k}={v}"]
                for net in orig_config['networks']:
                    run_cmd += ["--network", net]
                if orig_config['restart']:
                    run_cmd += ["--restart", orig_config['restart']]
            run_cmd.append(image)
            subprocess.run(run_cmd, check=True)
            print(f"Backup wiederhergestellt und Container '{container_name}' neu gestartet.")
            input("[Enter] für Hauptmenü...")
    except KeyboardInterrupt:
        print("\nZurück zum Hauptmenü...")
    except Exception as e:
        print(f"Fehler: {e}")
    return

def main():
    print("=== Docker Backup Tool ===")
    check_docker()
    config = load_config()
    while True:
        action = select_action()
        if action == "backup":
            backup_menu(config)
        elif action == "restore":
            restore_backup(config)
        elif action == "settings":
            settings_menu(config)
        elif action == "exit":
            print("Beende Docker Backup Tool...")
            break

if __name__ == "__main__":
    main()
