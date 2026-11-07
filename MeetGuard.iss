; Instalador do Dirigível Meet Guard (Inno Setup 6)
; Gerado a partir de marca.py — rode construir_instalador.bat em vez de compilar direto.

#include "build\marca.iss"

[Setup]
AppId={{{#AppGuid}}
AppName={#Produto}
AppVersion={#Versao}
AppVerName={#Produto} {#Versao}
AppPublisher={#Empresa}
AppPublisherURL={#Site}
AppSupportURL={#Site}
AppUpdatesURL={#Site}
AppContact={#Email}
AppCopyright=© {#Empresa}
VersionInfoVersion={#Versao}
VersionInfoCompany={#Empresa}
VersionInfoProductName={#Produto}
VersionInfoDescription=Instalador do {#Produto}
DefaultDirName={autopf}\{#Empresa}\{#NomeCurto}
DisableProgramGroupPage=yes
DisableWelcomePage=no
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=instalador
OutputBaseFilename=Instalar-Dirigivel-Meet-Guard-{#Versao}
SetupIconFile=build\recursos\app.ico
UninstallDisplayIcon={app}\{#Exe}.exe
UninstallDisplayName={#Produto}
WizardStyle=modern
WizardImageFile=build\recursos\wizard_grande.bmp,build\recursos\wizard_grande_2x.bmp
WizardSmallImageFile=build\recursos\wizard_pequeno.bmp,build\recursos\wizard_pequeno_2x.bmp
Compression=lzma2/max
SolidCompression=yes
CloseApplications=force
RestartApplications=no

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Messages]
ptbr.WelcomeLabel2=Este assistente vai instalar o [name/ver] no seu computador.%n%nCom ele você liga e desliga o microfone e a câmera com um atalho de teclado e vê o estado de cada um perto do relógio.%n%nFeche seus aplicativos de reunião antes de continuar.

[Tasks]
Name: "iniciar"; Description: "Iniciar o {#NomeCurto} junto com o Windows (recomendado)"; GroupDescription: "Opções:"
Name: "areatrabalho"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Opções:"; Flags: unchecked

[Files]
Source: "dist\{#Exe}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#Produto}"; Filename: "{app}\{#Exe}.exe"
Name: "{autodesktop}\{#Produto}"; Filename: "{app}\{#Exe}.exe"; Tasks: areatrabalho

[Run]
; remove o antigo MicCam, se existir
Filename: "{sys}\taskkill.exe"; Parameters: "/im MicCam.exe /f"; Flags: runhidden; StatusMsg: "Removendo versões antigas..."
Filename: "{sys}\schtasks.exe"; Parameters: "/delete /tn ""MicCam"" /f"; Flags: runhidden
; iniciar com o Windows
Filename: "{app}\{#Exe}.exe"; Parameters: "--configurar-inicializacao sim"; Flags: runhidden waituntilterminated; Tasks: iniciar; StatusMsg: "Configurando a inicialização..."
Filename: "{app}\{#Exe}.exe"; Parameters: "--configurar-inicializacao nao"; Flags: runhidden waituntilterminated; Tasks: not iniciar
; abrir ao terminar
Filename: "{app}\{#Exe}.exe"; Description: "Abrir o {#Produto} agora"; Flags: nowait postinstall skipifsilent runascurrentuser

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/im {#Exe}.exe /f"; Flags: runhidden; RunOnceId: "Fechar"
Filename: "{app}\{#Exe}.exe"; Parameters: "--restaurar --silencioso"; Flags: runhidden waituntilterminated; RunOnceId: "Restaurar"
Filename: "{sys}\schtasks.exe"; Parameters: "/delete /tn ""{#NomeTarefa}"" /f"; Flags: runhidden; RunOnceId: "Inicializacao"

[Code]
// Fecha o Meet Guard aberto antes de atualizar os arquivos
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Codigo: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/im {#Exe}.exe /f', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  Result := '';
end;
