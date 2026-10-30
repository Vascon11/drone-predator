# ESP32 + drone — diagramas de ligação

Dois jeitos de colocar um ESP32 (sugestão: **ESP32-C3 Super Mini**) no drone. Os pinos são sugestões para o
C3 e podem mudar; tudo marcado 🔎 depende das medições pendentes em [`README.md`](README.md).

## Opção A — ESP32 por Wi-Fi (sem tocar nos fios do drone) — começar por aqui

O ESP32 entra na rede do drone como cliente e fala o mesmo protocolo que o notebook (UDP 50000).
Alimentação própria, fixado por fora com fita dupla face ou abraçadeira.

Versão em imagem: [`fotos/esp32-opcao-a-wifi.png`](fotos/esp32-opcao-a-wifi.png)

```mermaid
flowchart LR
    subgraph EXT["Por fora do drone (fita dupla face)"]
        BAT1["Bateria 1S 3,7 V<br/>pequena, ~150–300 mAh"]
        ESP["ESP32-C3 Super Mini"]
        TOF["VL53L0X (TOF200C)<br/>apontado para baixo"]
    end

    subgraph DRONE["Drone (sem modificação)"]
        CAM["Câmera / módulo Lewei<br/>AP Wi-Fi 192.168.0.1"]
        FC["Controlador de voo<br/>(corpo)"]
        SERVO["Servo de inclinação<br/>da câmera"]
    end

    PC["Notebook (opcional)<br/>vídeo + IA"]

    BAT1 -- "+ → 5V · − → GND" --> ESP
    TOF -- "I2C<br/>SDA → GPIO8 · SCL → GPIO9<br/>VCC → 3V3 · GND → GND" --> ESP
    ESP -. "Wi-Fi: UDP 50000<br/>comandos BT (0xB5, 0x94...)" .-> CAM
    PC -. "Wi-Fi: TCP 7060 (vídeo)<br/>UDP 50000" .-> CAM
    CAM -- "UART (fio de 4 pinos)" --> FC
    FC -- "PWM (fio de 3 pinos)" --> SERVO
```

Cuidado: o drone e o notebook mandando comandos ao mesmo tempo vão brigar. Defina quem manda (por exemplo,
o notebook só assiste o vídeo enquanto o ESP32 pilota, ou o ESP32 só lê o sensor e repassa ao notebook).

## Opção B — ESP32 na UART (depois de medir o conector de 4 pinos)

O ESP32 fica **no meio** do cabo de 4 pinos (cabo Y, sem cortar fios) e vira uma ponte entre a câmera e o
controlador de voo: repassa tudo o que a câmera manda e injeta os próprios comandos. Sem a latência do Wi-Fi.

Versão em imagem: [`fotos/esp32-opcao-b-uart.png`](fotos/esp32-opcao-b-uart.png)

```mermaid
flowchart LR
    CAM["Câmera / módulo Lewei<br/>(Wi-Fi + vídeo)"]
    ESP["ESP32-C3 Super Mini<br/>ponte UART + lógica<br/>repassa quadros BT<br/>e injeta comandos"]
    FC["Controlador de voo<br/>(corpo)"]
    TOF["VL53L0X<br/>apontado para baixo"]
    SERVO["Servo da câmera<br/>(fio amarelo)"]

    CAM -- "TX → GPIO3 (RX1)<br/>branco ou azul 🔎" --> ESP
    ESP -- "GPIO4 (TX1) → RX" --> CAM
    ESP -- "GPIO21 (TX0) → RX" --> FC
    FC -- "TX → GPIO20 (RX0)<br/>branco ou azul 🔎" --> ESP
    FC == "vermelho 5 V 🔎 → 5V<br/>preto → GND (comum)" ==> ESP
    TOF -- "I2C: SDA GPIO8 · SCL GPIO9<br/>3V3 · GND" --> ESP
    ESP -. "PWM GPIO5<br/>só se ptz1/ptz2 não funcionar" .-> SERVO
```

Checklist antes de ligar a opção B:

1. Medir tensões: vermelho ~5 V? branco/azul ~3,3 V? Se a linha for **5 V**, colocar conversor de nível
   (o ESP32 é 3,3 V).
2. Descobrir com o USB-TTL **qual fio sai da câmera e qual sai do controlador** e o baudrate.
3. Primeiro só **escutar** (TX do ESP32 desconectado). Só depois montar a ponte.
4. Nunca ligar um fio do drone direto em outro fio do drone.

## Peso e energia

| Item | Peso aprox. |
|---|---|
| ESP32-C3 Super Mini | ~2 g |
| VL53L0X (TOF200C) | ~2–3 g |
| Bateria 1S pequena (só na opção A) | ~5–10 g |
| Fios, fita | ~2–5 g |

Total na faixa de **10–20 g** — dentro do limite sugerido para motores escovados. Na opção B não há bateria
extra: o ESP32 consome pouco (~100 mA com Wi-Fi ligado, menos sem).
