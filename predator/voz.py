"""Voz do Predator: toca frases pré-gravadas da pt-BR-ThalitaNeural em scripts/voz/p_*.wav.

Os arquivos foram gerados antes com edge-tts e convertidos para WAV mono/24 kHz; durante o uso,
`paplay` toca tudo offline. Nunca envia nada ao drone e nunca levanta erro: se faltar o arquivo
ou o paplay, fica em silêncio para não atrapalhar o voo.
"""
import os
import subprocess

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "voz")
VOZ_ORIGINAL = "pt-BR-ThalitaNeural"


def falar(nome, esperar=False):
    """Toca p_<nome>.wav. Sem esperar, não bloqueia o laço de controle."""
    arquivo = os.path.join(PASTA, f"p_{nome}.wav")
    if not os.path.exists(arquivo):
        return
    try:
        p = subprocess.Popen(["paplay", arquivo], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if esperar:
            p.wait(timeout=10)
    except Exception:
        pass
