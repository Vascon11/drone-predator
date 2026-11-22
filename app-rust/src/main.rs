use std::cell::{Cell, RefCell};
use std::ffi::{CString, c_void};
use std::fs::File;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::rc::Rc;
use std::time::Duration;

use adw::prelude::*;
use gtk::glib::translate::from_glib_full;
use gtk::glib::{self, ControlFlow, Propagation};
use libloading::Library;

const APP_ID: &str = "local.predator.Painel";
const PORT: u16 = 8777;
const URL: &str = "http://127.0.0.1:8777/";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Mode {
    Dry,
    Fly,
    Gestures,
    Maneuver,
}

impl Mode {
    fn parse(value: &str) -> Option<Self> {
        match value {
            "seco" => Some(Self::Dry),
            "voar" => Some(Self::Fly),
            "gestos" => Some(Self::Gestures),
            "manobra" => Some(Self::Maneuver),
            _ => None,
        }
    }

    fn is_flight(self) -> bool {
        self != Self::Dry
    }

    fn subtitle(self) -> &'static str {
        match self {
            Self::Dry => "modo seco",
            Self::Fly => "VOANDO",
            Self::Gestures => "VOANDO com gestos",
            Self::Maneuver => "VOO AUTOMATICO: frente, tras, direita, esquerda",
        }
    }
}

fn requested_mode(args: &[String]) -> Option<Mode> {
    args.windows(2)
        .find(|pair| pair[0] == "--modo")
        .and_then(|pair| Mode::parse(&pair[1]))
}

struct WebKit {
    _library: Library,
    new_view: unsafe extern "C" fn() -> *mut gtk::ffi::GtkWidget,
    load_uri: unsafe extern "C" fn(*mut c_void, *const i8),
}

impl WebKit {
    fn load() -> Result<Self, String> {
        unsafe {
            let library = Library::new("libwebkitgtk-6.0.so.4")
                .map_err(|error| format!("WebKit nao encontrado: {error}"))?;
            let new_view = *library
                .get::<unsafe extern "C" fn() -> *mut gtk::ffi::GtkWidget>(b"webkit_web_view_new\0")
                .map_err(|error| format!("WebKit incompativel: {error}"))?;
            let load_uri = *library
                .get::<unsafe extern "C" fn(*mut c_void, *const i8)>(b"webkit_web_view_load_uri\0")
                .map_err(|error| format!("WebKit incompativel: {error}"))?;
            Ok(Self {
                _library: library,
                new_view,
                load_uri,
            })
        }
    }

    fn new_widget(&self) -> gtk::Widget {
        unsafe { from_glib_full((self.new_view)()) }
    }

    fn navigate(&self, widget: &gtk::Widget, uri: &str) {
        let uri = CString::new(uri).expect("URL sem byte nulo");
        unsafe { (self.load_uri)(widget.as_ptr() as *mut c_void, uri.as_ptr()) }
    }
}

struct State {
    root: PathBuf,
    app: adw::Application,
    window: adw::ApplicationWindow,
    title: adw::WindowTitle,
    stop_button: gtk::Button,
    stack: gtk::Stack,
    wifi_label: gtk::Label,
    wait_label: gtk::Label,
    webkit: WebKit,
    web: gtk::Widget,
    child: RefCell<Option<Child>>,
    flying: Cell<bool>,
    closing: Cell<bool>,
    wifi_ok: Cell<bool>,
    wait_ticks: Cell<u32>,
}

impl State {
    fn new(app: &adw::Application) -> Result<Rc<Self>, String> {
        let webkit = WebKit::load()?;
        let web = webkit.new_widget();
        web.set_hexpand(true);
        web.set_vexpand(true);

        let title = adw::WindowTitle::builder()
            .title("Predator")
            .subtitle("escolha o modo")
            .build();
        let header = adw::HeaderBar::builder().title_widget(&title).build();
        let stop_button = gtk::Button::with_label("Encerrar");
        stop_button.add_css_class("destructive-action");
        stop_button.set_visible(false);
        header.pack_end(&stop_button);

        let stack = gtk::Stack::builder()
            .transition_type(gtk::StackTransitionType::Crossfade)
            .build();
        let wifi_label = gtk::Label::new(None);
        let wait_label = gtk::Label::new(Some("ligando o piloto..."));
        stack.add_named(&start_page(&wifi_label), Some("inicio"));
        stack.add_named(&wait_page(&wait_label), Some("espera"));
        stack.add_named(&web, Some("painel"));

        let content = gtk::Box::new(gtk::Orientation::Vertical, 0);
        content.append(&header);
        content.append(&stack);
        let window = adw::ApplicationWindow::builder()
            .application(app)
            .title("Predator")
            .default_width(1400)
            .default_height(860)
            .content(&content)
            .build();

        let state = Rc::new(Self {
            root: Path::new(env!("CARGO_MANIFEST_DIR"))
                .parent()
                .expect("app-rust dentro do projeto")
                .to_path_buf(),
            app: app.clone(),
            window,
            title,
            stop_button,
            stack,
            wifi_label,
            wait_label,
            webkit,
            web,
            child: RefCell::new(None),
            flying: Cell::new(false),
            closing: Cell::new(false),
            wifi_ok: Cell::new(false),
            wait_ticks: Cell::new(0),
        });
        state.connect_signals();
        state.update_wifi();
        Ok(state)
    }

    fn connect_signals(self: &Rc<Self>) {
        let weak = Rc::downgrade(self);
        self.stop_button.connect_clicked(move |_| {
            if let Some(state) = weak.upgrade() {
                state.window.close();
            }
        });

        let weak = Rc::downgrade(self);
        self.window.connect_close_request(move |_| {
            weak.upgrade()
                .map_or(Propagation::Proceed, |state| state.close_requested())
        });

        for (name, mode) in [
            ("seco", Mode::Dry),
            ("voar", Mode::Fly),
            ("gestos", Mode::Gestures),
            ("manobra", Mode::Maneuver),
        ] {
            let action = gtk::gio::SimpleAction::new(name, None);
            let weak = Rc::downgrade(self);
            action.connect_activate(move |_, _| {
                if let Some(state) = weak.upgrade() {
                    state.request_mode(mode);
                }
            });
            self.window.add_action(&action);
        }

        let weak = Rc::downgrade(self);
        glib::timeout_add_seconds_local(2, move || {
            if let Some(state) = weak.upgrade() {
                state.update_wifi();
                ControlFlow::Continue
            } else {
                ControlFlow::Break
            }
        });
    }

    fn present(&self) {
        self.window.present();
    }

    fn update_wifi(&self) {
        let ip = drone_wifi_ip();
        self.wifi_ok.set(ip.is_some());
        self.wifi_label.set_label(&match ip {
            Some(ip) => format!("Wi-Fi do drone: conectado ({ip})"),
            None => "Wi-Fi do drone: NAO conectado - conecte em WiFi-1080P-GPS-... (modo seco abre mesmo assim)".into(),
        });
    }

    fn request_mode(self: &Rc<Self>, mode: Mode) {
        if self.child.borrow().is_some() {
            return;
        }
        if mode == Mode::Dry {
            self.start(mode);
            return;
        }
        if !self.wifi_ok.get() {
            self.alert(
                "Sem o Wi-Fi do drone",
                "Conecte o notebook no Wi-Fi do drone (WiFi-1080P-GPS-...) antes de voar.",
            );
            return;
        }

        let extra = match mode {
            Mode::Gestures => " com gestos",
            Mode::Maneuver => " automatico (sobe 1,5 m, frente/tras/direita/esquerda, desce)",
            _ => "",
        };
        let dialog = adw::AlertDialog::builder()
            .heading(format!("Confirmar voo{extra}"))
            .body("Helices presas - 5 m livres e ninguem perto - controle de radio na mao - bateria em repouso >= 75 - drone recem-ligado se o ultimo pouso teve estado 5 ou emergencia.\n\nO painel vai mandar comandos de verdade.")
            .default_response("cancelar")
            .close_response("cancelar")
            .build();
        dialog.add_responses(&[("cancelar", "Cancelar"), ("voar", "Autorizo este voo")]);
        dialog.set_response_appearance("voar", adw::ResponseAppearance::Destructive);
        let weak = Rc::downgrade(self);
        dialog.connect_response(None, move |_dialog, response| {
            if response == "voar"
                && let Some(state) = weak.upgrade()
            {
                state.start(mode);
            }
        });
        dialog.present(Some(&self.window));
    }

    fn start(self: &Rc<Self>, mode: Mode) {
        if port_open() {
            self.alert(
                "Porta ocupada",
                "Ja existe algo na porta 8777 (outro piloto aberto?). Feche-o e tente de novo.",
            );
            return;
        }

        let home = std::env::var_os("HOME")
            .map(PathBuf::from)
            .unwrap_or_default();
        let python = if mode == Mode::Gestures {
            self.root
                .parent()
                .unwrap_or(&self.root)
                .join("gestos/.venv/bin/python")
        } else {
            home.join(".local/share/aruco-venv/bin/python")
        };
        let mut args = vec![
            "-P".into(),
            self.root
                .join("scripts/piloto_predator.py")
                .into_os_string(),
            "--app".into(),
            "--basico".into(),
            "--gravar".into(),
            "--web".into(),
            "--sem-navegador".into(),
            "--porta".into(),
            PORT.to_string().into(),
        ];
        if mode == Mode::Gestures {
            args.push("--gestos".into());
        }
        if mode == Mode::Maneuver {
            args.extend([
                "--roteiro-foto".into(),
                "--alvo-altura".into(),
                "1.5".into(),
                "--manobra".into(),
            ]);
        }
        if mode.is_flight() {
            args.extend(["--voar".into(), "--confirmo-voo".into()]);
        }

        let cache = std::env::var_os("XDG_CACHE_HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|| home.join(".cache"));
        let log_path = cache.join("predator-piloto.log");
        let log = match File::create(&log_path) {
            Ok(file) => file,
            Err(error) => {
                self.alert(
                    "Nao foi possivel abrir",
                    &format!("Erro ao criar {}: {error}", log_path.display()),
                );
                return;
            }
        };
        let stderr = match log.try_clone() {
            Ok(file) => file,
            Err(error) => {
                self.alert(
                    "Nao foi possivel abrir",
                    &format!("Erro ao preparar o log: {error}"),
                );
                return;
            }
        };
        match Command::new(python)
            .args(args)
            .current_dir(&self.root)
            .stdout(Stdio::from(log))
            .stderr(Stdio::from(stderr))
            .spawn()
        {
            Ok(child) => *self.child.borrow_mut() = Some(child),
            Err(error) => {
                self.alert(
                    "Nao foi possivel abrir",
                    &format!("Falha ao iniciar o piloto: {error}"),
                );
                return;
            }
        }

        self.flying.set(mode.is_flight());
        self.title.set_subtitle(mode.subtitle());
        self.stop_button.set_visible(true);
        self.stack.set_visible_child_name("espera");
        self.wait_ticks.set(0);
        self.wait_for_port();
    }

    fn wait_for_port(self: &Rc<Self>) {
        let weak = Rc::downgrade(self);
        glib::timeout_add_local(Duration::from_millis(250), move || {
            let Some(state) = weak.upgrade() else {
                return ControlFlow::Break;
            };
            if let Some(code) = state.child_exit_code() {
                state.failed(&format!(
                    "o piloto saiu (codigo {code}); veja ~/.cache/predator-piloto.log"
                ));
                return ControlFlow::Break;
            }
            if port_open() {
                state.webkit.navigate(&state.web, URL);
                state.stack.set_visible_child_name("painel");
                state.watch_process();
                return ControlFlow::Break;
            }
            let ticks = state.wait_ticks.get() + 1;
            state.wait_ticks.set(ticks);
            state.wait_label.set_label(if ticks < 12 {
                "ligando o piloto..."
            } else {
                "ligando o piloto (carregando os gestos...)..."
            });
            if ticks > 160 {
                state.failed("o painel nao abriu em 40 s");
                return ControlFlow::Break;
            }
            ControlFlow::Continue
        });
    }

    fn watch_process(self: &Rc<Self>) {
        let weak = Rc::downgrade(self);
        glib::timeout_add_local(Duration::from_millis(500), move || {
            let Some(state) = weak.upgrade() else {
                return ControlFlow::Break;
            };
            if let Some(code) = state.child_exit_code() {
                state.child.borrow_mut().take();
                if state.closing.get() {
                    state.app.quit();
                } else {
                    state.back_to_start();
                    if code != 0 {
                        state.alert(
                            "O piloto terminou",
                            &format!("Codigo {code}. Detalhes em ~/.cache/predator-piloto.log"),
                        );
                    }
                }
                ControlFlow::Break
            } else {
                ControlFlow::Continue
            }
        });
    }

    fn child_exit_code(&self) -> Option<i32> {
        self.child
            .borrow_mut()
            .as_mut()
            .and_then(|child| child.try_wait().ok().flatten())
            .map(|status| status.code().unwrap_or(-1))
    }

    fn failed(&self, message: &str) {
        if let Some(child) = self.child.borrow_mut().as_mut() {
            let _ = child.kill();
        }
        self.child.borrow_mut().take();
        self.back_to_start();
        self.alert("Nao foi possivel abrir", message);
    }

    fn back_to_start(&self) {
        self.webkit.navigate(&self.web, "about:blank");
        self.title.set_subtitle("escolha o modo");
        self.stop_button.set_visible(false);
        self.stack.set_visible_child_name("inicio");
    }

    fn close_requested(self: &Rc<Self>) -> Propagation {
        if self.child_exit_code().is_some() || self.child.borrow().is_none() {
            return Propagation::Proceed;
        }
        if self.closing.get() {
            return Propagation::Stop;
        }
        let phase = current_phase();
        if self.flying.get() && matches!(phase.as_deref(), Some("voando" | "armando" | "pousando"))
        {
            let dialog = adw::AlertDialog::builder()
                .heading("O drone esta no ar")
                .body("Encerrar manda POUSAR e o app fecha quando ele travar no chao.")
                .close_response("ficar")
                .build();
            dialog.add_responses(&[
                ("ficar", "Continuar voando"),
                ("pousar", "Pousar e encerrar"),
            ]);
            dialog.set_response_appearance("pousar", adw::ResponseAppearance::Destructive);
            let weak = Rc::downgrade(self);
            dialog.connect_response(None, move |_dialog, response| {
                if response == "pousar"
                    && let Some(state) = weak.upgrade()
                {
                    state.finish();
                }
            });
            dialog.present(Some(&self.window));
        } else {
            self.finish();
        }
        Propagation::Stop
    }

    fn finish(self: &Rc<Self>) {
        self.closing.set(true);
        self.title
            .set_subtitle("encerrando (pousa se estiver no ar)...");
        post_action("escape");
        let weak = Rc::downgrade(self);
        glib::timeout_add_seconds_local(4, move || {
            let Some(state) = weak.upgrade() else {
                return ControlFlow::Break;
            };
            if state.child_exit_code().is_some() {
                state.child.borrow_mut().take();
                state.app.quit();
                return ControlFlow::Break;
            }
            if matches!(current_phase().as_deref(), None | Some("chao"))
                && let Some(child) = state.child.borrow_mut().as_mut()
            {
                let _ = child.kill();
            }
            ControlFlow::Continue
        });
    }

    fn alert(&self, heading: &str, body: &str) {
        let dialog = adw::AlertDialog::builder()
            .heading(heading)
            .body(body)
            .build();
        dialog.add_response("ok", "OK");
        dialog.present(Some(&self.window));
    }
}

fn start_page(wifi_label: &gtk::Label) -> adw::StatusPage {
    let page = adw::StatusPage::builder()
        .icon_name("predator-drone")
        .title("Predator")
        .description("Hexacoptero pelo notebook: video, telemetria, teclado, roteiros e gestos.")
        .build();
    let content = gtk::Box::new(gtk::Orientation::Vertical, 12);
    content.set_halign(gtk::Align::Center);
    wifi_label.add_css_class("dim-label");
    content.append(wifi_label);
    for (name, label, style) in [
        (
            "seco",
            "Abrir em modo seco (nao envia nada)",
            "suggested-action",
        ),
        ("voar", "Voar", "destructive-action"),
        ("gestos", "Voar com gestos", "destructive-action"),
        (
            "manobra",
            "Teste automatico: frente, tras, direita, esquerda",
            "destructive-action",
        ),
    ] {
        let button = gtk::Button::with_label(label);
        button.set_action_name(Some(&format!("win.{name}")));
        button.add_css_class("pill");
        button.add_css_class(style);
        button.set_size_request(340, -1);
        content.append(&button);
    }
    let hint = gtk::Label::new(Some(
        "Teclado no painel: T destrava - E/Q sobe/desce - WASD move - H segura - L pousa - X emergencia",
    ));
    hint.add_css_class("caption");
    hint.add_css_class("dim-label");
    content.append(&hint);
    page.set_child(Some(&content));
    page
}

fn wait_page(label: &gtk::Label) -> gtk::Box {
    let content = gtk::Box::new(gtk::Orientation::Vertical, 16);
    content.set_valign(gtk::Align::Center);
    content.set_halign(gtk::Align::Center);
    let spinner = gtk::Spinner::new();
    spinner.set_size_request(48, 48);
    spinner.start();
    content.append(&spinner);
    content.append(label);
    content
}

fn drone_wifi_ip() -> Option<String> {
    let output = Command::new("ip")
        .args(["-br", "addr", "show", "wlp2s0"])
        .output()
        .ok()?;
    String::from_utf8_lossy(&output.stdout)
        .split_whitespace()
        .find(|part| part.starts_with("192.168.0."))
        .and_then(|part| part.split('/').next())
        .map(str::to_owned)
}

fn port_open() -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], PORT));
    TcpStream::connect_timeout(&address, Duration::from_millis(200)).is_ok()
}

fn http_request(method: &str, path: &str, body: Option<&str>) -> Option<String> {
    let address = SocketAddr::from(([127, 0, 0, 1], PORT));
    let mut stream = TcpStream::connect_timeout(&address, Duration::from_secs(1)).ok()?;
    stream.set_read_timeout(Some(Duration::from_secs(1))).ok()?;
    stream
        .set_write_timeout(Some(Duration::from_secs(1)))
        .ok()?;
    let body = body.unwrap_or("");
    let request = format!(
        "{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{PORT}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );
    stream.write_all(request.as_bytes()).ok()?;
    let mut response = String::new();
    stream.read_to_string(&mut response).ok()?;
    response
        .split_once("\r\n\r\n")
        .map(|(_, body)| body.to_owned())
}

fn current_phase() -> Option<String> {
    let body = http_request("GET", "/estado", None)?;
    serde_json::from_str::<serde_json::Value>(&body).ok()?["fase"]
        .as_str()
        .map(str::to_owned)
}

fn post_action(key: &str) {
    let body = serde_json::json!({ "k": key }).to_string();
    let _ = http_request("POST", "/acao", Some(&body));
}

fn main() -> glib::ExitCode {
    let app = adw::Application::builder()
        .application_id(APP_ID)
        .flags(gtk::gio::ApplicationFlags::HANDLES_COMMAND_LINE)
        .build();
    let state: Rc<RefCell<Option<Rc<State>>>> = Rc::new(RefCell::new(None));

    let state_for_activate = state.clone();
    app.connect_activate(move |app| {
        if let Some(existing) = state_for_activate.borrow().as_ref() {
            existing.present();
            return;
        }
        match State::new(app) {
            Ok(created) => {
                created.present();
                *state_for_activate.borrow_mut() = Some(created);
            }
            Err(error) => eprintln!("Predator: {error}"),
        }
    });

    let state_for_command = state.clone();
    app.connect_command_line(move |app, command_line| {
        let args: Vec<String> = command_line
            .arguments()
            .iter()
            .map(|arg| arg.to_string_lossy().into_owned())
            .collect();
        app.activate();
        if let (Some(mode), Some(current)) = (
            requested_mode(&args),
            state_for_command.borrow().as_ref().cloned(),
        ) {
            current.request_mode(mode);
        }
        0.into()
    });

    app.run()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_requested_mode() {
        let args = vec!["predator".into(), "--modo".into(), "gestos".into()];
        assert_eq!(requested_mode(&args), Some(Mode::Gestures));
    }

    #[test]
    fn rejects_unknown_or_incomplete_mode() {
        assert_eq!(requested_mode(&["predator".into(), "--modo".into()]), None);
        assert_eq!(
            requested_mode(&["predator".into(), "--modo".into(), "x".into()]),
            None
        );
    }
}
