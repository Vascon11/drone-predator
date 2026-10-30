# Como o drone funciona

Referência consolidada. Legenda: ✅ confirmado ao vivo · 📄 só análise estática do app.
Endereços de função referem-se às libs do APK `com.klh.lwfpv` 1.9.2 (arm64). Detalhes e histórico em
[`diario-re.md`](diario-re.md).

## Arquitetura

```
 notebook ──Wi-Fi 5 GHz──▶ módulo Lewei (câmera + AP Wi-Fi, 192.168.0.1)
                              │  TCP 7060  vídeo H.264 ("lewei_cmd")
                              │  UDP 50000 ponte ⇄ controlador de voo (protocolo BT)
                              │  TCP 9060  mesma ponte serial, via TCP
                              ▼
                        controlador de voo (GPS, barômetro, bússola, IMU, 6 motores)
```

O módulo Wi-Fi é só uma ponte: os pacotes BT passam direto para a serial do controlador de voo.
O controle remoto físico (2,4 GHz) é um caminho separado; o drone aceita comandos pelo Wi-Fi com o
controle desligado ✅.

## Rede ✅

| Item | Valor |
|---|---|
| SSID | `WiFi-1080P-GPS-<últimos 6 do MAC>` (aberto) |
| IP do drone | `192.168.0.1` (DHCP entrega `192.168.0.x` ao cliente) |
| Portas TCP abertas | 21, 23, 6288, 7060, 8060, 9060 |
| Vídeo | TCP 7060 |
| Controle/telemetria | UDP 50000 (o drone responde para a porta de origem) |
| Ponte serial TCP | 9060 — envia `connected` e depois os quadros BT |

## Protocolo de controle BT (UDP 50000)

```
42 54 <dir> <len> <cmd> <payload[len]> <ck>
"BT"   3C = app→drone, 3E = drone→app
ck = XOR de len, cmd e payload
```
Fonte: `GetBTGPSTxData` 0x107dfc, `ParseBTInfoData` 0x108650, `Get_BTChecksum` 0x110ff8
(`liblewei_uartprotol.so`). O app detecta a variante do protocolo pela resposta; este drone usa BT ✅.

### App → drone

| Comando | Bytes | Status |
|---|---|---|
| Pedir atitude + posição | `42 54 3c 01 88 01 88` + `42 54 3c 01 89 01 89` | ✅ |
| Destravar | `42 54 3c 01 79 00 78` | ✅ (hélices giram em marcha lenta) |
| Travar | `42 54 3c 01 79 01 79` | ✅ |
| Parada de emergência | `42 54 3c 01 94 02 97` | 📄 (enviado após os testes, sem efeito visível com motores já travados) |
| Decolar | `42 54 3c 01 94 00 95` | 📄 |
| Pousar | `42 54 3c 01 94 01 94` | 📄 |
| Voltar pra casa | `0x95 01` | 📄 |
| Pairar | `0xB6 01` | 📄 |
| Calibrar acelerômetro / bússola | `0x7A F1` / `0x7A E1` | 📄 |
| Headless liga/desliga | `0x6F 01` / `0x6F 00` | 📄 |
| Manche | `0xB5` + 6×u16 LE: roll, pitch, yaw, acelerador, ptz1, ptz2 (1000–2000, centro 1500) | ✅ enviado (acel. 1000) durante o teste de motores |
| Seguir | `0xB0` `01` + lat i32 + lon i32 (×1e7) | 📄 |
| Ler / gravar parâmetros | `0xB8` / `0xB9` | 📄 |

O app envia a cada 50 ms um comando pendente ou o manche, e a cada 1 s o pedido de telemetria.

### Drone → app

| cmd | Conteúdo | Status |
|---|---|---|
| `0x88` (len 7) | roll, pitch, yaw (i16 ÷10, graus); byte de estado: nibble baixo = estado (0 travado, 1 destravado), alto = modo | ✅ |
| `0x89` (len 19) | distância, vel. vertical, altura, vel. horizontal (i16 ÷10); satélites (u8 & 0x1F); flags (bit0 GPS ok); lat, lon (i32 ÷1e7); bateria (u8, parece %) | ✅ |
| `0x28` (len 10) | status de calibração e sensores (interpretação parcial) | ✅ recebido |
| `0x04` (len 15) | não tratado pelo app; parece atitude (roll/pitch/yaw i16 ÷10) + último byte ~0x4B | ✅ recebido, significado 📄 hipótese |

Observação: a altura vem do barômetro, relativa ao momento em que o drone ligou; varia ~1 m parado.

## Vídeo (TCP 7060) ✅

Fonte: `avc_read_buffer_thread` 0x11c370, `send_stream_cmd` 0x11c0fc (`liblewei-3.2.2.so`).

Comandos do cliente — 46 bytes:
```
"lewei_cmd\0" | cmd u32 LE @10 | param u32 @14 (só no START) | zeros
cmd 1 = heartbeat (1/s)   2 = iniciar vídeo (param = qualidade: 0/1 HD, 2/3 640×480)   3 = parar
```

Resposta — cabeçalho de 46 bytes + corpo:
```
cabeçalho: "lewei_cmd" | cmd u32 @10 (0x101/0x103 = vídeo) | tamanho u32 @22 | flag u32 @26 | a,b,c i16 @30/32/34
corpo:     32 B (tamanho n u32 @4, timestamp u64 @8, byte @16) + n bytes de H.264 Annex B
```

Ofuscação (desfeita em `predator/video.py`):
- flag `0x81`: `LW_Decode_New` reescreve 3 bytes em `data[n/2]` usando as tabelas MData1/2/3
  (permutações de 256 valores, extraídas para `predator/mdata.py`);
- caso contrário: inverte 1 byte na posição `encode_index(timestamp, n)`.

Resultado: H.264 Main, 1280×720, ~12,5 fps, lente grande-angular (olho de peixe).

## Perguntas em aberto

- Decolar/pousar/manche ainda não foram testados em voo; sentido dos eixos a confirmar.
- O drone recusa decolar sem GPS? (o app tem a opção "Take off only when GPS signal is well").
- Significado do pacote `0x04` e dos bits do `0x28`.
- Unidade exata da bateria.
- Para que servem as portas 21 (FTP), 23 (telnet), 6288 e 8060.
