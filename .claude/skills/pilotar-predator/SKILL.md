---
name: pilotar-predator
description: Prepara, confere e conduz voos de teste do drone Predator (hexacóptero Lewei, UDP 192.168.0.1:50000) pelo notebook, com checagens só de leitura, calibração e o voo curto do voo_1m.py. Use quando o usuário pedir para pilotar, decolar, calibrar, testar voo ou analisar um voo do Predator. Nunca envia comando de voo sem autorização explícita do usuário naquele voo.
---

# Pilotar o Predator

O Predator só tem **um** voo automatizado: `scripts/voo_1m.py` (decola, sobe ~0,8 m ou 6 s e pousa). O resto
são scripts de leitura e calibração. Não existe piloto de IA para o Predator, e o manche e o sentido dos eixos
nunca foram confirmados em voo. `controle.py` é para uma pessoa pilotar, não para mim.

## Regra de ouro

**Só mando comando que mova motor (destravar, decolar, manche, pouso) depois que o usuário autoriza, em
palavras dele, ESTE voo.** Uma autorização vale para um voo. "Pode rodar a calibração" não autoriza voo, e o
voo de ontem não autoriza o de hoje. Se tiver dúvida, pergunto.

Nunca rodo `voo_1m.py --confirmo-voo`, `controle.py` ou `teste_motores.py` por conta própria, nem os coloco em
lista de permissões. Também não contorno um pedido de confirmação do sistema.

## Fase 1 — só leitura (sem pedir permissão)

Rodar sempre com `python3 -P scripts/<nome>.py`. O `-P` é obrigatório: `scripts/dis.py` esconde o módulo `dis`
da biblioteca padrão.

1. Rede: `ip -br addr show wlp2s0` deve mostrar `192.168.0.x`. Se não, pedir ao usuário que conecte no Wi-Fi
   `WiFi-1080P-GPS-XXXXXX` (5 GHz). A rede de casa (cabo) também é `192.168.0.x`; os scripts prendem a
   `wlp2s0`.
2. `scripts/probe.py 8` mostra a telemetria. Conferir:
   - estado (nibble baixo do byte do `0x88`) = **0**, drone travado;
   - roll/pitch dentro de ±1°; satélites e `gps_fix` no `0x89`;
   - bateria (o byte não tem unidade confirmada; usar a tensão real do multímetro, se houver).
3. `scripts/telemetria_voo.py [s] [arquivo]` grava a telemetria em CSV.
4. **Câmera:** `scripts/gravar_voo.py [segundos] [--fotos]` grava o vídeo (TCP 7060, H.264 1280×720) e a
   telemetria com o **mesmo relógio** em `capturas/gravacao_<hora>/` (`video.h264`, `quadros.csv`,
   `telemetria.csv`; `--fotos` salva 1 jpg por segundo). É só leitura. A imagem **não vem pela telemetria**:
   são dois caminhos separados do drone. Não há campo de ângulo do gimbal na telemetria conhecida.
   **Testado em 20/11 com o drone parado e travado:** 10 s deram 124 quadros (12,6 fps, 1280×720), 89 linhas
   de telemetria (~9 Hz) e 6 fotos, no mesmo relógio. Se `video.h264` sair vazio, o notebook provavelmente não
   está na rede do drone (`ip -br addr show wlp2s0` deve dar `192.168.0.20`). Para vê-la: `ffplay video.h264`.
   Para ver uma foto, extrair com ffmpeg e abrir só a que o usuário pedir.

## Bateria (IMPORTANTE — olhar antes de qualquer voo)

O campo `bateria` do `0x89` (último byte) é tratado como **%**, mas a unidade **não foi confirmada**. Dados reais:

| Situação | Leitura |
|---|---|
| Parado, 01/11 (3 primeiros testes) | 80–82, e sob carga ficou em 68–69 |
| Parado, 01/11 depois de voos | 56–62 (voltava a ~60 em repouso) |
| Voo de 80 | caiu para **17** e terminou em 50 |
| Voo de 61–62 | caiu para **0** (leitura) e o drone seguiu voando/pousando |
| Parado em casa, 20/11 | 47–49 |

Leitura: a bateria (2S 7,4 V, 1200–1500 mAh, **provavelmente gasta**) **afunda muito sob carga**; o número em repouso
engana. Conferir a etiqueta real e a tensão com multímetro quando possível (pendência em `hardware/README.md`).

Regras desta skill:
- Sempre informar ao usuário a bateria em repouso **antes** de pedir autorização de voo, e dizer o que o
  número significa (unidade não confirmada).
- O `voo_1m.py` só recusa se a média em repouso for < 30; **eu sou mais conservador**: não proponho voo com
  menos de ~70 em repouso (os voos que partiram de ~61 chegaram a 0 de leitura). Essa regra é minha, não do
  script, e vale rever quando tivermos a tensão medida.
- Durante o voo, vigiar o campo; se a leitura cair abaixo de ~30 ou o drone indicar retorno por bateria (bit7
  do byte de flags do `0x89`), mando pousar.
- Pousou e travou: deixar a bateria descansar e conferir a leitura de novo antes de outro voo; um segundo voo
  seguido com a bateria fraca é o caso de maior risco.

## Fase 2 — calibração (peço confirmação ao usuário, drone travado, no chão)

`scripts/calibrar_completo.py --confirmo [--so-acel | --so-bussola] [--passadas 2]`. Só envia `0x7A F1` e
`0x7A E1`.
- Acelerômetro: drone **nivelado no celular** (0,0°/0,0°), tirar a mão. O resultado esperado é roll/pitch em
  ~0,00°; a sequência é `7a f1` → `7a f2` e o byte 4 do `0x28` vai de `00` para `02`. Mão no drone estraga a
  medida (aconteceu em 20/11).
- Bússola: fazer **ao ar livre, longe de metal, carro e celular**. O usuário gira o drone; o script compara o
  rumo com a bússola do celular. A variação entre rumos é o que importa.
- Dentro de casa o GPS tem ~2 satélites e a bússola é pior. A calibração que vale é a do campo.

## Fase 3 — checklist antes do voo (conferir TODOS com o usuário)

- Local aberto, grama, sem pessoas a menos de 5 m, alguém olhando o drone; hélices presas e sem folga.
- Bateria carregada (a antiga cai de ~68% para ~25% sob carga); drone no chão, no solo plano.
- Telemetria: travado, **10 ou mais satélites**, `gps_fix` verdadeiro, 30 s parado depois de firmar.
- Calibração de acelerômetro e de bússola feitas no local.
- Controle físico 2,4 GHz **ligado e na mão do usuário** como corte de emergência (a prioridade entre ele e o
  manche por Wi-Fi nunca foi testada, então não conto com ela).
- Usuário diz explicitamente que autoriza o voo.

Se algum item falhar, não voo e explico o que falta.

## Fase 4 — voo

```
python3 -P scripts/voo_1m.py --confirmo-voo
```
Limites embutidos no script: distância 5 m, velocidade 2 m/s, inclinação 25° (pousa), capotar corta motores
(60° por 0,3 s), 10 s sem subir trava no chão, mínimo de 8 satélites e 30% de bateria. Ctrl+C ou erro manda
pousar. Eu acompanho a saída; se o usuário disser "para", mando Ctrl+C e pouso, nunca corto motor no ar a
menos que ele peça emergência.

Saídas conhecidas que NÃO se repetem: `0x94 00` (decolar) não fez o drone subir em 01/11, e `--pulso` sobe o
acelerador 1650 por 1 s. `0x94 01` (pousar) foi ignorado por ~5 s, e o script reduz o acelerador (1300) se
ele não descer. Travar (`0x79 01`) só é aceito parado perto do chão.

## Fase 5 — depois do voo

Ler `capturas/voo1m_*.csv` e relatar sem enfeite: altura máxima, `h_speed` máxima, roll/pitch máximos,
distância máxima, satélites, o que o drone fez ao pousar e se o usuário viu algo diferente da telemetria (a
altura da telemetria subestimou ~2 m em 01/11). Comparar com o voo anterior e dizer se a deriva melhorou.

## Não fazer

- Não enviar `0xB5` (manche), `0x79 00` (destravar), `0x94`, `0x95`, `0xB6` nem `0x7A` fora dos scripts acima.
- Não inventar comandos novos por tentativa; o que vier de análise estática (`0x2F`, luz, velocidade) é teste
  de leitura no chão, nunca voo. O `0x2F 01` não teve resposta em 20/11.
- Não voar sem GPS firme, dentro de casa ou perto de pessoas.
- Não mexer em `docs/` ou fazer commit sem o usuário pedir.

## Onde está o resto

- Protocolo: `docs/protocolo.md` (atenção: ele diz `0xB8/0xB9` para parâmetros; a biblioteca aponta `0x2F`).
- Diário de RE e voos de 01/11: `docs/diario-re.md`. Hardware e conectores: `hardware/README.md`.
