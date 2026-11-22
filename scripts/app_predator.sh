#!/bin/bash
# App do Predator no notebook: painel no navegador (http://127.0.0.1:8777) com vídeo, horizonte, telemetria, botões
# e gravação; pilotagem pelo teclado (ou botões) no modo do app. "janela" no fim usa a janela simples antiga.
#   scripts/app_predator.sh          SECO: só mostra vídeo e telemetria, não manda nada ao drone
#   scripts/app_predator.sh voar     manda comandos (pergunta antes). Teclas: T destrava, E/Q sobe/desce,
#                                    W/S frente/trás, D/A direita/esquerda, H segura, G manobra, L pousa, X emergência
#   scripts/app_predator.sh [voar] gestos   + gestos de braço pela câmera: braço esticado = aproximar 3 m,
#                                    Cristo = afastar 3 m, casinha = segurar (usa o Python de ../gestos/.venv)
cd "$(dirname "$0")/.." || exit 1
PY=~/.local/share/aruco-venv/bin/python
if ! ip -br addr show wlp2s0 | grep -q "192\.168\.0\."; then
    echo "O notebook não está no Wi-Fi do drone (WiFi-1080P-GPS-...). Conecte e rode de novo."; exit 1
fi
ARGS=(--app --basico --gravar --web)
for x in "$@"; do
    if [ "$x" = "janela" ]; then ARGS=("${ARGS[@]/--web}"); fi
    if [ "$x" = "gestos" ]; then PY=../gestos/.venv/bin/python; ARGS+=(--gestos); fi
done
if [ "$1" = "voar" ]; then
    echo "VOO: hélices presas, 5 m livres, ninguém perto, controle de rádio na mão, bateria conferida."
    read -r -p "Digite VOAR para confirmar: " resp
    [ "$resp" = "VOAR" ] || { echo "Cancelado."; exit 1; }
    ARGS+=(--voar --confirmo-voo)
fi
exec "$PY" -P scripts/piloto_predator.py "${ARGS[@]}"
