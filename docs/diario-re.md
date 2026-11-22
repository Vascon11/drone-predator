# Drone "Predator" Hexacopter — engenharia reversa

> Nota (reorganização): os arquivos citados abaixo agora estão em `predator/` (bt.py, video.py, mdata.py,
> lwgps.py = antigo lewei.py) e `scripts/` (probe.py, teste_motores.py, scan.py, dis.py). Referência limpa: [protocolo.md](protocolo.md).

App: LW-FPV (`com.klh.lwfpv`), módulo Wi-Fi da **Lewei** (libs `liblewei-3.2.2.so`, `liblewei_uartprotol.so`).
SSID: `WIFI-OOOP-GPS-XXXXXX`. Drone = access point.

## Rede (análise estática do arm64)
| Item | Valor | Origem |
|---|---|---|
| IP do drone | `192.168.0.1` (módulo LW63: `172.16.10.1`) | strings .rodata |
| Vídeo | `rtsp://192.168.0.1/live` | strings |
| TCP | 7060, 8060 | `LW93NativeInit` (0x1B94, 0x1F7C) |
| UDP controle (padrão) | **50000**, payload cru | `LW93NativeInit` (0xC350) → `openUdpSocket` |
| UDP controle (alt.) | **40000**, cabeçalho `63 63 0a 00 00 <len16 LE>` + payload | `LW93SendUdpData` |
| Taxa de envio | 1 pacote a cada 50 ms (20 Hz) | `FlyCtrl.startSendDataThread93` |

## Protocolo de controle
- Java preenche `LWUartProtolBean.mControlPara` → nativo `LWUartProtolGetControlData()` gera os bytes.
- Joystick: throttle, rudder (yaw), aileron (roll), elvator (pitch) + trims, ptz.
- Flags: unlock, autoTakeoff, autoLanding, homeward, hover, headless, altHold, photo, video, calibrações.
- Waypoints: `PointPara{coordinate, height*10, speed*10, time}`; Circle: center/height/radius/speed*10.
- Telemetria (`FlyInfo`): GPS (lat/lon, nº satélites), altura, distância, velocidade, atitude, bateria, estado/modo.
- Formato exato dos bytes ainda **não** extraído → capturar tráfego real (PCAPdroid) ou continuar RE de `liblewei_uartprotol.so`.

## Próximos passos
1. Conectar o notebook no Wi-Fi do drone (sem hélices) → nmap, ffplay RTSP, escutar UDP.
2. Capturar o app com PCAPdroid mexendo um comando por vez.
3. Lib Python de controle + telemetria + vídeo.

## Confirmado ao vivo (2026-10-29)
- SSID real: `WiFi-1080P-GPS-109F08`, MAC do drone `38:e2:6e:10:9f:08`, notebook recebe `192.168.0.20`.
- **Conflito**: rede de casa (cabo) também é 192.168.0.x com roteador em .1 → usar `SO_BINDTODEVICE` em `wlp2s0` (ver `tools/scan.py`).
- Portas TCP abertas no drone: 21, 23, 6288, **7060, 8060, 9060** (as três últimas batem com a análise estática). 9060 manda `connected` ao conectar.

## Ambiente de RE
- REA (MCP `rea-agents@6.8.0`) registrado no Claude Code; provider Ghidra.
- Ghidra 12.1.4: `~/tools/ghidra_12.1.4_PUBLIC`; JDK 21: `~/tools/jdk-21.0.13+9`; Node 22.23.4: `~/tools/node-v22.23.4-linux-x64` (Node do sistema é 22.22.2, abaixo do mínimo do REA).
- adb: `tools/platform-tools/adb`; `tools/PCAPdroid.apk` (v2.0.2) para instalar no celular.
- Próximo alvo no REA/Ghidra: `liblewei_uartprotol.so` (arm64) → `LWUartProtolGetControlData` / `LWUartProtolFlyInfoParseData`.

## Protocolo LWGPS (RE com REA/Ghidra em `liblewei_uartprotol.so`, sha256 4b37bb60…)
Fonte: `GetLWGPSTxData` 0x10d618, `GetLWVirtulRockerControlData` 0x10bfd8, `Get_LWChecksum` 0x11131c,
`ParseLWInfoData` 0x10dde4, `setFlyInfo` 0x11e7b4, `GetUartCTLData` 0x110ac0. **Tudo estático — nada validado no drone ainda.**

Quadro: `46 48 <dir> <cmd> <len u16 LE> <payload[len]> <ck>`; dir `3C`('<') app→drone, `3E`('>') drone→app.
`ck` = XOR dos bytes do índice 3 até 5+len (cmd, len, payload).

Detecção: o app não sabe o protocolo; com `uartProtol=None` ele alterna BT→**LWGPS**→GL→HYN→WS→HF→FS a cada envio
até um parser aceitar a resposta. LWGPS é o candidato principal (app/lib Lewei) — **confirmar ao vivo**.

### App → drone
| cmd | len | payload | significado |
|---|---|---|---|
| 0x65 | 1 | 01 | pede telemetria; enviado se passou >1000 ms do último |
| 0x67 | 1 | 00 / 01 | travar/destravar (app manda 00 se drone está travado, 01 se destravado — semântica inferida) |
| 0x68 | 1 | 01 decolar, 02 pousar, 04 stop/emergência, 08 voltar pra casa |
| 0x69 | 1 | 01 | pairar (hover) |
| 0x66 | 1 | 01 calib. acelerômetro, 02 calib. bússola |
| 0x6a | 4 | pitch, roll, throttle, yaw (u8) | manche virtual; centro 0x80, throttle 0..255 de (rc-1000)*0.255 |
| 0x6b | 4 | i16 LE, i16 LE | gimbal/PTZ |
| 0x6d | 8 | lat*1e7 i32, lon*1e7 i32 | posição do "alvo" no modo seguir (a cada 200 ms) |
| 0x6e | 11 | alt/10, ?, speed, lat i32, lon i32 | órbita |
| 0x70 | 1 | 01 | ler parâmetros |
| 0x71 | 4 | 01,a,b,c / 02,spd,0,0 | gravar parâmetros |
| 0x80 | 1 | bitmask | vídeos curtos automáticos |
| 0x92 | 1 | n | ? (campo +0x20) |
Gestos especiais no 0x6a: destravar (oito externo) = `ff 00 00 00`; travar (oito interno) = `00 00 00 ff`.
Ordem dos eixos inferida dos gestos (padrão RC modo 2), não observada.

### Drone → app (cmd 0x65 'e', len 24) — offsets no quadro
| off | tipo | campo |
|---|---|---|
| 6 | i16/10 | roll (°) |
| 8 | i16/10 | pitch |
| 10 | i16/10 | yaw |
| 12 | u8 | nibble alto: modo de voo (tabela), nibble baixo: estado (0 = travado) |
| 13 | u16/10 | distância da casa (m) |
| 15 | i8/10 | velocidade vertical |
| 16 | i16/10 | altura (m) |
| 18 | i8/10 | velocidade horizontal |
| 19 | u8 &0x1f | nº de satélites |
| 20 | u8 | bit0 GPS ok; bits1-6 sinal do rádio; bit7 retorno por bateria |
| 21 | i32/1e7 | latitude |
| 25 | i32/1e7 | longitude |
| 29 | u8 | bateria |
Outros: 'd' (nome/versão ASCII), 'f' (status de calibração), 'p' (parâmetros), 'q' (ack de parâmetros), 'l'/'n' (waypoints/órbita ok).

## ✅ CONFIRMADO AO VIVO (2026-10-29): o drone fala **BTGPS**, não LWGPS
- UDP `192.168.0.1:50000`, quadros crus (sem cabeçalho `cc`). O drone responde ao endereço/porta de origem.
- Quadro: `42 54 <3C|3E> <len u8> <cmd> <payload[len]> <xor(len..payload)>` — checksum conferido em pacotes reais.
- Pedido de telemetria (o que o app manda a cada 1 s): `42 54 3c 01 88 01 88 42 54 3c 01 89 01 89`.
  Resposta 1:1: `0x88` (atitude) e `0x89` (posição). Sem pedido o drone também manda `0x04` e `0x28` (ver abaixo).
- Leitura real (drone na mão, dentro de casa): roll -0.5°, pitch -0.2°, yaw 55.2°, state 0 (travado), mode 1,
  0 satélites, bateria 48 (unidade ainda não confirmada).
- Biblioteca: `bt.py`. Teste só-leitura com whitelist: `probe.py`. (`lewei.py` = LWGPS, não usado por este drone.)

### BT app → drone (estático, GetBTGPSTxData 0x107dfc) — NÃO testados
| cmd | payload | ação |
|---|---|---|
| 0x88 / 0x89 | 01 | pedir atitude / posição |
| 0x79 | 00 destravar (se travado), 01 travar | |
| 0x94 | 00 decolar, 01 pousar | |
| 0x95 | 01 | voltar pra casa |
| 0xB6 | 01 | pairar |
| 0x7A | F1 calib. acelerômetro, E1 calib. bússola | |
| 0x6F | 01/00 | modo headless |
| 0xB5 | 6×u16 LE: roll, pitch, yaw, throttle, ptz1, ptz2 (1000..2000) | manche; deflexão ×0.5 no modo lento |
| 0xB0 | 01 + lat i32 + lon i32 | seguir |
| 0x0D | lat i32 + lon i32 | posição do celular (100 ms) |
| 0xB8 / 0xB9 | ler / gravar parâmetros | |
| 0x2B/0x2C/0x2D | 01 | vídeos curtos |

### BT drone → app (ParseBTInfoData 0x108650)
- `0x88` len 7: roll i16/10, pitch i16/10, yaw i16/10, u8 (nibble baixo = estado, alto = modo).
- `0x89` len 19: dist i16/10, vz i16/10, altura i16/10, vh i16/10, sats u8&0x1f, flags u8 (bit0 GPS ok), lat i32/1e7, lon i32/1e7, bateria u8.
- `0x28` len 10: status (byte payload[2] = estado calibração; payload[7] = bits de sensores prontos; headless).
- `0x7A` calibração; `0xB4/0xB7/0xB8/0xB9` acks de órbita/waypoint/parâmetros.
- `0x04` len 15: **não tratado pela lib**; parece atitude (roll/pitch/yaw i16/10) + último byte ~0x4b. Hipótese.

### Teste controle remoto ligado/desligado (2026-10-29)
- `0x28` payload[7]: `01` no 1º teste (controle off) → `00` após ligar o controle → **continuou `00`** ao desligar.
  Logo **não** indica link do controle; provável mudança de inicialização (o Wi-Fi do drone reconectou ao ligar o controle).
- Nenhuma outra diferença na telemetria entre controle on/off. Bipes do drone ocorreram ao parear o controle; nenhum bipe durante o probe.
- `0x04` payload[7] alterna 00/01 entre amostras independentemente do controle (significado desconhecido).

## ✅ VÍDEO FUNCIONANDO (2026-10-29) — `video.py`
- **TCP 192.168.0.1:7060**, protocolo `lewei_cmd` (liblewei-3.2.2.so: avc_read_buffer_thread 0x11c370, send_stream_cmd 0x11c0fc).
- Comando (46 B): `"lewei_cmd\0"` + cmd u32 @10 (+ param u32 @14 no START). 1 = heartbeat (1/s), 2 = iniciar (param = HD_flag: 0/1 HD, 2/3 640×480), 3 = parar.
- Resposta: cabeçalho 46 B (cmd @10, tamanho u32 @22, flag u32 @26, a/b/c i16 @30/32/34) + corpo:
  32 B de sub-cabeçalho (n u32 @4, timestamp u64 @8, byte @16) + H.264 Annex B.
- Ofuscação: flag 0x81 → `LW_Decode_New` reescreve 3 bytes em data[n/2] via tabelas MData1/2/3 (`mdata.py`);
  senão, inverte 1 byte em `encode_index(ts, n)`. Validado: ffmpeg decodifica 76 quadros sem erro.
- Stream real: **H.264 Main 1280×720, ~12,5 fps** (ts sobe 80 ms/quadro), SPS em todo quadro inicial.
- **TCP 9060**: manda `connected` e depois a telemetria BT (ponte TCP do controlador de voo, alternativa ao UDP 50000).
- Porta 8060: aceita conexão mas não envia nada com este comando.

## ✅ PRIMEIRO COMANDO DE MOTOR (2026-10-29 23:28) — `teste_motores.py`
- Sequência: telemetria + manche (acelerador 1000) a 20 Hz; `42 54 3c 01 79 00 78` (destravar).
- Drone reportou estado 0 → **1 (destravado) em 0,55 s**; após 2 s `79 01` (travar) → estado 0. Depois travar + emergência (`94 02`).
- Funciona **sem GPS (0 satélites) e com o controle remoto desligado**. Decolar (`94 00`) ainda não testado.
- **Confirmado visualmente pelo usuário: as hélices giraram ~2 s e pararam.**

## GPS confirmado (2026-10-29 23:51) — `scripts/gps_log.py`
- Drone perto da janela: 0 satélites de 23:43 a 23:51; 23:50:31–23:51:32 lat/lon espúrios (~-41..-45, ~-29..-30) com 0 sats.
- 23:51:33: 4 satélites, lat/lon coerentes com a localização real; gps_ok (flags bit0) = 0 o tempo todo; deriva ~70 m em 2 min.
- Bateria oscila 33–38 nas leituras seguidas (provável % estimado pela tensão).
- Varanda (2026-10-29 23:58 → 00:02): 4 satélites desde o início (recuperou da janela), gps_ok = 0 em 240 leituras,
  posição espalhada ~170 × 190 m, bateria 33 → 29. Teste interrompido para economizar bateria.
  Hipóteses p/ ficar em 4 sats: céu parcialmente coberto pela varanda/prédio, antena do GPS dentro da carcaça,
  receptor simples (só GPS, sem GLONASS/Galileo). Repetir ao ar livre, céu aberto, bateria cheia.

## Gimbal/PTZ da câmera (2026-10-30) — `scripts/teste_camera.py`
- App: gimbal = "Yuntai" (云台). `LW93MainActivity.onYuntaiProgress`: barra > 50 → `JoystickPara.ptz_v = 1800`, < 50 → `1200`;
  `onYuntaiStop` → `1500` e recentraliza a barra. É comando de velocidade, não posição. Nada no app escreve `ptz_h` além da inicialização.
- `GetBTVirtulRockerControlData` 0x106e74 copia os campos +0xe/+0x10 sem transformar para os dois últimos u16 do `0xB5`.
  `GetLWPTZControlData` 0x10c21c (variante LW) usa os mesmos campos, o que os identifica como PTZ. Qual deles é `ptz_v` não foi conferido; os dois foram testados.
- A barra aparece/some num `onClick` (`LW93MainActivity$23`), sem checagem de modelo no trecho lido: a barra existir no app não prova que há motor.
- Ao vivo, drone travado (estado 0), controle desligado não verificado, sem destravar: ptz1 e ptz2 em 2000/1000 por 3 s e em 1800/1200 por 6 s.
  Correlação de fase contra a referência: **0 px em todas as fases**, cena com bastante detalhe. Braço do drone sempre no mesmo lugar da imagem.
- Mancha verde na imagem = LED do drone piscando: aparece também com os canais em 1500, inclusive na referência.
- Hipóteses restantes: câmera sem motor (inclinação fixa ou manual) ou firmware que só aciona PTZ em outro estado (ex.: destravado).
- Mapeamento confirmado em `LW_ControlPara_struct` 0x11af38: ptz_h = +0xe = `ptz1`, ptz_v = +0x10 = `ptz2`. O app só envia `0xB5` com `joystickOn` ligado.
- O app parado manda acelerador 1500 (`FlyCtrl.initSendData`), não 1000. Repetido com pacote igual ao do app (acel. 1500, ptz2 1800/1200, 8 s, drone travado): **0 px**.
- Destravado, sem hélices, app supostamente fechado (`scripts/teste_camera_destravado.py`, 17:08): estado 1, ptz2 1800/1200 por 5 s e ptz1 1800/1200 por 3 s: **0 px**. Travou ao final (estado 0).
- O usuário testou a barra no app com o drone travado: nada aconteceu, mas a telemetria do app estava zerada na foto, então o teste não é conclusivo.
- O usuário relata que já moveu a câmera antes, que ela está firme mas parece móvel, com engrenagem, e que vê um motorzinho na lateral: motor existe, provavelmente. Novas hipóteses: PTZ só destravado, só pelo controle físico, ou mecanismo/ligação com defeito.

## Bateria, motores e gravações (2026-10-30 e 31)
- 2026-10-30, sem hélices: `teste_motores.py` não destravou em 3 tentativas com bateria 2–3 (antes 62). Causa mais provável: pouca carga.
- 2026-10-31, sem hélices, bateria carregada: destravou em 0,60 s e travou sozinho. Bateria caiu de 100 para 69 em ~40 min ligado, sem voar.
- Gravados `capturas/normais_4m.h264` (3597 quadros) e `normais_6m.h264` (3600 quadros, distância real ~5,5 m), 180 s, ~20 fps, sem erro de
  decodificação. Copiados com hash conferido para o pendrive, com `sim_1793406047.json`. Análise de falsos disparos fica no outro computador.

## Seguir por visão no app (2026-10-31)
- `jadx` 1.5.2 leu o APK (2 erros em 2663 classes). Yuntai só altera `ptz_v`, sem condição no Java: suspeita de falha física ou de ligação na câmera.
- Modo `CTL_VisionFollow`: `VisionObjRectToJoystickValue` 0x111e78 (`liblewei_uartprotol.so`) converte o retângulo do alvo em manche.
- Caso padrão (`droneID` 0/0x18): resultado com mais de 200 ms centra yaw e pitch. Yaw = 1500 − erro·velocidade·500/(W·10), erro = W/2 − (x + w/2);
  zona morta W/20; teto ±200. Distância: afastar −124 se h > 0,8W, h > 0,9H, y < 0,1H ou y + h > 0,9H; aproximar +124 se h < 0,5H e w < 0,3W;
  histerese de 5 s ao inverter. Acelerador só em variantes (1350/1650). Sem pouso ao perder alvo. `droneID` deste drone não confirmado.
- Status: só análise estática; sentido real de yaw e pitch segue sem teste em voo.

## Primeiros voos (2026-11-01, casa da avó) — `scripts/voo_1m.py`
- Comando de decolar `0x94 00` não fez o drone subir (3 tentativas, até com dois envios e pausa). Subir o acelerador do manche (1650 por 1 s) funciona. Pousar `0x94 01` foi ignorado por ~5 s; descer reduzindo o acelerador (1300) funcionou. Travar (`0x79 01`) só aceito com o drone parado perto do chão (~1–11 s).
- Ao destravar, a altura da telemetria zera (ex.: 3,3 → 0,0); o script mede o chão de novo depois de destravar.
- Altura da telemetria subestima: 0,7–1,0 m contra ~2 m vistos por testemunha. GPS acompanhou o deslocamento (1,4 m) e bate com a "distância" do drone (1,8 m).
- Deriva de 1–2 m com inclinação de até ~20° sem comando; calibração de acelerômetro (`0x7A F1`, resposta `7a f3`) não resolveu. Um voo terminou batendo na parede; último voo tombou ao pousar (roll 63°, pitch 55° no registro).
- Bateria afunda sob carga (~68 → ~25) e oscila; leitura em repouso volta a ~60.

## Voos de 20/11 e voz do Predator (2026-11-20) — `scripts/voo_1m.py --pulso`
- Antes: drone travado, 10–18 satélites, bateria em repouso 72–80 depois de carregar (placa carregadora externa, sem leitura de % pela USB). Pitch parado em −3,0° sem calibrar.
- Voo 1 (14:58, `capturas/voo1m_20261120_145855.csv`): destravou em 0,2 s, pulso de acelerador 1650 por 1 s, subiu rápido (v_speed até 3,2 m/s) e **deitou de lado**: roll até −148,6°, pitch −22,5° a +51,2°. Script mandou pousar com 0,2 m e travou em 4 s. Bateria 69 → leitura 5 sob carga → 61.
- Voo 2 (15:01, `capturas/voo1m_20261120_150130.csv`): igual, v_speed até 3,7 m/s, roll até −93,5°, pitch −35,1° a +15,5°, bateria 76 → 0 → 14. Distância máxima 5,1 m com h_speed só 0,4 m/s (provável ruído de GPS).
- O usuário viu o drone subir **em espiral, sem ficar no mesmo lugar**, e virar de lado. Padrão repetido nos dois voos.
- Um voo antes (decolar com `0x94 00`, 20/11 de manhã): 10 s sem sair do chão, travou sozinho; confirma o diário de 01/11.
- Hipóteses: acelerômetro sem calibrar (pitch −3,0° parado), pulso 1650 forte demais sem estabilização, hélice/motor com problema, bateria afundando. Reduzir o pulso para ~1550 sugerido, ainda não testado.
- Calibração do acelerômetro às 15:03 (`scripts/calibrar_completo.py --so-acel --passadas 2`, drone no piso plano): roll/pitch de −1,0°/−3,0° para 0,0°/0,0°, `0x28` byte 4 foi de 00 para 02. Voo depois da calibração: ainda não feito.
- Voz: `predator/voz.py` e `scripts/falar_status.py` falam o estado com frases da Thalita (edge-tts) em `scripts/voz/p_*.wav`; `voo_1m.py` narra as fases. Só tocam áudio, nada é enviado ao drone.

### Voos de 20/11 à tarde: pulso de acelerador e voo para a frente (`voo_1m.py --pulso`, `voo_frente.py`)
- Pulso de 1 s sem vento: **1550** não sai do chão; **1600** andou ~20 cm; **1625** subiu um pouco e pousou a ~10 cm; **1650** sobe a ~3 m/s e capota (voos 1 e 2, com vento e na madeira). Faixa de decolagem estreita entre 1625 e 1650.
- A altura da telemetria não serve: marcou 0,0–0,1 m com o drone subindo e andando (confirmado a olho três vezes). O script decidia "saiu do chão" pela altura e travava em vez de pousar; agora também conta v_speed > 0,5 m/s (voo_1m) ou > 0,3 m/s (voo_frente) e inclinação > 15°.
- Local com vento e sobre a madeira inclinada (pitch parado −2,5°) piorou a deriva; sem vento e nivelado (roll/pitch ~0°) os voos ficaram estáveis.
- `voo_frente.py` (pitch 1560 por 1,5 s depois do pulso 1625, acelerador 1600): o drone foi para a **direita do drone**, não para a frente, e **subiu bastante** (acelerador 1600 por 1,5 s a mais). Telemetria: pitch −2,4° a +0,7°, roll até +3,0°, distância só 0,8 m; o pouso demorou ~23 s (pouso `0x94 01` ignorado por 5 s). Hipótese: roll e pitch estão **trocados no pacote do manche `0xB5`** (a ordem foi inferida, não observada). Teste: desvio no canal de roll.
- Tentativa do teste com roll (`--eixo roll --pitch 1560 --acel-frente 1550`): o drone **não destravou em 3 s** (bateria 46–50 em repouso; em 30/10 aconteceu o mesmo com bateria baixa). Nenhum acelerador enviado.
- Bateria em repouso ao longo do dia: 72–80 depois da carga, 69 → 61 → 53 → 49 depois dos voos; a leitura chegou a 0–14 durante os pulsos.
- Novo: `predator/armar.py` (destravar com tentativas e pausa, travar com confirmação) e `scripts/destravar.py` (destrava, fica armado, trava; não decola).

### Ensaios sem voar: inclinação à mão e caminhada guiada por voz (2026-11-20, drone travado)
- Ensaio à mão (`scripts/ensaio_eixos_mao.py`, voz Thalita manda inclinar): **pitch negativo = nariz para baixo (frente)** (−10,4°; trás +8,2°) e **roll positivo = asa direita para baixo** (direita +11,7°; esquerda −12,0°). Cada movimento mexeu só no seu eixo; roll e pitch da telemetria não estão trocados. Isso vale para a telemetria, não prova a ordem dos canais do manche `0xB5`.
- Caminhada guiada (`scripts/ensaio_caminhada.py`): carregando o drone ~3 m em cada direção, o GPS decomposto pelo yaw deu frente +3,4 m, trás −3,4 m, direita +3,1 m (na direita do nariz), esquerda −3,5 m; deslocamento cruzado de 0,9–1,4 m (erro do GPS/passo torto). **O yaw é o rumo do nariz** (83–85°, estável). A velocidade horizontal (`h_speed`) máxima foi 0,2–0,3 m/s, então a velocidade lida é baixa para andar a pé.
- Consequência: o resumo de `scripts/teste_eixos.py` (deslocamento na frente/direita do nariz) é confiável quando o drone anda mais de ~1,5 m. No voo para a frente de 20/11 o GPS mostrou só ~0,3 m na direção do nariz, pequeno demais para contradizer o que o usuário viu a olho (foi para a direita e subiu).
- Pendente: com a bateria carregada, rodar `teste_eixos.py` por direção (frente, tras, direita, esquerda) e comparar o canal do manche com a direção observada; a bateria não carregou de verdade com o drone ligado (leitura 32–44 por 10 min).
- Monitor da carga: `scripts/monitor_bateria.py` (só leitura, CSV em `capturas/bateria_*.csv`).

### Câmera, ArUco, fluxo óptico do XS9 e controlador em simulação (2026-11-20, à tarde)
- Câmera do Predator (H.264 1280×720): com a lente suja/encostada a imagem era um borrão cinza (vídeo ~0,0 MB em 3 s); depois de limpar, nítida (0,7 MB em 3 s). A folha ArUco do XS9 (`DICT_4X4_100`, marcadores de 4 cm) aparece inteira a 30–50 cm do chão; o detector (`scripts/ver_aruco.py`, venv `~/.local/share/aruco-venv`, rodar com `-P` por causa de `scripts/dis.py`) leu até 50 marcadores num quadro. Borrão de movimento (câmera balançando) impede a leitura.
- Fluxo óptico do XS9 (`xs9/fluxo.py`, OpenCV clássico, não é rede) no vídeo do Predator reduzido a 640 px (`scripts/ensaio_fluxo_mao.py` + `scripts/analisa_fluxo.py`, drone travado na mão, voz Thalita): válido em 100% dos 1499 pares. Direita dx −207, esquerda +81 (sinais opostos, eixo x da imagem); subir escala 0,86. Frente e trás ficaram pequenos (dy −13 e −43) e inconclusivos: repetir com mais amplitude.
- Teste de eixo com voo (`scripts/teste_eixos.py --direcao frente`, pulso 1625, desvio 60, acelerador 1550, bateria 27 ao destravar): pitch −6,1° a +2,3°, roll +0,4° a +5,0°; o usuário viu o drone ir **para a direita** e capotar no final (pousado de cabeça para baixo, sem dano). GPS +0,50 m na frente e −0,61 m na direita do nariz (erro ~1 m). Conclusão: o canal de pitch parece vir acompanhado de roll à direita; ordem dos canais do manche `0xB5` segue não confirmada.
- Dados dos voos de 20/11 (`eixos_frente_*.csv`, `voofrente_*.csv`): telemetria a 10 Hz; parado, roll/pitch variam ±0,05°; offset de nivelamento muda por voo (−3,1° a +0,3°). Com o desvio de 60 mantido por 1,5 s, a inclinação sobe a ~4,3° em ~0,2 s e **volta a ~0 em ~0,5 s com o comando ainda aplicado**; velocidade horizontal ~0,4 m/s constante. Atraso comando → inclinação ≤ 0,1–0,2 s.
- Controlador (`predator/controle.py`: PD de posição/velocidade + `Vigia`) e simulação (`scripts/simula_controle.py --modelo antigo|medido|velocidade`, sem drone): modelo "ângulo mantido" funciona (erro máx 0,63 m, kp 60 kd 15); modelo "medido" (inclinação com lavagem) **não funciona**, o Vigia pousa em 28–30 de 30; hipótese B, o manche comandando **velocidade** (60 unidades ≈ 0,4 m/s, `modo` 1 → 2 após destravar), funciona com kp 60, kd 15 (erro máx 0,17 m, 0 pousos do Vigia). Com roll/pitch trocados ou sinal invertido o Vigia pousa em 30 de 30. Hipótese B não provada: a base são 2 voos de ~1,5 s.
- Próximo teste: voo de degrau (desvio de 60 por ~3 s, ver se `h_speed` se mantém ou cresce), com bateria carregada, barbante e protetores, só com autorização.
- Bateria: 35–43 em repouso à tarde, leitura de 0–14 sob carga; com 27 ao destravar ainda destravou e voou ~9 s. Carregar antes do próximo voo.
- Scripts novos: `scripts/ver_aruco.py`, `ensaio_fluxo_mao.py`, `analisa_fluxo.py`, `teste_eixos.py`, `destravar.py`, `simula_controle.py`, `predator/controle.py`.

### Piloto pelo teclado e o travamento depois da emergência (2026-11-20, noite)
- Voo de bateria carregada (84–88 em repouso): `teste_eixos.py --direcao direita` (pulso 1625, desvio de roll +60): o drone perdeu o controle e o usuário o pegou; roll só +1°, pouso levou 12 s.
- `scripts/piloto_predator.py` (janela tkinter, teclado WASD, T destrava, E/Q acelerador em rampa de 50 µs/s, L pousa, X emergência; grava `capturas/piloto_*/`, thread de controle a 20 Hz; `--teclado-global` lê /dev/input e começa desligado, F12 liga) e `predator/teclado.py` (mapa de teclas, 6 testes). Voo 1 do piloto: pulso de 1625 e depois neutro, o drone capotou em ~1,5 s (roll −146°/+179°), o script pousou por inclinação > 40°.
- Teste de bancada sem hélices: o piloto destravou duas vezes e depois **recusou destravar** em 6 tentativas (T) e em 3 tentativas do `destravar.py`, sempre depois de uma rodada que terminou com X (fase direto para `chao`, estado 2). O `destravar.py` só destravou (0,2 s) **depois de desligar e ligar o drone**, quando a telemetria mostrava `modo` 1; nos testes que falharam o `modo` era 2. À tarde ele destravou várias vezes com modo 2, então a relação não é perfeita. Hipótese de trabalho: depois da emergência (`0x94 02`) o drone só destrava de novo depois de desligar e ligar. O piloto agora avisa e bloqueia o T depois do X até o `modo` voltar a 1.
- Detalhes do piloto: o acelerador com E segurada chegou a 1625 em 1,25 s (rampa de 100 µs/s, depois baixada para 50); A (roll 1460 por 0,55 s) era pequeno demais para notar sem hélice; a leitura da bateria cai a ~2 com o acelerador em 1580–1625 (queda de tensão). A voz dizia "pousou" quando o T falhava em destravar; é a fase `chao`, não um pouso.
- O sistema de permissões do Claude Code negou rodar `destravar.py` pelo agente (liga motores); o usuário rodou com `!`.
- Pendente: teste de bancada sem hélices do WASD/EQ (qual motor muda com cada tecla), com o drone desligado e ligado antes; depois decidir o voo de linha de base com o controle de rádio.

### Jogo de correção, IA por imitação (modelo sol) e telemetria real (2026-11-20, noite)
- `scripts/jogo_correcao.py`: jogo de manter o drone parado (vista de cima, WASD como manche analógico, força 0–100%, vento que gira devagar, ruído correlacionado); grava observação → ação em `capturas/jogo_*.csv`. `--auto N` joga com o PD (professor), `--sintonia N` varre ganhos. PD kp 60, kd 15: 0,22 m no modelo `velocidade`, 0,70 m no `antigo`, perde 15/15 no `medido`. Ganhos menores pioram (kp 10: 0,73 m); a regressão que deu "−19 por metro" era enviesada pelo ruído da medida (eu tinha concluído errado que o PD era agressivo demais).
- Humano: nas melhores rodadas do modelo velocidade, 0,19–0,24 m (empate ou melhor que o PD); no `antigo` perdeu em 6 s; o `medido` ainda não foi jogado. Só 2 rodadas completas por modelo: pouco para imitar.
- Tarefa 1 (OpenCode, `openai/gpt-6.1-sol`, `docs/tarefa_opencode_1.md`, resultado em `docs/resultado_opencode_1.md`, código em `ia/`): MLP numpy 22→32→32→2 (saída contínua ±100%), clonagem do PD + 3 iterações de DAgger, 160 mil exemplos. Prova de 100 sementes por modelo: **igual ao PD** (0,207 m velocidade, 0,707 m antigo) e **100/100 perdidas no `medido`**. Recomendação: não levar ao drone.
- Tarefa 2 (`docs/tarefa_opencode_2.md`, `docs/resultado_opencode_2.md`, `ia/real/`; dados limpos sem lat/lon em `ia/reais/`, gerados por `scripts/prepara_dados_reais.py`): dos 734 s de telemetria real só **24,6 s** têm comando conhecido com o drone no ar. Ruído da posição medido: 0,175 m (leste) e 0,259 m (norte), **muito mais persistente no tempo** que o simulador. Política retreinada em ambiente calibrado: ainda sem vantagem sobre o PD, 100/100 perdidas no `medido`. Replay aberto em 79 trechos reais: com o drone **parado**, a política segurou um eixo acima de 57% por até 29,9 s, **perseguindo a deriva aparente do GPS**. Recomendação: não levar ao drone.
- Bateria: a leitura cai a 0–20 com o acelerador mesmo **sem hélices**; destravar falhou em sequência depois de rodadas com a leitura em ~0 e voltou depois de desligar e ligar (hipótese: proteção de bateria baixa, ou emergência `0x94 02`).
- Plano: voo de linha de base com o **controle de rádio**, gravado só por leitura (`gravar_voo.py`), com bateria carregada e hélices no lugar; depois treinar a IA olhando a imagem (fluxo óptico e ArUco) em vez do GPS parado, e jogar mais rodadas completas (principalmente `medido`).

### Endurecimento da biblioteca Python (2026-11-22, sem voo)
- Revisão do pacote `predator/`: a separação entre protocolo (`bt.py`), rede (`link.py`), vídeo (`video.py`) e cálculos puros (`teclado.py`, `controle.py`, `suave.py`) estava boa, mas lifecycle, concorrência e validação de dados ainda eram frágeis para uso como biblioteca de voo.
- `predator/link.py`: `Drone.start()` e `stop()` agora são idempotentes; cada execução usa evento e threads próprios, fecha o socket e aguarda as threads. A telemetria passou a ser publicada como snapshot atômico, com idades separadas para atitude (`0x88`) e posição (`0x89`), e `link_ok` exige ambas frescas. Respostas UDP exigem origem `192.168.0.1:50000` e direção `DRONE_TO_APP`; interface, destino e períodos podem ser configurados no construtor. Parar limpa fila e manche, e comandos são recusados com o link parado para não reaparecerem num reinício.
- `predator/video.py`: limite de 4 MiB por corpo, validação de corpo mínimo e tamanho H.264 antes dos offsets/desofuscação; gravação protegida por lock; `start()`/`stop()` idempotentes; threads e `ffmpeg` são encerrados e aguardados. Se o decoder morrer, o worker o recria e reconecta à câmera.
- `predator/suave.py` e `controle.py`: rejeitam `NaN`, infinito, `dt <= 0` e parâmetros temporais inválidos. Relógio regressivo limpa a janela de velocidade. Movimento horizontal só começa e continua com GPS fix, pelo menos 8 satélites e posição com no máximo 1,5 s; perda do GPS zera roll/pitch automático e impede declarar chegada. A chegada também exige velocidade/referência baixas. O `Vigia` manda pousar com telemetria não finita.
- `predator/armar.py`: exige confirmação de telemetria nova e fresca depois dos comandos de destravar e travar, evitando aceitar estado antigo; agora aceita tanto o `Link` síncrono dos scripts quanto `predator.link.Drone`.
- `scripts/piloto_predator.py`: perda de GPS durante `MoverPara`/segurar posição neutraliza o automático e inicia pouso; o conjunto de teclas recebeu lock para não manter manche anterior por corrida entre HTTP, teclado e controle. POSTs do painel recusam origem externa, tipo diferente de JSON e corpos grandes, reduzindo CSRF vindo de páginas web.
- Empacotamento e testes: criado `pyproject.toml`, API pública em `predator/__init__.py` e suíte só com biblioteca padrão. Resultado offline: **31 testes passaram** (protocolo/direção/checksum, snapshots, start-stop-start, limpeza de comandos, parser de vídeo, GPS, tempos, configuração de forças, teclado, armar/travar e Vigia). Wheel `predator_drone-0.1.0` gerado com sucesso.
- Validação real somente de leitura, drone travado: a classe nova recebeu telemetria com `link=True`, estado 0, modo 1, bateria 86 (unidade ainda não confirmada), GPS fix/12 satélites, roll −0,4°, pitch +1,4° e idade de posição 0,09 s. Vídeo novo recebeu quadro, marcou 20 fps, sem erro, e encerrou limpo. Foram enviados apenas pedidos de telemetria e comandos de iniciar/heartbeat/parar câmera; nenhum comando de motor, manche, voo ou calibração.
- Riscos residuais: manche/eixos e controle horizontal continuam sem validação segura em voo; GPS parado já mostrou deriva de metros; altura e bateria têm leituras não confiáveis sob carga. Estas mudanças reduzem falhas de software, mas **não tornam a IA nem `MoverPara` aprovados para voo real**.
- Pendência: verificar, somente com o drone travado e em modo de leitura, se ele responde corretamente aos pedidos `0x88` (atitude/estado/modo) e `0x89` (posição/GPS/bateria) enviados separadamente. Se confirmado, avaliar `0x88` a 10 Hz e `0x89` a 2–5 Hz para reduzir tráfego; a economia de energia provavelmente será pequena diante de Wi-Fi, câmera, GPS e motores. Não aplicar antes de medir e manter `link_ok` exigindo os dois blocos recentes para qualquer automático.
- Voz confirmada pela memória do agente: `pt-BR-ThalitaNeural` (`edge-tts`), escolhida depois de comparar com Francisca. As frases são geradas com internet antes do uso, convertidas para WAV mono/24 kHz e tocadas offline com `paplay`; origem e comando de geração documentados em `scripts/voz/README.md`.
- Pendência de IA para movimento suave: manter `predator/suave.py` como planejador e envelope determinístico (rampas, limites, GPS fresco, chegada e neutralização), mesmo se uma política for treinada. A IA deve propor alvo, velocidade de referência ou correção limitada; a saída final continua passando por `MoverPara`, saturações e `Vigia`. Treinar primeiro só em simulação e demonstrações gravadas, provar em sementes separadas e não liberar para o drone enquanto não superar o controlador clássico e os testes de perda de GPS/telemetria. O horizontal permanece apenas simulado.
- Configuração unificada de força: `predator.movimento.MovimentoConfig` define limites independentes para horizontal, subida, descida e giro (desvios de 0 a 500 em torno de 1500). A mesma instância pode ser passada a `teclado.comando_teclas`, `teclado.para_manche` e `MoverPara`, preparando também o envelope de uma futura IA. Sem configuração explícita, as APIs antigas preservam seus limites anteriores.
- Manual consolidado criado em `docs/manual-biblioteca-e-voo.md`: instalação, API, telemetria, vídeo, forças, teclado, movimento suave, aplicativo GNOME, checklist, operação manual, pouso/emergência, pós-voo, IA e diagnóstico. Recursos são separados entre confirmados, experimentais e não validados; o `README.md` aponta para o manual.
