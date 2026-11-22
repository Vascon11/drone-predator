#!/usr/bin/env python3
"""App do GNOME para o Predator: escolhe o modo, confirma o voo e mostra o painel (piloto_predator.py --web) numa janela própria.

Roda com o Python do sistema (GTK 4 + libadwaita + WebKit). O piloto roda num processo separado com o Python dele:
gestos/.venv (tem MediaPipe) quando os gestos estão ligados, senão o venv do OpenCV.
  python3 scripts/predator_gnome.py [--modo seco|voar|gestos]
Fechar a janela com o drone no ar manda pousar e espera o piloto terminar (ele só sai com o drone no chão).
"""
import os
import sys

# O GNOME pode manter o Exec antigo em cache. Encaminhe-o para o app Rust antes
# de importar GTK/Python, preservando inclusive as acoes --modo do atalho.
RUST_APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app-rust", "target", "release", "predator-gnome"))
if os.path.isfile(RUST_APP) and os.access(RUST_APP, os.X_OK):
    os.execv(RUST_APP, [RUST_APP, *sys.argv[1:]])

import json
import socket
import subprocess
import urllib.request

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("WebKit", "6.0")
from gi.repository import Adw, Gio, GLib, Gtk, WebKit  # noqa: E402

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PY_OPENCV = os.path.expanduser("~/.local/share/aruco-venv/bin/python")
PY_GESTOS = os.path.abspath(os.path.join(RAIZ, "..", "gestos", ".venv", "bin", "python"))
PORTA = 8777
URL = f"http://127.0.0.1:{PORTA}/"
APP_ID = "local.predator.Painel"


def wifi_do_drone():
    """IP do notebook na interface do drone, ou None se não estiver na rede 192.168.0.x."""
    try:
        saida = subprocess.run(["ip", "-br", "addr", "show", "wlp2s0"], capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return None
    for parte in saida.split():
        if parte.startswith("192.168.0."):
            return parte.split("/")[0]
    return None


def porta_aberta():
    with socket.socket() as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", PORTA)) == 0


def acao(k):
    """Manda uma ação ao painel (como o botão da página). Falha em silêncio se o piloto já saiu."""
    try:
        req = urllib.request.Request(URL + "acao", data=json.dumps({"k": k}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=1).read()
    except Exception:
        pass


def fase_atual():
    try:
        return json.loads(urllib.request.urlopen(URL + "estado", timeout=1).read()).get("fase")
    except Exception:
        return None


class Janela(Adw.ApplicationWindow):
    def __init__(self, app, modo_inicial=None):
        super().__init__(application=app, title="Predator")
        self.set_default_size(1400, 860)
        self.proc = None
        self.voando = False
        self.fechando = False

        self.titulo = Adw.WindowTitle(title="Predator", subtitle="escolha o modo")
        cab = Adw.HeaderBar(title_widget=self.titulo)
        self.bt_parar = Gtk.Button(label="Encerrar")
        self.bt_parar.add_css_class("destructive-action")
        self.bt_parar.set_visible(False)
        self.bt_parar.connect("clicked", lambda *_: self.close())
        cab.pack_end(self.bt_parar)

        self.pilha = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.pilha.add_named(self._tela_inicio(), "inicio")
        self.pilha.add_named(self._tela_espera(), "espera")
        self.web = WebKit.WebView(vexpand=True, hexpand=True)
        self.pilha.add_named(self.web, "painel")

        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        caixa.append(cab)
        caixa.append(self.pilha)
        self.set_content(caixa)
        self.connect("close-request", self._ao_fechar)
        GLib.timeout_add_seconds(2, self._atualiza_wifi)
        if modo_inicial:
            GLib.idle_add(self._pedir, modo_inicial)

    # ---------- telas ----------
    def _tela_inicio(self):
        pagina = Adw.StatusPage(icon_name="predator-drone", title="Predator",
                                description="Hexacóptero pelo notebook: vídeo, telemetria, teclado, roteiros e gestos.")
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, halign=Gtk.Align.CENTER)
        self.lb_wifi = Gtk.Label()
        self.lb_wifi.add_css_class("dim-label")
        caixa.append(self.lb_wifi)
        for modo, rotulo, estilo in (("seco", "Abrir em modo seco (não envia nada)", "suggested-action"),
                                     ("voar", "Voar", "destructive-action"),
                                     ("gestos", "Voar com gestos", "destructive-action"),
                                     ("manobra", "Teste automático: frente, trás, direita, esquerda", "destructive-action")):
            b = Gtk.Button(label=rotulo)
            b.add_css_class("pill")
            b.add_css_class(estilo)
            b.set_size_request(340, -1)
            b.connect("clicked", lambda _b, m=modo: self._pedir(m))
            caixa.append(b)
        dica = Gtk.Label(label="Teclado no painel: T destrava · E/Q sobe/desce · WASD move · H segura · L pousa · X emergência")
        dica.add_css_class("caption")
        dica.add_css_class("dim-label")
        caixa.append(dica)
        pagina.set_child(caixa)
        self._atualiza_wifi()
        return pagina

    def _tela_espera(self):
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
        sp = Adw.Spinner()
        sp.set_size_request(48, 48)
        self.lb_espera = Gtk.Label(label="ligando o piloto…")
        caixa.append(sp)
        caixa.append(self.lb_espera)
        return caixa

    def _atualiza_wifi(self):
        ip = wifi_do_drone()
        self.wifi_ok = ip is not None
        self.lb_wifi.set_label(f"Wi-Fi do drone: conectado ({ip})" if ip else
                               "Wi-Fi do drone: NÃO conectado — conecte em WiFi-1080P-GPS-… (modo seco abre mesmo assim)")
        return True

    # ---------- iniciar ----------
    def _pedir(self, modo):
        if self.proc:
            return
        if modo == "seco":
            self._iniciar(modo)
            return
        if not self.wifi_ok:
            self._aviso("Sem o Wi-Fi do drone", "Conecte o notebook no Wi-Fi do drone (WiFi-1080P-GPS-…) antes de voar.")
            return
        extra = {"gestos": " com gestos", "manobra": " automático (sobe 1,5 m, frente/trás/direita/esquerda, desce)"}.get(modo, "")
        d = Adw.AlertDialog(heading="Confirmar voo" + extra,
                            body="Hélices presas · 5 m livres e ninguém perto · controle de rádio na mão · bateria em repouso ≥ 75 · "
                                 "drone recém-ligado se o último pouso teve estado 5 ou emergência.\n\n"
                                 "O painel vai mandar comandos de verdade.")
        d.add_response("cancelar", "Cancelar")
        d.add_response("voar", "Autorizo este voo")
        d.set_response_appearance("voar", Adw.ResponseAppearance.DESTRUCTIVE)
        d.set_default_response("cancelar")
        d.set_close_response("cancelar")
        d.connect("response", lambda _d, r: self._iniciar(modo) if r == "voar" else None)
        d.present(self)

    def _iniciar(self, modo):
        if porta_aberta():
            self._aviso("Porta ocupada", f"Já existe algo na porta {PORTA} (outro piloto aberto?). Feche-o e tente de novo.")
            return
        gestos = modo == "gestos"
        py = PY_GESTOS if gestos else PY_OPENCV
        args = [py, "-P", os.path.join(RAIZ, "scripts", "piloto_predator.py"), "--app", "--basico", "--gravar", "--web",
                "--sem-navegador", "--porta", str(PORTA)]
        if gestos:
            args.append("--gestos")
        if modo == "manobra":
            args += ["--roteiro-foto", "--alvo-altura", "1.5", "--manobra"]
        if modo in ("voar", "gestos", "manobra"):
            args += ["--voar", "--confirmo-voo"]
        log = open(os.path.join(GLib.get_user_cache_dir(), "predator-piloto.log"), "w")
        self.proc = subprocess.Popen(args, cwd=RAIZ, stdout=log, stderr=subprocess.STDOUT)
        self.voando = modo != "seco"
        self.titulo.set_subtitle({"seco": "modo seco", "voar": "VOANDO", "gestos": "VOANDO com gestos",
                                  "manobra": "VOO AUTOMÁTICO: frente, trás, direita, esquerda"}[modo])
        self.bt_parar.set_visible(True)
        self.pilha.set_visible_child_name("espera")
        self.t_espera = 0
        GLib.timeout_add(250, self._espera_porta)

    def _espera_porta(self):
        if self.proc.poll() is not None:
            self._falhou(f"o piloto saiu (código {self.proc.returncode}); veja ~/.cache/predator-piloto.log")
            return False
        if porta_aberta():
            self.web.load_uri(URL)
            self.pilha.set_visible_child_name("painel")
            GLib.timeout_add(500, self._vigia_processo)
            return False
        self.t_espera += 1
        self.lb_espera.set_label("ligando o piloto" + ("" if self.t_espera < 12 else " (carregando os gestos…)") + "…")
        if self.t_espera > 160:
            self._falhou("o painel não abriu em 40 s")
            return False
        return True

    def _vigia_processo(self):
        if self.proc and self.proc.poll() is not None:
            codigo = self.proc.returncode
            self.proc = None
            if self.fechando:
                self.get_application().quit()
            else:
                self._voltar_inicio()
                if codigo:
                    self._aviso("O piloto terminou", f"Código {codigo}. Detalhes em ~/.cache/predator-piloto.log")
            return False
        return True

    def _falhou(self, msg):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.proc = None
        self._voltar_inicio()
        self._aviso("Não foi possível abrir", msg)

    def _voltar_inicio(self):
        self.web.load_uri("about:blank")
        self.titulo.set_subtitle("escolha o modo")
        self.bt_parar.set_visible(False)
        self.pilha.set_visible_child_name("inicio")

    def _aviso(self, titulo, texto):
        d = Adw.AlertDialog(heading=titulo, body=texto)
        d.add_response("ok", "OK")
        d.present(self)

    # ---------- fechar ----------
    def _ao_fechar(self, *_):
        if not self.proc or self.proc.poll() is not None:
            return False  # fecha
        if self.fechando:
            return True
        fase = fase_atual()
        if self.voando and fase in ("voando", "armando", "pousando"):
            d = Adw.AlertDialog(heading="O drone está no ar",
                                body="Encerrar manda POUSAR e o app fecha quando ele travar no chão.")
            d.add_response("ficar", "Continuar voando")
            d.add_response("pousar", "Pousar e encerrar")
            d.set_response_appearance("pousar", Adw.ResponseAppearance.DESTRUCTIVE)
            d.set_close_response("ficar")
            d.connect("response", lambda _d, r: self._encerrar() if r == "pousar" else None)
            d.present(self)
        else:
            self._encerrar()
        return True

    def _encerrar(self):
        self.fechando = True
        self.titulo.set_subtitle("encerrando (pousa se estiver no ar)…")
        acao("escape")  # pousa e sai; o piloto só termina com o drone no chão
        GLib.timeout_add_seconds(4, self._forcar_se_no_chao)

    def _forcar_se_no_chao(self):
        if self.proc and self.proc.poll() is None and fase_atual() in (None, "chao"):
            self.proc.terminate()  # no chão (ou painel mudo): pode encerrar
        return self.proc is not None and self.proc.poll() is None


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.modo = None

    def do_command_line(self, linha):
        args = linha.get_arguments()[1:]
        self.modo = args[args.index("--modo") + 1] if "--modo" in args and args.index("--modo") + 1 < len(args) else None
        self.activate()
        return 0

    def do_activate(self):
        win = self.props.active_window
        if win is None:
            win = Janela(self, self.modo if self.modo in ("seco", "voar", "gestos", "manobra") else None)
        elif self.modo in ("seco", "voar", "gestos", "manobra"):
            win._pedir(self.modo)
        win.present()


if __name__ == "__main__":
    GLib.set_prgname(APP_ID)
    sys.exit(App().run(sys.argv))
