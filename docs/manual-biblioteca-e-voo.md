# Manual da biblioteca e de voo do Predator

Manual da biblioteca `predator-drone` 0.1.0, do aplicativo GNOME e dos procedimentos operacionais conhecidos para o hexacóptero Predator/Lewei.

> **Estado do projeto:** experimental. Telemetria, vídeo, destravar e travar foram confirmados no hardware. Os sentidos definitivos do manche, movimento horizontal automático, gestos e IA não estão aprovados para voo real.

## 1. Escopo e avisos

Este documento ensina a:

- instalar, testar e usar a biblioteca Python;
- abrir o aplicativo em modo seguro;
- interpretar telemetria e vídeo;
- configurar limites de força;
- operar o piloto manual com as barreiras existentes;
- encerrar, pousar e analisar uma sessão;
- distinguir recursos confirmados de hipóteses experimentais.

Este documento **não autoriza um voo**. Cada voo exige autorização explícita naquele momento, área externa livre, drone no chão, bateria conferida e uma pessoa com o controle físico na mão.

### Classificação usada

| Marca | Significado |
|---|---|
| Confirmado | Observado no drone real ou coberto diretamente pelo código e testes. |
| Experimental | Implementado, mas baseado em poucas medições. |
| Não validado | Não deve ser usado como se fosse confiável em voo. |

### Regras fundamentais

1. Comece sempre em **modo seco**.
2. Não trate o campo `battery` como porcentagem certificada; sua unidade não foi confirmada.
3. Não confie em GPS sem `gps_fix`, satélites suficientes e posição recente.
4. Não confie na altura como medida absoluta: ela já variou parada e subestimou voos reais.
5. Prefira pouso normal (`L`) a emergência (`X`). Emergência pode cortar motores no ar.
6. Como precaução conservadora, depois de emergência ou estado 5, desligue e ligue o drone antes de tentar destravar novamente. A necessidade após estado 5 ainda é hipótese.

## 2. Arquitetura do projeto

| Componente | Responsabilidade |
|---|---|
| `predator/link.py` | Socket UDP, envio periódico, telemetria e comandos. |
| `predator/bt.py` | Montagem e parsing do protocolo BTGPS. |
| `predator/video.py` | Protocolo TCP da câmera, H.264 e decodificação com FFmpeg. |
| `predator/movimento.py` | Limites compartilhados de força. |
| `predator/teclado.py` | Teclas para desvios do manche. |
| `predator/suave.py` | Perfis de velocidade, altura e `MoverPara`. |
| `predator/controle.py` | Controlador PD e `Vigia`. |
| `predator/armar.py` | Destravar/travar com confirmação de telemetria. |
| `predator/voz.py` | Reprodução offline da voz Thalita. |
| `scripts/piloto_predator.py` | Piloto integrado, gravação, painel e segurança operacional. |
| `app-rust/` | Janela GNOME em Rust que inicia o piloto Python. |
| `tests/` | Testes offline da biblioteca. |

O aplicativo em Rust cuida da janela, seleção do modo e confirmação. O processo Python continua responsável por protocolo, vídeo, telemetria, gravação e controle.

## 3. Instalação e testes

### Requisitos principais

- Linux com Python 3.10 ou superior;
- FFmpeg;
- OpenCV e NumPy para o piloto integrado;
- `paplay` para voz, opcional;
- GTK 4, libadwaita e WebKitGTK 6 para o aplicativo GNOME;
- Rust/Cargo apenas para recompilar o frontend;
- interface Wi-Fi `wlp2s0`, ou configuração explícita de outra interface na biblioteca.

O piloto atual espera o Python com OpenCV em:

```text
~/.local/share/aruco-venv/bin/python
```

O modo de gestos espera o projeto irmão em `../gestos/` e seu ambiente em `../gestos/.venv/`.

### Instalar a biblioteca

Na raiz do projeto:

```bash
python3 -m pip install .
```

### Executar os testes offline

```bash
python3 -m unittest discover -s tests -v
```

A suíte atual contém 31 testes e não acessa o drone. Ela cobre protocolo, checksum, direção, lifecycle, telemetria, vídeo, GPS, teclado, forças, armar/travar, movimento suave, PD e `Vigia`.

### Recompilar o aplicativo GNOME

```bash
cargo test --manifest-path app-rust/Cargo.toml
cargo build --release --manifest-path app-rust/Cargo.toml
```

O atalho local aponta para `app-rust/target/release/predator-gnome`.

## 4. Início rápido somente leitura

### Pela biblioteca

```python
import time
from predator import Drone

drone = Drone(read_only=True).start()
try:
    time.sleep(2)
    tel = drone.telemetry
    print("link:", drone.link_ok)
    print("estado:", tel.state)
    print("bateria:", tel.battery)
    print("GPS:", tel.gps_fix, tel.satellites)
    print("atitude:", tel.roll, tel.pitch, tel.yaw)
finally:
    drone.stop()
```

Em `read_only=True`, `Drone.command()` é bloqueado e o laço não transmite manche.

### Pelos scripts

```bash
python3 -P scripts/probe.py 8
python3 -P scripts/falar_status.py 4 --mudo
python3 -P scripts/gravar_voo.py 10 --fotos
```

“Somente leitura” ainda envia pedidos de telemetria e, no vídeo, START/heartbeat/STOP da câmera. Significa que não envia comandos de motor ou voo.

## 5. Referência da biblioteca

### 5.1 API pública

```python
from predator import Drone, Telemetry, VideoStream, MovimentoConfig
```

Versão:

```python
import predator
print(predator.__version__)  # 0.1.0
```

### 5.2 Conexão e telemetria

```python
Drone(
    read_only=False,
    iface=None,
    destination=None,
    period=None,
    telemetry_period=None,
    link_timeout=None,
)
```

Padrões:

- interface: `wlp2s0`;
- destino: `192.168.0.1:50000`;
- ciclo: 50 ms;
- pedido de telemetria: 0,5 s na biblioteca, 0,1 s no piloto;
- timeout do link: 1,5 s na biblioteca.

Métodos e propriedades:

| API | Resultado |
|---|---|
| `start()` | Inicia socket e threads; chamadas repetidas não duplicam threads. |
| `stop()` | Fecha socket, aguarda threads, limpa fila e repõe manche seguro. |
| `telemetry` | Snapshot consistente de `Telemetry`. |
| `telemetry_age` | Idade do último `0x88`. |
| `position_age` | Idade do último `0x89`. |
| `link_ok` | Verdadeiro apenas se atitude e posição estão recentes. |
| `gps_ok()` | Exige fix, satélites e posição recente. |
| `armed` | Estado diferente de 0/ausente. |
| `command(nome)` | Enfileira comando conhecido. |
| `set_sticks(...)` | Atualiza manche, limitado a `1000..2000`. |

Campos de `Telemetry`:

```text
roll pitch yaw state mode
height distance v_speed h_speed
satellites gps_fix lat lon battery
updated position_updated
```

### 5.3 Comandos

Nomes aceitos por `Drone.command()`:

```text
destravar  travar  decolar  pousar
emergencia  casa  pairar
```

Estrutura da chamada, não uma autorização para executar:

```python
drone = Drone().start()
drone.command("travar")
time.sleep(0.2)  # command() enfileira; em operação real, espere confirmação de telemetria
drone.stop()
```

Para travamento operacional, prefira `predator.armar.travar()`, que espera confirmação nova. `command()` recusa links somente leitura e instâncias não iniciadas. O comando `decolar` não fez este drone subir nos ensaios; ele não deve ser tratado como confirmado.

### 5.4 Protocolo BT

`predator.bt` oferece:

```python
frame(cmd, payload=b"", direction=APP_TO_DRONE)
request_telemetry()
unlock()
lock()
takeoff()
land()
return_home()
hover()
joystick(roll=1500, pitch=1500, yaw=1500, throttle=1500, ptz1=1500, ptz2=1500)
split(data, direction=None)
parse(frame)
```

Telemetria conhecida:

- `0x88`: roll, pitch, yaw, estado e modo;
- `0x89`: altura, distância, velocidades, satélites, fix, latitude, longitude e bateria.

`split()` valida checksum e pode exigir a direção `DRONE_TO_APP`.

### 5.5 Vídeo

```python
video = VideoStream().start()
try:
    quadro_rgb = video.latest
    print(video.fps, video.last_error)
finally:
    video.stop()
```

Características:

- câmera em `192.168.0.1:7060`;
- H.264 recebido por TCP;
- saída RGB `1280×720`;
- `latest_time` registra o último quadro;
- `toggle_recording(path)` grava H.264 cru;
- falha do decoder recria FFmpeg e reconecta;
- corpos maiores que 4 MiB ou truncados são rejeitados.

### 5.6 Configuração de força

```python
from predator import MovimentoConfig

config = MovimentoConfig(
    forca_horizontal=60,
    forca_vertical_sobe=100,
    forca_vertical_desce=150,
    forca_giro=40,
)
```

Cada valor representa o desvio máximo ao redor de `1500` e deve estar entre `0` e `500`.

```python
config.limitar(roll=200, pitch=-90, yaw=80, acel=-300)
# (60, -60, 40, -150)
```

A mesma configuração pode limitar teclado, conversão do manche e `MoverPara`. Isso cria um envelope comum para uma futura política de IA.

### 5.7 Teclado e manche

```python
from predator import teclado

desvios = teclado.comando_teclas(
    {"w", "d", "e"},
    config=config,
)
manche = teclado.para_manche(desvios, config=config)
```

Mapa:

| Teclas | Canal |
|---|---|
| `W/S` | pitch, frente/trás pretendido |
| `D/A` | roll, direita/esquerda pretendido |
| `C/Z` | yaw, giro |
| `E/Q` | acelerador, subir/descer |

Os sentidos físicos definitivos ainda não estão confirmados. Houve movimento cruzado nos ensaios.

### 5.8 Movimento suave

Componentes:

- `Perfil`: acelera e freia uma referência;
- `Velocidade`: estima velocidade numa janela de amostras;
- `ControleAltura`: referência vertical para acelerador;
- `MoverPara`: combina posição, velocidade e limites;
- `gps_valido`: verifica fix, satélites e frescor;
- `metros_ne`, `para_corpo`, `para_mundo`: conversões geográficas.

Exemplo offline de construção:

```python
from predator import MovimentoConfig
from predator.suave import MoverPara

mover = MoverPara(
    tel,
    altura=2.0,
    frente=3.0,
    config=MovimentoConfig(forca_horizontal=30),
)

saida = mover.passo(tempo, tel_atual, dt)
roll = saida["roll"]
pitch = saida["pitch"]
acelerador = saida["acel"]
```

Alvos disponíveis:

- `altura`: altura da telemetria;
- `frente`/`direita`: deslocamento relativo ao nariz inicial;
- `norte`/`leste`: metros relativos à origem GPS.

Movimento horizontal exige:

- `gps_fix=True`;
- pelo menos oito satélites por padrão;
- posição com até 1,5 s;
- valores finitos e `dt > 0`.

**Status:** vertical baseado em poucas medições; horizontal apenas simulado e não aprovado para voo real.

### 5.9 Controle PD e Vigia

```python
from predator.controle import Ganhos, PD, Vigia

pd = PD(Ganhos(kp=30, kd=60, maximo=60))
roll, pitch = pd.comando(ex, ey, vx, vy)

vigia = Vigia()
motivo = vigia.verifica(t, roll, pitch, erro, roll_deg, pitch_deg)
```

O `Vigia` sinaliza:

- telemetria inválida;
- erro maior que o limite;
- inclinação alta;
- comando saturado sem melhora.

Ele apenas calcula e devolve um motivo. O chamador é responsável por iniciar um pouso.

### 5.10 Destravar e travar

```python
from predator.armar import destravar, travar

ok, segundos = destravar(link, manche_minimo, tentativas=2)
travou = travar(link, manche_minimo)
```

O argumento `manche_minimo` é o quadro/valor seguro esperado pelo tipo de link usado. As funções repetem comandos e só aceitam sucesso após telemetria nova e fresca. `destravar()` liga motores e exige autorização específica do teste ou voo.

### 5.11 Voz

```python
from predator.voz import falar
falar("sem_sinal")
```

A voz é `pt-BR-ThalitaNeural`. As frases foram geradas previamente com `edge-tts`, convertidas para WAV mono/24 kHz e são tocadas offline com `paplay`. Veja `scripts/voz/README.md`.

### 5.12 LWGPS

`predator.lwgps` implementa outra variante Lewei. Este Predator usa BTGPS; LWGPS permanece como resultado da engenharia reversa e não deve ser selecionado para este hardware.

## 6. Aplicativo GNOME

Abra **Predator** na lista de aplicativos do GNOME.

Modos:

| Modo | O que faz |
|---|---|
| Modo seco | Vídeo, telemetria, painel e gravação; não transmite controle. |
| Voar | Habilita o piloto real após confirmação. |
| Voar com gestos | Carrega MediaPipe e habilita gestos experimentais. |
| Manobra automática | Executa roteiro experimental e não é considerado validado. |

O aplicativo:

- verifica `192.168.0.x` em `wlp2s0`;
- usa a porta local 8777;
- grava log em `~/.cache/predator-piloto.log`;
- espera até 40 s pelo painel;
- pergunta antes de voo real;
- ao fechar durante voo, oferece “Pousar e encerrar”.

## 7. Controles de voo

| Tecla | Ação |
|---|---|
| `T` | Destravar motores; não decola. |
| `E/Q` | Subir/descer. |
| `W/S` | Frente/trás pretendido. |
| `D/A` | Direita/esquerda pretendido. |
| `C/Z` | Girar por yaw; indisponível em `--basico`. |
| `H` | Segurar posição/altura por GPS, experimental. |
| `G` | Manobra automática, experimental. |
| `L` | Pouso normal. |
| `X` | Emergência: corte/trava; pode derrubar o drone. |
| `Esc` | Pousar e sair. |
| `1–5` | Forças horizontais 15, 20, 30, 40 e 60. |
| `6–7` | 80 e 100, somente com `--forte`; modo app usa 250. |
| `F1–F4` | Inversão de pitch, roll, yaw e acelerador fora de `--basico`. |
| `F12` | Liga/desliga teclado global. |

O painel GNOME usa `--basico`: mantém WASD, E/Q, T, L, X, H, G e Esc, mas desabilita C/Z, presets e inversões.

## 8. Checklist antes do voo

### Ambiente

- [ ] Área externa, aberta e sem pessoas num raio mínimo de 5 m.
- [ ] Chão plano; evitar paredes, carros, árvores e metal próximo.
- [ ] Alguém observando o drone.
- [ ] Controle físico ligado e na mão, sem presumir prioridade sobre Wi-Fi.

### Hardware

- [ ] Braços e hélices sem folga, trincas ou deformação.
- [ ] Bateria fria, sem estufamento e firmemente conectada.
- [ ] Por precaução, drone recém-ligado após emergência ou estado 5; a relação com estado 5 ainda é hipótese.
- [ ] Lente limpa.

### Notebook e telemetria

- [ ] Wi-Fi `WiFi-1080P-GPS-…` conectado em `wlp2s0`.
- [ ] Estado `0`, travado.
- [ ] `link_ok=True`.
- [ ] GPS fix e pelo menos 8 satélites; preferir 10 ou mais.
- [ ] Roll/pitch próximos de zero; o piloto recusa acima de 10°.
- [ ] Vídeo presente.
- [ ] Bateria em repouso conferida. O app recomenda 75 ou mais; a unidade não é confirmada.
- [ ] Modo seco testado antes do modo de voo.

### Autorização

- [ ] O operador autorizou explicitamente **este** voo.
- [ ] A autorização não veio de uma sessão ou voo anterior.

## 9. Procedimento de voo manual

1. Abra o aplicativo em **modo seco**.
2. Confira vídeo, estado, GPS, bateria e atitude.
3. Feche o modo seco e selecione **Voar** apenas após o checklist.
4. Confirme o diálogo do voo.
5. Pressione `T` para destravar. Isso só deve colocar motores em marcha lenta.
6. Observe se o estado muda e se o drone permanece estável no chão.
7. Use `E` progressivamente para subir; o comando de decolagem do firmware não funcionou nos testes.
8. Use forças pequenas inicialmente. Não comece pelo modo app de ±250.
9. Mantenha o drone próximo e baixo; os sentidos dos canais ainda têm incerteza.
10. Pressione `L` para pousar antes de a bateria cair ou o comportamento ficar incerto.
11. Espere o estado voltar a `0` antes de encerrar.

### Barreiras automáticas do piloto

- ciclo de controle a 20 Hz;
- link perdido por aproximadamente 1,5 s inicia pouso;
- roll/pitch acima de 40° inicia pouso;
- distância GPS acima de 8 m inicia pouso;
- perda de GPS durante `MoverPara` inicia pouso;
- tecla humana cancela roteiro;
- inclinação acima de 60° por 0,3 s durante pouso aciona emergência;
- no chão, tenta travar a cada 0,1 s;
- se não travar em 3 s após detectar chão, aciona emergência.

## 10. Movimento automático e IA

### Estado atual

Não estão aprovados para hardware:

- `MoverPara` horizontal;
- segurar posição por GPS;
- ida e volta automática;
- manobra G;
- voo por gestos;
- PD no drone;
- checkpoints de IA por imitação.

As análises existentes mostram que a política treinada não superou o PD e pode perseguir deriva aparente do GPS por dezenas de segundos.

### Arquitetura recomendada para IA

A IA não deve escrever valores RC sem proteção. A ordem recomendada é:

```text
sensores/imagem
      ↓
política de IA
      ↓
alvo, velocidade ou correção limitada
      ↓
MovimentoConfig
      ↓
MoverPara / ControleAltura / PD
      ↓
Vigia
      ↓
manche
```

O código determinístico continua responsável por:

- limites de força;
- rampas e frenagem;
- validação de GPS e telemetria;
- neutralização;
- detecção de chegada;
- decisão de pousar em falha.

Treino recomendado:

1. coletar demonstrações em simulação;
2. separar treino, validação e prova por sementes;
3. testar perda de GPS, vídeo e telemetria;
4. comparar contra PD/controlador clássico;
5. reprovar a política se mantiver comando saturado ou não melhorar o erro;
6. só discutir hardware depois de superar os testes offline.

## 11. Pouso, emergência e encerramento

### Pouso normal

1. Pressione `L`.
2. O piloto entra em `pousando` e começa neutro.
3. Se necessário, reduz acelerador para 1300 após alguns segundos.
4. O detector procura atitude e altura compatíveis com chão.
5. No chão, manda acelerador 1000 e repete `travar`.
6. Aguarde telemetria fresca com estado `0`.

### Emergência

Use `X` somente quando continuar girando motores for mais perigoso que cortar. No ar, o drone pode cair.

Após `X`:

- o piloto envia emergência e trava repetidamente;
- o piloto bloqueia novo destravamento enquanto o modo não voltar a 1;
- desligue e ligue o drone antes de outro teste;
- inspecione braços e hélices.

### Fechar o aplicativo

- `Esc` solicita pouso e saída;
- fechar a janela durante voo abre confirmação;
- o processo espera chegar à fase `chao`;
- não mate o processo enquanto o drone puder estar no ar.

## 12. Pós-voo

1. Confirme estado `0`.
2. Desligue o drone.
3. Deixe a bateria descansar e confira aquecimento/estufamento.
4. Inspecione hélices, braços e motores.
5. Anote qualquer diferença entre observação visual e telemetria.
6. Preserve a pasta `capturas/piloto_<hora>/`.
7. Compare:
   - altura máxima;
   - velocidade horizontal e vertical;
   - roll/pitch máximos;
   - distância;
   - satélites;
   - bateria antes, durante e depois;
   - tempo e comportamento do pouso.

## 13. Diagnóstico de problemas

| Sintoma | Verificação |
|---|---|
| App diz Wi-Fi desconectado | Verifique `wlp2s0` e endereço `192.168.0.x`. |
| Sem telemetria | Confirme `192.168.0.1:50000`, interface e rede do drone. |
| `link_ok=False` com atitude visível | O pacote de posição `0x89` também precisa estar recente. |
| Sem vídeo | Confira FFmpeg, TCP 7060, lente e `VideoStream.last_error`. |
| Porta ocupada | Feche outro piloto na porta 8777. |
| Piloto terminou | Consulte `~/.cache/predator-piloto.log`. |
| Gestos não carregam | Confira `../gestos/.venv`, MediaPipe e joblib. |
| Teclado global não funciona | Permissão do grupo `input`, nova sessão e F12. |
| Não destrava | Estado 0, link, GPS, bateria, inclinação e religamento após emergência. |
| Movimento invertido | Os canais não estão confirmados; não improvise inversão em automático. |
| Bateria despenca | Campo não é porcentagem certificada; interrompa o voo e avalie a bateria. |
| Altura incoerente | O barômetro é relativo, ruidoso e já subestimou altura real. |
| Pouso demora | Firmware já ignorou pouso; mantenha área livre e deixe o piloto concluir. |
| Processo não fecha | Ele espera a fase `chao`; não force se houver possibilidade de voo. |

## 14. Limitações confirmadas

### Confirmado no hardware

- telemetria e vídeo funcionam;
- destravar e travar funcionam em condições adequadas;
- decolar por `0x94 00` não elevou este drone;
- pousar por firmware já demorou ou foi ignorado;
- altura pode ser incorreta;
- bateria cai fortemente sob carga;
- GPS parado deriva;
- canal pretendido como pitch apresentou resposta lateral;
- emergência pode exigir religamento;
- PTZ não moveu a câmera nos testes.

### Hipóteses

- manche pode comandar velocidade em vez de ângulo mantido;
- há resposta cruzada ou possível troca de canais;
- estado 5 parece intervenção do firmware por bateria baixa;
- controle físico pode ou não ter prioridade sobre Wi-Fi.

### Não validado

- sentidos finais de todos os eixos;
- giro automático até um rumo;
- retorno para casa e pairar do firmware;
- unidade da bateria;
- navegação autônoma;
- IA em voo real.

## 15. Desenvolvimento e testes

Antes de alterar controle:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q predator tests
```

Princípios:

- parsers e controladores devem permanecer testáveis sem hardware;
- scripts de leitura usam whitelist;
- comandos perigosos precisam de confirmação explícita;
- configuração deve entrar por construtor, não por alteração de globais;
- relógios de controle usam `time.monotonic()`;
- recursos devem ter `start()`/`stop()` idempotentes;
- telemetria deve ser publicada como snapshot;
- mudanças de segurança entram no `docs/diario-re.md`.

## 16. Referência rápida

### Biblioteca

```python
from predator import Drone, Telemetry, VideoStream, MovimentoConfig
from predator import bt, teclado, suave
from predator.controle import Ganhos, PD, Vigia
```

### Comandos seguros de diagnóstico

```bash
python3 -P scripts/probe.py 8
python3 -P scripts/falar_status.py 4 --mudo
python3 -m unittest discover -s tests -v
```

### Controles essenciais

```text
T destrava      E/Q sobe/desce      WASD movimento
L pousa         X emergência        Esc pousa e sai
```

### Documentos relacionados

- `README.md`: visão geral;
- `docs/protocolo.md`: protocolo de rede;
- `docs/diario-re.md`: evidências e histórico;
- `docs/resultado_opencode_1.md`: primeira análise de IA;
- `docs/resultado_opencode_2.md`: análise com telemetria real;
- `scripts/voz/README.md`: origem da voz.
