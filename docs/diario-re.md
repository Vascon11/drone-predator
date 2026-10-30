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
