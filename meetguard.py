# -*- coding: utf-8 -*-
"""
Dirigível Meet Guard
Liga e desliga microfone e câmera com atalhos, mostra o estado de cada um
em ícones perto do relógio e traz uma janela de configurações.

Linha de comando:
  MeetGuard.exe                         abre e mostra a janela
  MeetGuard.exe --tray                  abre só nos ícones (usado ao iniciar com o Windows)
  MeetGuard.exe --restaurar             libera microfone e câmera
  MeetGuard.exe --configurar-inicializacao sim|nao
"""

import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import time
import webbrowser

import marca

CREATE_NO_WINDOW = 0x08000000
PASTA_DADOS = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), marca.PASTA_DADOS)
ARQ_CONFIG = os.path.join(PASTA_DADOS, "config.json")
ARQ_LOG = os.path.join(PASTA_DADOS, "log.txt")
CONFIG_ANTIGA = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "MicCam", "config.json")

PADRAO = {
    "atalho_mic": "ctrl+alt+m",
    "atalho_cam": "ctrl+alt+c",
    "intervalo_mic": 1,
    "intervalo_cam": 3,
    "mostrar_avisos": True,
    "cameras": None,        # null = todas
    "ja_abriu": False,      # primeira abertura mostra a aba Ajuda
}


# =============================== Utilidades ===============================
def log(msg):
    try:
        os.makedirs(PASTA_DADOS, exist_ok=True)
        with open(ARQ_LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + str(msg) + "\n")
    except Exception:
        pass


def instalar_registro_de_erros():
    import traceback

    def gancho(tipo, valor, tb):
        log("ERRO:\n" + "".join(traceback.format_exception(tipo, valor, tb)))

    sys.excepthook = gancho
    threading.excepthook = lambda a: gancho(a.exc_type, a.exc_value, a.exc_traceback)


def recurso(nome):
    bases = [getattr(sys, "_MEIPASS", ""), os.path.dirname(os.path.abspath(__file__))]
    for base in bases:
        for sub in ("recursos", os.path.join("build", "recursos")):
            p = os.path.join(base, sub, nome)
            if base and os.path.exists(p):
                return p
    return None


def carregar_config():
    cfg = dict(PADRAO)
    origem = ARQ_CONFIG if os.path.exists(ARQ_CONFIG) else CONFIG_ANTIGA  # migra do MicCam
    try:
        with open(origem, encoding="utf-8") as f:
            cfg.update({k: v for k, v in json.load(f).items() if k in PADRAO})
    except Exception:
        pass
    salvar_config(cfg)
    return cfg


def salvar_config(cfg):
    try:
        os.makedirs(PASTA_DADOS, exist_ok=True)
        with open(ARQ_CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log(f"erro ao salvar config: {e!r}")


CFG = carregar_config()


def _powershell(cmd, timeout=60):
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", cmd],
        capture_output=True, timeout=timeout, creationflags=CREATE_NO_WINDOW,
    )


def _ps_str(txt):
    return "'" + str(txt).replace("'", "''") + "'"


# ============================= Administrador ==============================
def eh_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def comando_do_programa():
    """[executável, argumentos...] para abrir este programa."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return [pyw if os.path.exists(pyw) else exe, os.path.abspath(sys.argv[0])]


def relancar_como_admin():
    cmd = comando_do_programa()
    params = " ".join(f'"{a}"' for a in cmd[1:] + sys.argv[1:])
    ctypes.windll.shell32.ShellExecuteW(None, "runas", cmd[0], params, None, 1)
    sys.exit(0)


# ======================== Instância única + "mostrar" ======================
NOME_MUTEX = "Global\\DirigivelMeetGuard_Mutex"
NOME_EVENTO = "Global\\DirigivelMeetGuard_Mostrar"
_k32 = ctypes.windll.kernel32 if os.name == "nt" else None
if _k32:
    _k32.CreateMutexW.restype = ctypes.c_void_p
    _k32.CreateEventW.restype = ctypes.c_void_p
    _k32.OpenEventW.restype = ctypes.c_void_p
    _k32.SetEvent.argtypes = [ctypes.c_void_p]
    _k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]


def ja_esta_aberto():
    _k32.CreateMutexW(None, False, NOME_MUTEX)
    return _k32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def pedir_para_mostrar():
    h = _k32.OpenEventW(0x0002, False, NOME_EVENTO)  # EVENT_MODIFY_STATE
    if h:
        _k32.SetEvent(h)


def esperar_pedidos_de_mostrar(callback):
    h = _k32.CreateEventW(None, False, False, NOME_EVENTO)
    while True:
        if _k32.WaitForSingleObject(h, 0xFFFFFFFF) == 0:
            callback()


# =============================== Microfone ================================
def _volume_mic():
    import comtypes
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    try:
        comtypes.CoInitialize()
    except OSError:
        pass
    try:
        disp = AudioUtilities.GetMicrophone()
    except Exception:
        return None
    if disp is None:
        return None
    ev = getattr(disp, "EndpointVolume", None)
    if ev is not None:
        return ev
    interface = disp.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def mic_ligado():
    try:
        v = _volume_mic()
        return None if v is None else not bool(v.GetMute())
    except Exception:
        return None


def definir_mic(ligar):
    v = _volume_mic()
    if v is not None:
        v.SetMute(0 if ligar else 1, None)


# ================================ Câmera ==================================
PS_LISTAR = (
    "$d = Get-PnpDevice -PresentOnly -Class Camera,Image -ErrorAction SilentlyContinue | "
    "Where-Object { $_.Class -eq 'Camera' -or $_.FriendlyName -match 'cam|video|v.deo' }; "
    "ConvertTo-Json -Compress -InputObject @($d | Select-Object InstanceId, Status, FriendlyName)"
)


def listar_cameras():
    try:
        r = _powershell(PS_LISTAR, timeout=30)
        saida = r.stdout.decode("utf-8", errors="replace").strip()
        if not saida:
            return []
        dados = json.loads(saida)
        if isinstance(dados, dict):
            dados = [dados]
        return [d for d in dados if d and d.get("InstanceId")]
    except Exception as e:
        log(f"erro ao listar câmeras: {e!r}")
        return []


def definir_cameras(cams, ligar):
    acao = "Enable-PnpDevice" if ligar else "Disable-PnpDevice"
    cmd = "; ".join(f"{acao} -InstanceId {_ps_str(c['InstanceId'])} -Confirm:$false" for c in cams)
    if cmd:
        _powershell(cmd)


def cameras_controladas(cams):
    escolhidas = CFG.get("cameras")
    return cams if not escolhidas else [c for c in cams if c["InstanceId"] in escolhidas]


def cam_ligada(cams):
    cams = cameras_controladas(cams)
    if not cams:
        return None
    return any(c.get("Status") == "OK" for c in cams)


CHAVES_PRIV = [
    r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam",
    r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam\NonPackaged",
]


def liberar_privacidade_camera():
    """Desfaz o bloqueio de privacidade usado pelo antigo MicCam."""
    import winreg
    for chave in CHAVES_PRIV:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chave, 0,
                                winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as k:
                if str(winreg.QueryValueEx(k, "Value")[0]).lower() == "deny":
                    winreg.SetValueEx(k, "Value", 0, winreg.REG_SZ, "Allow")
        except OSError:
            pass


# ========================= Iniciar com o Windows ==========================
def inicializacao_ativa():
    r = subprocess.run(["schtasks", "/query", "/tn", marca.NOME_TAREFA],
                       capture_output=True, creationflags=CREATE_NO_WINDOW)
    return r.returncode == 0


def definir_inicializacao(ativar):
    if not ativar:
        subprocess.run(["schtasks", "/delete", "/tn", marca.NOME_TAREFA, "/f"],
                       capture_output=True, creationflags=CREATE_NO_WINDOW)
        return
    cmd = comando_do_programa()
    args = " ".join([f'"{a}"' for a in cmd[1:]] + ["--tray"])
    usuario = "$env:USERDOMAIN + '\\' + $env:USERNAME"
    ps = (
        f"$u = {usuario}; "
        f"$a = New-ScheduledTaskAction -Execute {_ps_str(cmd[0])} -Argument {_ps_str(args)}; "
        "$t = New-ScheduledTaskTrigger -AtLogOn -User $u; "
        "$p = New-ScheduledTaskPrincipal -UserId $u -LogonType Interactive -RunLevel Highest; "
        "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
        "-ExecutionTimeLimit ([TimeSpan]::Zero); "
        f"Register-ScheduledTask -TaskName {_ps_str(marca.NOME_TAREFA)} -Action $a -Trigger $t "
        "-Principal $p -Settings $s -Force | Out-Null"
    )
    r = _powershell(ps)
    if r.returncode != 0:
        log("erro ao criar inicialização: " + r.stderr.decode("utf-8", "replace"))


# ============================ Ícones da bandeja ===========================
VERDE, VERMELHO, CINZA, BRANCO = (46, 125, 50), (198, 40, 40), (120, 120, 120), (255, 255, 255)


def _base(estado):
    from PIL import Image, ImageDraw
    S = 256
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cor = CINZA if estado is None else (VERDE if estado else VERMELHO)
    d.ellipse((4, 4, S - 4, S - 4), fill=cor)
    return img, d, cor


def _risco(d, cor):
    d.line((60, 60, 196, 196), fill=cor, width=40)
    d.line((60, 60, 196, 196), fill=BRANCO, width=18)


def icone_mic(estado, tam=64):
    img, d, cor = _base(estado)
    d.rounded_rectangle((100, 44, 156, 146), radius=28, fill=BRANCO)
    d.arc((76, 80, 180, 172), start=0, end=180, fill=BRANCO, width=12)
    d.line((128, 172, 128, 200), fill=BRANCO, width=12)
    d.line((100, 204, 156, 204), fill=BRANCO, width=12)
    if estado is False:
        _risco(d, cor)
    return img.resize((tam, tam))


def icone_cam(estado, tam=64):
    img, d, cor = _base(estado)
    d.rounded_rectangle((52, 88, 160, 168), radius=14, fill=BRANCO)
    d.polygon([(166, 128), (206, 98), (206, 158)], fill=BRANCO)
    if estado is False:
        _risco(d, cor)
    return img.resize((tam, tam))


NOMES = {"mic": "Microfone", "cam": "Câmera"}
ICONES = {"mic": icone_mic, "cam": icone_cam}


def texto_estado(qual, estado):
    a = "a" if qual == "cam" else "o"
    if estado is None:
        return f"não encontrad{a}"
    return f"ligad{a}" if estado else f"desligad{a}"


def formatar_atalho(atalho):
    nomes = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "windows": "Win", "left windows": "Win",
             "right windows": "Win", "alt gr": "AltGr"}
    return " + ".join(nomes.get(p.strip(), p.strip().upper()) for p in atalho.split("+"))


# ================================ Aplicativo ==============================
class MeetGuard:
    def __init__(self, mostrar_janela):
        import pystray
        self.pystray = pystray
        self.fila = queue.Queue()
        self.trava = {"mic": threading.Lock(), "cam": threading.Lock()}
        self.capturando = None
        self.hotkeys = {}
        self.cams = listar_cameras()
        self.estado = {"mic": mic_ligado(), "cam": cam_ligada(self.cams)}
        log(f"câmeras: {[c.get('FriendlyName') for c in self.cams]}; estado: {self.estado}")

        self.icons = {
            q: pystray.Icon(f"DirigivelMeetGuard_{q}", ICONES[q](self.estado[q]),
                            self._dica(q), menu=self._menu_bandeja(q))
            for q in ("mic", "cam")
        }
        self.janela = Janela(self)
        if mostrar_janela:
            primeira = not CFG.get("ja_abriu")
            if primeira:
                CFG["ja_abriu"] = True
                salvar_config(CFG)
            # mostra depois que a janela termina de montar (evita abrir escondida)
            self.janela.root.after(500, lambda: self.janela.mostrar("Ajuda" if primeira else None))

    # ---------- infraestrutura ----------
    @staticmethod
    def bg(func, *args):
        threading.Thread(target=func, args=args, daemon=True).start()

    def na_janela(self, func):
        """Executa func na thread da janela (tkinter não aceita outras threads)."""
        self.fila.put(func)

    def avisar(self, qual, msg, forcar=False):
        if forcar or CFG.get("mostrar_avisos", True):
            try:
                self.icons[qual].notify(msg, marca.PRODUTO)
            except Exception:
                pass

    def _dica(self, q):
        return f"{marca.NOME_CURTO} · {NOMES[q]} {texto_estado(q, self.estado[q])} " \
               f"({formatar_atalho(CFG['atalho_' + q])})"

    def _menu_bandeja(self, q):
        M = self.pystray.MenuItem
        return self.pystray.Menu(
            M(lambda _i: f"{'Desligar' if self.estado[q] else 'Ligar'} {NOMES[q].lower()}",
              lambda: self.bg(self.alternar, q), default=True),
            M(f"Abrir {marca.NOME_CURTO}", lambda: self.na_janela(self.janela.mostrar)),
            self.pystray.Menu.SEPARATOR,
            M("Sair", lambda: self.sair()),
        )

    def atualizar(self, q, estado, avisar=False):
        self.estado[q] = estado
        ic = self.icons[q]
        ic.icon = ICONES[q](estado)
        ic.title = self._dica(q)
        if avisar:
            self.avisar(q, f"{NOMES[q]} {texto_estado(q, estado).upper()}")
        self.na_janela(lambda: self.janela.mostrar_estado(q))

    # ---------- ações ----------
    def alternar(self, q):
        if self.capturando or not self.trava[q].acquire(blocking=False):
            return
        try:
            if q == "mic":
                atual = mic_ligado()
                if atual is not None:
                    definir_mic(not atual)
                self.atualizar("mic", mic_ligado(), avisar=True)
            else:
                cams = cameras_controladas(listar_cameras())
                if cams:
                    self.na_janela(lambda: self.janela.ocupado("cam", True))
                    definir_cameras(cams, not cam_ligada(cams))
                self.atualizar("cam", self.verificar_cameras(), avisar=True)
        except Exception as e:
            log(f"erro ao alternar {q}: {e!r}")
            self.avisar(q, f"Não foi possível alterar: {e}", forcar=True)
        finally:
            self.trava[q].release()
            self.na_janela(lambda: self.janela.ocupado(q, False))

    def verificar_cameras(self):
        cams = listar_cameras()
        assinatura = lambda lst: [(c["InstanceId"], c.get("Status")) for c in lst]  # noqa: E731
        if assinatura(cams) != assinatura(self.cams):
            self.cams = cams
            self.na_janela(self.janela.mostrar_cameras)
        self.cams = cams
        return cam_ligada(cams)

    def escolher_camera(self, iid, marcar):
        todas = [c["InstanceId"] for c in self.cams]
        escolhidas = set(CFG.get("cameras") or todas) & set(todas)
        if marcar:
            escolhidas.add(iid)
        else:
            if escolhidas <= {iid}:
                self.avisar("cam", "Pelo menos uma câmera precisa ficar marcada.", forcar=True)
                self.na_janela(self.janela.mostrar_cameras)
                return
            escolhidas.discard(iid)
            cam = next((c for c in self.cams if c["InstanceId"] == iid), None)
            if cam and cam.get("Status") != "OK":
                definir_cameras([cam], True)  # câmera fora do controle volta a funcionar
        CFG["cameras"] = None if escolhidas >= set(todas) else sorted(escolhidas)
        salvar_config(CFG)
        with self.trava["cam"]:
            self.atualizar("cam", self.verificar_cameras())
        self.na_janela(self.janela.mostrar_cameras)

    def restaurar_tudo(self):
        with self.trava["mic"], self.trava["cam"]:
            definir_mic(True)
            liberar_privacidade_camera()
            definir_cameras([c for c in listar_cameras() if c.get("Status") != "OK"], True)
            self.atualizar("mic", mic_ligado())
            self.atualizar("cam", self.verificar_cameras())
        self.avisar("cam", "Microfone e câmera liberados.", forcar=True)

    # ---------- atalhos ----------
    def registrar_atalhos(self):
        import keyboard
        for h in self.hotkeys.values():
            try:
                keyboard.remove_hotkey(h)
            except Exception:
                pass
        self.hotkeys = {}
        for q in ("mic", "cam"):
            try:
                self.hotkeys[q] = keyboard.add_hotkey(CFG["atalho_" + q], lambda q=q: self.bg(self.alternar, q))
            except Exception as e:
                log(f"atalho inválido {CFG['atalho_' + q]!r}: {e!r}")
                self.avisar(q, f"Atalho inválido: {CFG['atalho_' + q]}. Ajuste na janela.", forcar=True)
            self.icons[q].title = self._dica(q)

    def capturar_atalho(self, q):
        """Espera o usuário apertar a nova combinação. Devolve mensagem de erro ou None."""
        import keyboard
        if self.capturando:
            return "Já estou esperando outro atalho."
        self.capturando = q
        try:
            for h in self.hotkeys.values():  # evita disparar o atalho atual durante a gravação
                try:
                    keyboard.remove_hotkey(h)
                except Exception:
                    pass
            self.hotkeys = {}
            time.sleep(0.3)
            novo = keyboard.read_hotkey(suppress=False)
            outro = "cam" if q == "mic" else "mic"
            modificadores = {"ctrl", "alt", "shift", "windows", "left windows", "right windows", "alt gr"}
            partes = novo.split("+") if novo else []
            if not novo or novo == "esc":
                return "Alteração cancelada."
            if not (set(partes) & modificadores) and not (len(partes) == 1 and partes[0].startswith("f")):
                return "Use uma combinação com Ctrl, Alt, Shift ou Win (ou uma tecla F1–F24)."
            if novo == CFG["atalho_" + outro]:
                return f"{formatar_atalho(novo)} já é o atalho de {NOMES[outro].lower()}."
            CFG["atalho_" + q] = novo
            salvar_config(CFG)
            return None
        finally:
            self.capturando = None
            self.registrar_atalhos()

    # ---------- ciclo de vida ----------
    def _loop(self, q):
        while True:
            time.sleep(max(1.0, float(CFG.get("intervalo_" + q, 3))))
            if self.trava[q].locked():
                continue
            try:
                e = mic_ligado() if q == "mic" else self.verificar_cameras()
                if e != self.estado[q] and not self.trava[q].locked():
                    self.atualizar(q, e)
            except Exception as ex:
                log(f"erro verificando {q}: {ex!r}")

    def _rodar_icone(self, q):
        try:
            self.icons[q].run()
        except Exception:
            import traceback
            log(f"ícone {q}: ERRO\n" + traceback.format_exc())

    def sair(self):
        try:
            import keyboard
            keyboard.unhook_all()
        except Exception:
            pass
        for ic in self.icons.values():
            try:
                ic.stop()
            except Exception:
                pass
        log("encerrado pelo usuário")
        os._exit(0)

    def rodar(self):
        self.registrar_atalhos()
        for q in ("mic", "cam"):
            threading.Thread(target=self._rodar_icone, args=(q,), daemon=True).start()
            threading.Thread(target=self._loop, args=(q,), daemon=True).start()
        threading.Thread(target=esperar_pedidos_de_mostrar,
                         args=(lambda: self.na_janela(self.janela.mostrar),), daemon=True).start()
        log("rodando")
        self.janela.loop()


# ================================= Janela =================================
def _misturar(hex_cor, alvo, t):
    h = hex_cor.lstrip("#")
    c = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(a + (b - a) * t):02x}" for a, b in zip(c, alvo))


COR = marca.COR_PRINCIPAL
COR_ESCURA = _misturar(COR, (0, 0, 0), 0.25)
COR_CLARA = _misturar(COR, (255, 255, 255), 0.85)
VERDE_UI, VERMELHO_UI, CINZA_UI = "#2E7D32", "#C62828", "#757575"


class Janela:
    def __init__(self, app):
        import customtkinter as ctk
        from PIL import Image
        self.app, self.ctk, self.Image = app, ctk, Image
        ctk.set_appearance_mode("light")
        self.root = root = ctk.CTk()
        root.withdraw()
        root.title(marca.PRODUTO)
        root.geometry("560x720")
        root.minsize(520, 680)
        root.protocol("WM_DELETE_WINDOW", self.esconder)
        ico = recurso("app.ico")
        if ico:
            try:
                root.iconbitmap(ico)
                root.after(300, lambda: root.iconbitmap(ico))  # o customtkinter troca o ícone depois de abrir
            except Exception:
                pass

        self.F = lambda tam, peso="normal": ctk.CTkFont(family="Segoe UI", size=tam, weight=peso)
        self.w = {"mic": {}, "cam": {}}
        self._montar_cabecalho()
        self._montar_abas()
        self._montar_rodape()
        root.after(100, self._processar_fila)

    # ---------- estrutura ----------
    def _img_logo(self, tam):
        caminho = recurso("logo.png")
        if not caminho:
            return None
        img = self.Image.open(caminho)
        return self.ctk.CTkImage(light_image=img, dark_image=img, size=(tam, tam))

    def _montar_cabecalho(self):
        ctk = self.ctk
        cab = ctk.CTkFrame(self.root, fg_color=COR, corner_radius=0, height=84)
        cab.pack(fill="x")
        cab.pack_propagate(False)
        logo = self._img_logo(52)
        if logo:
            ctk.CTkLabel(cab, image=logo, text="").pack(side="left", padx=(20, 12))
        txt = ctk.CTkFrame(cab, fg_color="transparent")
        txt.pack(side="left", fill="y", pady=14)
        ctk.CTkLabel(txt, text=marca.NOME_CURTO, font=self.F(22, "bold"), text_color="white",
                     anchor="w").pack(anchor="w")
        ctk.CTkLabel(txt, text=f"por {marca.EMPRESA}", font=self.F(13),
                     text_color=_misturar(COR, (255, 255, 255), 0.7), anchor="w").pack(anchor="w")

    def _montar_abas(self):
        ctk = self.ctk
        self.abas = ctk.CTkTabview(
            self.root, fg_color="#F4F6FA", corner_radius=12,
            segmented_button_selected_color=COR, segmented_button_selected_hover_color=COR_ESCURA,
            segmented_button_unselected_color=_misturar(COR, (255, 255, 255), 0.45),
            segmented_button_unselected_hover_color=_misturar(COR, (255, 255, 255), 0.3),
            segmented_button_fg_color=_misturar(COR, (255, 255, 255), 0.45), text_color="white")
        self.abas.pack(fill="both", expand=True, padx=16, pady=(10, 0))
        for nome in ("Controles", "Câmeras", "Opções", "Ajuda", "Sobre"):
            self.abas.add(nome)
        self.abas._segmented_button.configure(font=self.F(13, "bold"))
        self._aba_controles(self.abas.tab("Controles"))
        self._aba_cameras(self.abas.tab("Câmeras"))
        self._aba_opcoes(self.abas.tab("Opções"))
        self._aba_ajuda(self.abas.tab("Ajuda"))
        self._aba_sobre(self.abas.tab("Sobre"))

    def _montar_rodape(self):
        ctk = self.ctk
        rod = ctk.CTkFrame(self.root, fg_color="transparent")
        rod.pack(fill="x", padx=20, pady=12)
        ctk.CTkLabel(rod, text="Fechar esta janela mantém o Meet Guard ativo perto do relógio.",
                     font=self.F(12), text_color="#6B7380").pack(side="left")
        ctk.CTkButton(rod, text="Sair", width=70, height=30, font=self.F(12),
                      fg_color="#E3E7EE", hover_color="#D5DBE5", text_color="#1E2530",
                      command=self.app.sair).pack(side="right")

    def _cartao(self, pai):
        c = self.ctk.CTkFrame(pai, fg_color="white", corner_radius=12, border_width=1, border_color="#E1E5EC")
        c.pack(fill="x", padx=6, pady=8)
        return c

    def _botao(self, pai, texto, cmd, largura=120, secundario=False):
        if secundario:
            return self.ctk.CTkButton(pai, text=texto, command=cmd, width=largura, height=34,
                                      corner_radius=8, font=self.F(13), fg_color="#E3E7EE",
                                      hover_color="#D5DBE5", text_color="#1E2530")
        return self.ctk.CTkButton(pai, text=texto, command=cmd, width=largura, height=34, corner_radius=8,
                                  font=self.F(13, "bold"), fg_color=COR, hover_color=COR_ESCURA)

    # ---------- aba Controles ----------
    def _aba_controles(self, aba):
        ctk = self.ctk
        for q in ("mic", "cam"):
            w = self.w[q]
            c = self._cartao(aba)
            topo = ctk.CTkFrame(c, fg_color="transparent")
            topo.pack(fill="x", padx=16, pady=(14, 6))
            w["icone"] = ctk.CTkLabel(topo, text="")
            w["icone"].pack(side="left", padx=(0, 12))
            col = ctk.CTkFrame(topo, fg_color="transparent")
            col.pack(side="left")
            ctk.CTkLabel(col, text=NOMES[q], font=self.F(17, "bold"), text_color="#1E2530",
                         anchor="w").pack(anchor="w")
            w["status"] = ctk.CTkLabel(col, text="", font=self.F(13, "bold"), anchor="w")
            w["status"].pack(anchor="w")
            w["botao"] = self._botao(topo, "", lambda q=q: self.app.bg(self.app.alternar, q), largura=130)
            w["botao"].pack(side="right")

            linha = ctk.CTkFrame(c, fg_color="#F4F6FA", corner_radius=8)
            linha.pack(fill="x", padx=16, pady=(6, 14))
            ctk.CTkLabel(linha, text="Atalho", font=self.F(12), text_color="#6B7380").pack(
                side="left", padx=(12, 8), pady=8)
            w["atalho"] = ctk.CTkLabel(linha, text="", font=self.F(14, "bold"), text_color="#1E2530")
            w["atalho"].pack(side="left", pady=8)
            w["gravar"] = self._botao(linha, "Alterar", lambda q=q: self.gravar_atalho(q),
                                      largura=90, secundario=True)
            w["gravar"].pack(side="right", padx=8, pady=6)
            self.mostrar_estado(q)

        dica = ctk.CTkFrame(aba, fg_color="transparent")
        dica.pack(pady=(6, 0))
        ctk.CTkLabel(dica, text="Não vê os ícones perto do relógio?", font=self.F(12),
                     text_color="#6B7380").pack(side="left")
        ctk.CTkButton(dica, text="Veja como deixá-los à mostra", width=10, height=24, font=self.F(12, "bold"),
                      fg_color="transparent", hover_color="#E3E7EE", text_color=COR,
                      command=lambda: self.abas.set("Ajuda")).pack(side="left", padx=(4, 0))

    def mostrar_estado(self, q):
        e = self.app.estado[q]
        w = self.w[q]
        img = ICONES[q](e, tam=96)
        w["icone"].configure(image=self.ctk.CTkImage(light_image=img, dark_image=img, size=(44, 44)))
        cor = CINZA_UI if e is None else (VERDE_UI if e else VERMELHO_UI)
        w["status"].configure(text=texto_estado(q, e).capitalize(), text_color=cor)
        if e is None:
            w["botao"].configure(text="Indisponível", state="disabled")
        else:
            w["botao"].configure(text="Desligar" if e else "Ligar", state="normal",
                                 fg_color=VERMELHO_UI if e else VERDE_UI,
                                 hover_color=_misturar(VERMELHO_UI if e else VERDE_UI, (0, 0, 0), 0.2))
        if self.app.capturando != q:
            w["atalho"].configure(text=formatar_atalho(CFG["atalho_" + q]), text_color="#1E2530")

    def ocupado(self, q, sim):
        if sim:
            self.w[q]["botao"].configure(text="Aguarde...", state="disabled")
        else:
            self.mostrar_estado(q)

    def gravar_atalho(self, q):
        w = self.w[q]
        w["atalho"].configure(text="Pressione a nova combinação...  (Esc cancela)", text_color=COR)
        w["gravar"].configure(state="disabled")

        def trabalho():
            erro = self.app.capturar_atalho(q)

            def fim():
                w["gravar"].configure(state="normal")
                self.mostrar_estado(q)
                if erro:
                    w["atalho"].configure(text=erro, text_color=VERMELHO_UI)
                    self.root.after(3500, lambda: self.mostrar_estado(q))
            self.app.na_janela(fim)
        self.app.bg(trabalho)

    # ---------- aba Câmeras ----------
    def _aba_cameras(self, aba):
        ctk = self.ctk
        ctk.CTkLabel(aba, text="Escolha quais câmeras o atalho liga e desliga.",
                     font=self.F(14, "bold"), text_color="#1E2530").pack(anchor="w", padx=8, pady=(8, 0))
        ctk.CTkLabel(aba, text="Câmeras desmarcadas ficam sempre ligadas (por exemplo, a do celular).",
                     font=self.F(12), text_color="#6B7380").pack(anchor="w", padx=8, pady=(0, 6))
        self.lista_cams = ctk.CTkScrollableFrame(aba, fg_color="white", corner_radius=12,
                                                 border_width=1, border_color="#E1E5EC", height=260)
        self.lista_cams.pack(fill="both", expand=True, padx=6, pady=6)
        self._botao(aba, "Atualizar lista", self._atualizar_cams, largura=150, secundario=True).pack(
            anchor="e", padx=6, pady=(4, 6))
        self.mostrar_cameras()

    def _atualizar_cams(self):
        def trabalho():
            with self.app.trava["cam"]:
                self.app.atualizar("cam", self.app.verificar_cameras())
            self.app.na_janela(self.mostrar_cameras)
        self.app.bg(trabalho)

    def mostrar_cameras(self):
        ctk = self.ctk
        for filho in self.lista_cams.winfo_children():
            filho.destroy()
        if not self.app.cams:
            ctk.CTkLabel(self.lista_cams, text="Nenhuma câmera encontrada.", font=self.F(13),
                         text_color="#6B7380").pack(pady=20)
            return
        escolhidas = CFG.get("cameras")
        for c in self.app.cams:
            iid = c["InstanceId"]
            linha = ctk.CTkFrame(self.lista_cams, fg_color="transparent")
            linha.pack(fill="x", padx=8, pady=6)
            var = ctk.BooleanVar(value=(not escolhidas) or iid in escolhidas)
            ctk.CTkCheckBox(linha, text=c.get("FriendlyName") or iid, variable=var, font=self.F(13),
                            fg_color=COR, hover_color=COR_ESCURA, text_color="#1E2530",
                            command=lambda iid=iid, var=var: self.app.bg(self.app.escolher_camera, iid,
                                                                         var.get())
                            ).pack(side="left")
            ativa = c.get("Status") == "OK"
            ctk.CTkLabel(linha, text="ativa" if ativa else "desativada", font=self.F(12, "bold"),
                         text_color=VERDE_UI if ativa else VERMELHO_UI).pack(side="right")

    # ---------- aba Opções ----------
    def _aba_opcoes(self, aba):
        ctk = self.ctk
        c = self._cartao(aba)
        self.var_inicio = ctk.BooleanVar(value=False)
        self.sw_inicio = ctk.CTkSwitch(c, text="Iniciar junto com o Windows", variable=self.var_inicio,
                                       font=self.F(14), progress_color=COR, text_color="#1E2530",
                                       command=self._mudar_inicio)
        self.sw_inicio.pack(anchor="w", padx=16, pady=(16, 8))
        self.var_avisos = ctk.BooleanVar(value=bool(CFG.get("mostrar_avisos", True)))
        ctk.CTkSwitch(c, text="Mostrar aviso ao ligar ou desligar", variable=self.var_avisos,
                      font=self.F(14), progress_color=COR, text_color="#1E2530",
                      command=self._mudar_avisos).pack(anchor="w", padx=16, pady=(8, 16))

        c2 = self._cartao(aba)
        ctk.CTkLabel(c2, text="Algo não está funcionando?", font=self.F(14, "bold"),
                     text_color="#1E2530").pack(anchor="w", padx=16, pady=(14, 0))
        ctk.CTkLabel(c2, text="Libera o microfone e todas as câmeras de uma vez.", font=self.F(12),
                     text_color="#6B7380").pack(anchor="w", padx=16)
        botoes = ctk.CTkFrame(c2, fg_color="transparent")
        botoes.pack(fill="x", padx=16, pady=(8, 14))
        self._botao(botoes, "Liberar microfone e câmera", lambda: self.app.bg(self.app.restaurar_tudo),
                    largura=210).pack(side="left")
        self._botao(botoes, "Pasta de registros", lambda: os.startfile(PASTA_DADOS),
                    largura=150, secundario=True).pack(side="right")

    def _mudar_inicio(self):
        ativar = self.var_inicio.get()
        self.sw_inicio.configure(state="disabled")

        def trabalho():
            definir_inicializacao(ativar)
            ok = inicializacao_ativa()
            self.app.na_janela(lambda: (self.var_inicio.set(ok), self.sw_inicio.configure(state="normal")))
        self.app.bg(trabalho)

    def _mudar_avisos(self):
        CFG["mostrar_avisos"] = bool(self.var_avisos.get())
        salvar_config(CFG)

    def _ler_inicio(self):
        self.app.bg(lambda: (lambda ok: self.app.na_janela(lambda: self.var_inicio.set(ok)))(
            inicializacao_ativa()))

    # ---------- aba Ajuda ----------
    def _aba_ajuda(self, aba):
        ctk = self.ctk
        win11 = getattr(sys, "getwindowsversion", lambda: None)()
        win11 = bool(win11 and win11.build >= 22000)
        c = self._cartao(aba)
        ctk.CTkLabel(c, text="Deixe os ícones sempre à mostra", font=self.F(15, "bold"),
                     text_color="#1E2530").pack(anchor="w", padx=16, pady=(14, 0))
        ctk.CTkLabel(c, text="O Windows costuma esconder ícones novos na setinha  ^  ao lado do relógio.",
                     font=self.F(12), text_color="#6B7380").pack(anchor="w", padx=16)
        if win11:
            passos = ["Clique no botão abaixo para abrir as configurações da barra de tarefas.",
                      "Abra a seção \"Outros ícones da bandeja do sistema\".",
                      f"Ative as opções do {marca.PRODUTO} (microfone e câmera)."]
        else:
            passos = ["Clique no botão abaixo para abrir as configurações da barra de tarefas.",
                      "Em \"Área de notificação\", clique em \"Selecionar quais ícones aparecem na "
                      "barra de tarefas\".",
                      f"Ative as opções do {marca.PRODUTO} (microfone e câmera)."]
        for i, passo in enumerate(passos, 1):
            linha = ctk.CTkFrame(c, fg_color="transparent")
            linha.pack(fill="x", padx=16, pady=(8 if i == 1 else 4, 0))
            ctk.CTkLabel(linha, text=str(i), width=24, height=24, corner_radius=12, fg_color=COR,
                         text_color="white", font=self.F(12, "bold")).pack(side="left", anchor="n")
            ctk.CTkLabel(linha, text=passo, font=self.F(13), text_color="#1E2530", justify="left",
                         wraplength=400, anchor="w").pack(side="left", padx=(10, 0), fill="x")
        self._botao(c, "Abrir configurações da barra de tarefas", self._abrir_config_barra,
                    largura=300).pack(anchor="w", padx=16, pady=(12, 6))
        ctk.CTkLabel(c, text="Atalho: você também pode arrastar os ícones da setinha  ^  para a barra de tarefas.",
                     font=self.F(12), text_color="#6B7380", wraplength=460, justify="left").pack(
            anchor="w", padx=16, pady=(0, 14))

        c2 = self._cartao(aba)
        ctk.CTkLabel(c2, text="Como usar", font=self.F(15, "bold"), text_color="#1E2530").pack(
            anchor="w", padx=16, pady=(14, 4))
        for txt in ("Clique no ícone perto do relógio para ligar ou desligar.",
                    "Clique com o botão direito no ícone para abrir esta janela ou sair.",
                    "Use os atalhos de teclado da aba Controles em qualquer programa.",
                    "Verde = ligado · Vermelho = desligado · Cinza = não encontrado."):
            ctk.CTkLabel(c2, text="•  " + txt, font=self.F(13), text_color="#1E2530", anchor="w",
                         justify="left", wraplength=460).pack(anchor="w", padx=16, pady=1)
        ctk.CTkLabel(c2, text="", height=6).pack()

    def _abrir_config_barra(self):
        try:
            os.startfile("ms-settings:taskbar")
        except Exception as e:
            log(f"erro ao abrir configurações da barra: {e!r}")

    # ---------- aba Sobre ----------
    def _aba_sobre(self, aba):
        ctk = self.ctk
        logo = self._img_logo(96)
        if logo:
            ctk.CTkLabel(aba, image=logo, text="").pack(pady=(18, 6))
        ctk.CTkLabel(aba, text=marca.PRODUTO, font=self.F(20, "bold"), text_color="#1E2530").pack()
        ctk.CTkLabel(aba, text=f"Versão {marca.VERSAO}", font=self.F(13), text_color="#6B7380").pack()
        ctk.CTkLabel(aba, text=f"Desenvolvido por {marca.EMPRESA}", font=self.F(14),
                     text_color="#1E2530").pack(pady=(14, 8))
        links = ctk.CTkFrame(aba, fg_color="transparent")
        links.pack()
        self._botao(links, marca.SITE.replace("https://", ""), lambda: webbrowser.open(marca.SITE),
                    largura=180).pack(side="left", padx=6)
        self._botao(links, marca.EMAIL, lambda: webbrowser.open("mailto:" + marca.EMAIL),
                    largura=200, secundario=True).pack(side="left", padx=6)
        ctk.CTkLabel(aba, text=f"© {time.strftime('%Y')} {marca.EMPRESA}. Todos os direitos reservados.",
                     font=self.F(11), text_color="#8A919C").pack(side="bottom", pady=10)

    # ---------- ciclo ----------
    def _processar_fila(self):
        try:
            while True:
                self.app.fila.get_nowait()()
        except queue.Empty:
            pass
        except Exception as e:
            log(f"erro na janela: {e!r}")
        self.root.after(100, self._processar_fila)

    def mostrar(self, aba=None, tentativa=1):
        self._ler_inicio()
        if aba:
            self.abas.set(aba)
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(300, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()
        # confere se a janela realmente apareceu; se não, tenta de novo
        if tentativa < 3:
            self.root.after(700, lambda: None if self.root.state() == "normal"
                            else self.mostrar(aba, tentativa + 1))

    def esconder(self):
        self.root.withdraw()

    def loop(self):
        self.root.mainloop()


# ================================ Restaurar ===============================
def restaurar(silencioso=False):
    def passo(nome, func):
        try:
            func()
            msg = f"[OK]   {nome}"
        except Exception as e:
            msg = f"[ERRO] {nome}: {e}"
        log("restaurar: " + msg)
        if not silencioso:
            print(msg)

    passo("Microfone com som", lambda: definir_mic(True))
    passo("Privacidade da câmera liberada", liberar_privacidade_camera)
    passo("Câmeras ativadas",
          lambda: definir_cameras([c for c in listar_cameras() if c.get("Status") != "OK"], True))


# ================================= Início =================================
def main():
    if os.name != "nt":
        print("Este programa é só para Windows.")
        sys.exit(1)
    instalar_registro_de_erros()
    if not eh_admin():
        relancar_como_admin()
    args = sys.argv[1:]

    if "--restaurar" in args:
        restaurar(silencioso="--silencioso" in args)
        return
    if "--configurar-inicializacao" in args:
        i = args.index("--configurar-inicializacao")
        valor = args[i + 1].lower() if i + 1 < len(args) else "sim"
        definir_inicializacao(valor in ("sim", "1", "true", "yes"))
        log(f"inicialização configurada: {valor}")
        return

    if ja_esta_aberto():
        if "--tray" not in args:
            pedir_para_mostrar()
        return

    log(f"iniciando {marca.PRODUTO} {marca.VERSAO}")
    liberar_privacidade_camera()
    MeetGuard(mostrar_janela="--tray" not in args).rodar()


if __name__ == "__main__":
    main()
