"""Cópias LIMPAS da telemetria real dos voos, para treino: posição em metros a partir do ponto de partida, SEM latitude/longitude.

Lê capturas/{voo1m_*,voofrente_*,eixos_*,piloto_*/dados.csv,gravacao_*/telemetria.csv} (só leitura) e grava ia/reais/*.csv
mais ia/reais/INDICE.json com o que cada arquivo é (comando enviado por fase, quando se sabe). Não lê imagens nem vídeos.
Uso: python3 -P scripts/prepara_dados_reais.py
"""
import csv
import glob
import json
import math
import os

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CAP, SAIDA = os.path.join(RAIZ, "capturas"), os.path.join(RAIZ, "ia", "reais")
os.makedirs(SAIDA, exist_ok=True)

# o que cada voo mandou (do diário de 20/11); valores em µs do manche, 1500 = neutro
NOTAS = {
    "voo1m_20261120_084929": "decolar por 0x94 (não subiu); sem acelerador",
    "voo1m_20261120_145855": "pulso de acelerador 1650 por 1 s e depois neutro; subiu a ~3 m/s e capotou",
    "voo1m_20261120_150130": "pulso 1650; deitou de lado",
    "voo1m_20261120_150505": "pulso 1550; não saiu do chão",
    "voo1m_20261120_150649": "pulso 1600; ~20 cm",
    "voo1m_20261120_151033": "pulso 1600, sem vento; não decolou",
    "voo1m_20261120_151209": "pulso 1625; pequeno salto",
    "voofrente_20261120_151454": "pulso 1625 por 1 s e depois desvio de pitch +60 com acelerador 1600 por 1,5 s (fase 'frente'); foi para a DIREITA e subiu",
    "eixos_frente_20261120_182234": "pulso 1625, depois pitch +60 com acelerador 1550 por 1,5 s (fase 'frente')",
    "eixos_direita_20261120_210706": "pulso 1625, depois roll +60 com acelerador 1550 por 1,5 s (fase 'direita'); perdeu o controle",
}
CAMPOS = ["t", "fase", "estado", "modo", "altura", "v_vert", "v_hor", "distancia", "satelites", "bateria", "roll", "pitch", "yaw",
          "leste_m", "norte_m", "roll_us", "pitch_us", "yaw_us", "acel_us"]


def le(caminho):
    return list(csv.DictReader(open(caminho)))


def pega(x, *nomes):
    for n in nomes:
        if n in x and x[n] != "":
            return x[n]
    return ""


def converte(linhas, nome):
    base = None
    saida = []
    t0 = None
    for x in linhas:
        lat, lon = pega(x, "lat"), pega(x, "lon")
        sats = pega(x, "satellites", "satelites", "satélites")
        e = n = ""
        try:
            if lat and lon and float(lat) != 0 and int(float(sats or 0)) >= 8:
                la, lo = float(lat), float(lon)
                if base is None:
                    base = (la, lo)
                n = round((la - base[0]) * 111320, 2)
                e = round((lo - base[1]) * 111320 * math.cos(math.radians(base[0])), 2)
        except ValueError:
            pass
        t = float(x["t"])
        t0 = t if t0 is None else t0
        saida.append({
            "t": round(t - t0, 3), "fase": pega(x, "fase"), "estado": pega(x, "state", "estado"), "modo": pega(x, "mode", "modo"),
            "altura": pega(x, "height", "altura"), "v_vert": pega(x, "v_speed", "v_vert"), "v_hor": pega(x, "h_speed", "v_hor"),
            "distancia": pega(x, "distance", "distancia"), "satelites": sats, "bateria": pega(x, "battery", "bateria"),
            "roll": pega(x, "roll"), "pitch": pega(x, "pitch"), "yaw": pega(x, "yaw"), "leste_m": e, "norte_m": n,
            "roll_us": pega(x, "roll_us"), "pitch_us": pega(x, "pitch_us"), "yaw_us": pega(x, "yaw_us"), "acel_us": pega(x, "acel_us")})
    return saida


indice = {}
arquivos = (sorted(glob.glob(f"{CAP}/voo1m_2026*.csv")) + sorted(glob.glob(f"{CAP}/voofrente_2026*.csv")) +
            sorted(glob.glob(f"{CAP}/eixos_*_2026*.csv")) + sorted(glob.glob(f"{CAP}/piloto_*/dados.csv")) +
            sorted(glob.glob(f"{CAP}/gravacao_*/telemetria.csv")))
for caminho in arquivos:
    nome = os.path.basename(os.path.dirname(caminho)) if caminho.endswith(("dados.csv", "telemetria.csv")) else os.path.basename(caminho)[:-4]
    if caminho.endswith("telemetria.csv"):
        nome += "_telemetria"
    elif caminho.endswith("dados.csv"):
        nome += "_dados"
    try:
        linhas = le(caminho)
        if not linhas or "t" not in linhas[0]:
            continue
        saida = converte(linhas, nome)
    except (OSError, ValueError, KeyError) as e:
        print("pulado", nome, e)
        continue
    with open(os.path.join(SAIDA, nome + ".csv"), "w", newline="") as f:
        w = csv.DictWriter(f, CAMPOS)
        w.writeheader()
        w.writerows(saida)
    dur = saida[-1]["t"] - saida[0]["t"]
    indice[nome] = {"linhas": len(saida), "duracao_s": round(dur, 1),
                    "nota": NOTAS.get(nome, "piloto pelo teclado (comandos em roll_us/pitch_us/yaw_us/acel_us)" if nome.startswith("piloto_")
                                      else "só telemetria, drone sem voar, sem comando enviado" if "telemetria" in nome else "")}
json.dump(indice, open(os.path.join(SAIDA, "INDICE.json"), "w"), indent=1, ensure_ascii=False)
print(f"{len(indice)} arquivos limpos em ia/reais/ (sem latitude/longitude); {sum(v['duracao_s'] for v in indice.values()):.0f} s no total")
