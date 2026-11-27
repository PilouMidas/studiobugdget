#!/bin/bash
# Picturial — Devis de production : lanceur local (macOS, fonctionne aussi sous Linux).
# Double-cliquez sur ce fichier : il démarre le serveur local, attend qu'il soit prêt,
# puis ouvre l'application dans votre navigateur par défaut sur http://127.0.0.1:PORT/
# Si l'application tourne déjà, il rouvre simplement l'instance existante.
set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
SERVER="$DIR/server.py"
DATA_DIR="${PICTURIAL_DATA_DIR:-$HOME/Library/Application Support/Picturial}"
mkdir -p "$DATA_DIR" 2>/dev/null || true
LOCK="$DATA_DIR/serveur.json"
LOG="$DATA_DIR/serveur.log"

msg_dialog() {
  echo "$1"
  if command -v osascript >/dev/null 2>&1; then
    osascript -e "display dialog \"$1\" with title \"Picturial — Devis de production\" buttons {\"OK\"} default button \"OK\"" >/dev/null 2>&1 || true
  fi
}

ouvrir_url() {
  if command -v open >/dev/null 2>&1; then
    open "$1"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$1" >/dev/null 2>&1 || echo "Ouvrez $1 dans votre navigateur."
  else
    echo "Ouvrez $1 dans votre navigateur."
  fi
}

# 1. Détecter Python 3 (présent sur macOS ; si la boîte de dialogue Apple apparaît, installez
#    les « Command Line Developer Tools » puis relancez ce fichier).
PY=""
for c in python3 /usr/bin/python3 python; do
  if command -v "$c" >/dev/null 2>&1; then
    if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
      PY="$(command -v "$c")"
      break
    fi
  fi
done
if [ -z "$PY" ]; then
  msg_dialog "Python 3 est nécessaire mais aucune version utilisable n'a été trouvée. Sur Mac : ouvrez le Terminal, exécutez « xcode-select --install » (une fenêtre système vous le propose aussi), puis double-cliquez à nouveau sur « Ouvrir le devis.command »."
  exit 1
fi

# 2. Une instance tourne déjà ? -> on rouvre simplement la bonne URL.
if [ -f "$LOCK" ]; then
  PORT="$( "$PY" -c 'import json,sys
try:
    print(json.load(open(sys.argv[1])).get("port",""))
except Exception:
    print("")' "$LOCK" 2>/dev/null || echo "")"
  if [ -n "$PORT" ]; then
    if "$PY" -c 'import urllib.request,sys
urllib.request.urlopen("http://127.0.0.1:"+sys.argv[1]+"/api/health", timeout=2)' "$PORT" >/dev/null 2>&1; then
      ouvrir_url "http://127.0.0.1:$PORT/"
      exit 0
    fi
  fi
fi

# 3. Choisir un port libre (évite le conflit « port déjà occupé »).
PORT="$( "$PY" -c 'import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()' 2>/dev/null || echo "")"
if [ -z "$PORT" ]; then
  msg_dialog "Impossible de réserver un port local pour le serveur. Réessayez dans un instant."
  exit 1
fi

# 4. Démarrer le serveur local (boucle locale uniquement, jamais exposé sur le réseau).
PICTURIAL_DATA_DIR="$DATA_DIR" PICTURIAL_DB="$DATA_DIR/devis.db" \
  nohup "$PY" "$SERVER" --host 127.0.0.1 --port "$PORT" >"$LOG" 2>&1 &
SRV_PID=$!

# 5. Attendre que le serveur soit prêt (jusqu'à ~30 secondes).
OK=0
i=0
while [ "$i" -lt 60 ]; do
  if "$PY" -c 'import urllib.request,sys
urllib.request.urlopen("http://127.0.0.1:"+sys.argv[1]+"/api/health", timeout=1)' "$PORT" >/dev/null 2>&1; then
    OK=1
    break
  fi
  if ! kill -0 "$SRV_PID" 2>/dev/null; then
    break
  fi
  sleep 0.5
  i=$((i + 1))
done

if [ "$OK" != "1" ]; then
  msg_dialog "Le serveur n'a pas démarré (port peut-être occupé entre-temps, ou erreur de lancement). Consultez le journal : $LOG — puis relancez « Ouvrir le devis.command »."
  exit 1
fi

echo "Picturial — serveur de devis prêt sur http://127.0.0.1:$PORT/ (données : $DATA_DIR)"
ouvrir_url "http://127.0.0.1:$PORT/"
