# ESP32 disponível — a placa que temos

Ficha da placa ESP32 que já está em mãos, como gravar nela e o que dá para esperar dela no drone.
Os diagramas de ligação estão em [`esp32.md`](esp32.md) e [`ligacao-eletrica.md`](ligacao-eletrica.md).

Levantado em 2026-11-10, ligando a placa por USB no notebook Fedora. Legenda: ✅ confirmado · 🔎 a medir.

## Ficha

| Item | Valor |
|---|---|
| Chip | ESP32-D0WD-V3, revisão v3.1 (ESP32 **clássico**, não é C3/S3) ✅ |
| Núcleos / clock | 2 × Xtensa, 240 MHz ✅ |
| Rádio | Wi-Fi **só 2,4 GHz**, Bluetooth clássico + BLE ✅ |
| Flash | 4 MB (fabricante 0x68, dispositivo 0x4016), 3,3 V, modo DIO ✅ |
| Cristal | 40 MHz ✅ |
| MAC Wi-Fi | `f4:65:0b:55:8b:08` (o Bluetooth termina em `0a`) ✅ |
| USB-serial | QinHeng **CH343**, `1a86:55d4`, aparece como `/dev/ttyACM0` ✅ |
| Formato | placa de desenvolvimento com USB (tipo DevKit), bem maior e mais pesada que o C3 Super Mini do plano 🔎 |
| Firmware original | Bluepad32 v4.1.0 (controle de um robô que já foi desmontado) ✅ |

## O que ele tem de sensor

Quase nada útil para voo. O ESP32 entra no drone como **cérebro e ponte**, e os sensores vêm de fora.

| Tem | Observação |
|---|---|
| Sensor de temperatura do chip | mede o próprio chip, serve para ver superaquecimento |
| 10 pinos touch capacitivos | sem uso no drone |
| ADC 12 bits, 2 DAC | ADC não linear; o ADC2 não funciona com o Wi-Fi ligado |
| RSSI do Wi-Fi e do Bluetooth | proximidade bem grosseira |
| CSI do Wi-Fi | detecção de presença/movimento, experimental |
| Sensor Hall | removido nas versões novas do Arduino, ignorar |

**Não tem:** IMU, barômetro, bússola, GPS, câmera. No Predator isso já existe no controlador de voo; o que falta
(altura precisa perto do chão, obstáculos) é o ToF VL53L0X do plano, ligado por I2C.

## Gravar nela

### Modo download: só pelo cabo

O reset automático por DTR/RTS **não funciona** nesta placa: o pino EN responde, o GPIO0 não. O `esptool` comum falha
com `Wrong boot mode detected (0x13)`. O botão BOOT está ligado ao GPIO0 e funciona.

1. Desconecte o USB da placa.
2. Segure o botão **BOOT**.
3. Reconecte o USB com o BOOT apertado.
4. Segure uns 3 segundos e solte.

BOOT + EN com a placa ligada falhou nas três tentativas; use só o método acima.

### Armadilhas

- **A porta serial precisa ficar aberta entre os comandos.** Quando o último programa fecha a porta, o Linux mexe em
  DTR/RTS, o chip reinicia e sai do modo download. Em um script, abra o `/dev/ttyACM0` com `os.open` + `tty.setraw` e
  mantenha enquanto usa o `esptool`.
- **Não use `--baud` em comandos separados.** O stub fica na velocidade pedida (ex.: 460800) e a próxima chamada, que
  conecta a 115200, não recebe resposta. Ou use um comando só, ou deixe a velocidade padrão.
- **Reiniciar por software pode voltar em modo download** se o GPIO0 estiver baixo. Desconectar e reconectar o USB sem
  apertar nada resolve.
- Gravação testada em 2026-11-10: 4 MB regravados com o mesmo conteúdo, hash verificado, firmware subiu normalmente.

### Ferramentas usadas (fora deste repositório)

| O quê | Onde |
|---|---|
| Assistente falado (voz Francisca) que guia o modo download e testa a gravação | `~/Downloads/esp32-assistente/esp32_assistente.py` |
| Backup completo da flash original (4 MB) | `~/Downloads/esp32-assistente/backup_flash_20261110_150933.bin` |
| Firmware de teste "hello" (Wi-Fi + OTA), PlatformIO | `/mnt/dados/esp32-hello/` |

O backup não está no repositório (binário de 4 MB). Para restaurar o estado original:
`esptool write-flash 0x0 backup_flash_20261110_150933.bin`, com a placa em modo download.

## Firmware "hello"

Serve para provar Wi-Fi e atualização pela rede, e é a base para o protótipo do drone.

- **Primeira vez:** sem rede salva, a placa cria o Wi-Fi `ESP32-Hello-Setup`. Conecte nele e abra `http://192.168.4.1`
  para informar a rede (2,4 GHz) e a senha. As credenciais ficam na memória da placa, não no código.
- **Depois:** página em `http://esp32-hello.local` (IP, sinal, memória livre, uptime, botão para o LED).
- **OTA:** `pio run -e ota -t upload`, com senha própria definida em `include/config.h` do projeto.
- **Estado:** firmware gravado e rodando em modo de configuração. A rede Wi-Fi **ainda não foi configurada**.

## Pendências

- 🔎 **Medir a banda do Wi-Fi do drone** com ele ligado e o notebook em alcance (`nmcli dev wifi list`). O
  `docs/protocolo.md` cita 5 GHz; se for, o ESP32 clássico (e o C3) **não conecta**, e a Opção A de `esp32.md` não
  funciona. Sobram a Opção B (UART) ou um ESP32-C5, que tem 5 GHz.
- 🔎 Escolher a placa que realmente vai voar (o C3 Super Mini do plano); esta fica para bancada e protótipo.
- Comprar o VL53L0X e testar na mesa, alimentado só pelo USB.
- Configurar o Wi-Fi do firmware hello e validar o OTA pela rede.
