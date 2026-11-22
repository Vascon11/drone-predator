# Voz do Predator

As frases `p_*.wav`, `e_*.wav`, `c_*.wav` e `f_*.wav` usam a voz neural
`pt-BR-ThalitaNeural`, escolhida pelo usuário em 20/11/2026 após comparação com
`pt-BR-FranciscaNeural`.

Os áudios são gerados previamente com `edge-tts`, convertidos para WAV mono a 24 kHz e
tocados offline com `paplay`. Isso é necessário porque o Wi-Fi do drone não oferece internet.

Exemplo de geração:

```bash
edge-tts --voice pt-BR-ThalitaNeural --text "Drone travado." --write-media frase.mp3
ffmpeg -i frase.mp3 -ar 24000 -ac 1 frase.wav
```

Não gerar fala dinâmica durante o voo. Se não houver telemetria, a frase deve informar
"sem sinal do drone" em vez de inferir ou inventar um estado.
