# -*- coding: utf-8 -*-
"""
Gera os arquivos visuais a partir de marca.py (e de logo.png, se existir):
  build/recursos/app.ico            ícone do programa e do instalador
  build/recursos/logo.png           logo usada na janela
  build/recursos/wizard_*.bmp       imagens do assistente de instalação
  build/marca.iss                   dados da marca para o Inno Setup
  build/versao.txt                  informações de versão do .exe
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import marca  # noqa: E402

BUILD = os.path.join(AQUI, "build")
REC = os.path.join(BUILD, "recursos")


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def misturar(c1, c2, t):
    return tuple(round(a + (b - a) * t) for a, b in zip(c1, c2))


COR = hex_rgb(marca.COR_PRINCIPAL)
ESCURA = misturar(COR, (0, 0, 0), 0.45)
CLARA = misturar(COR, (255, 255, 255), 0.25)
BRANCO = (255, 255, 255)


def gradiente(w, h, c1, c2):
    img = Image.new("RGB", (w, h), c1)
    d = ImageDraw.Draw(img)
    for y in range(h):
        d.line((0, y, w, y), fill=misturar(c1, c2, y / max(1, h - 1)))
    return img


def logo_padrao(S=1024):
    """Escudo com uma câmera: proteção nas reuniões."""
    fundo = gradiente(S, S, CLARA, ESCURA).convert("RGBA")
    mascara = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mascara).rounded_rectangle((0, 0, S - 1, S - 1), radius=S // 4.5, fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(fundo, (0, 0), mascara)
    d = ImageDraw.Draw(img)

    # escudo
    cx, top, bot, w = S / 2, S * 0.17, S * 0.86, S * 0.62
    escudo = [
        (cx - w / 2, top + S * 0.07), (cx, top), (cx + w / 2, top + S * 0.07),
        (cx + w / 2, top + S * 0.36),
    ]
    # lados descem retos e curvam suavemente até a ponta (Bézier quadrática)
    def bezier(p0, p1, p2, n=24):
        return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0],
                 (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1])
                for t in (i / n for i in range(1, n + 1))]
    meio = top + S * 0.36
    escudo += bezier((cx + w / 2, meio), (cx + w / 2, bot - S * 0.14), (cx, bot))
    escudo += bezier((cx, bot), (cx - w / 2, bot - S * 0.14), (cx - w / 2, meio))[:-1]
    escudo.append((cx - w / 2, top + S * 0.36))
    d.polygon(escudo, fill=BRANCO)

    # câmera dentro do escudo
    cy = S * 0.47
    d.rounded_rectangle((cx - S * 0.17, cy - S * 0.085, cx + S * 0.07, cy + S * 0.085),
                        radius=S * 0.03, fill=COR)
    d.polygon([(cx + S * 0.085, cy), (cx + S * 0.17, cy - S * 0.07), (cx + S * 0.17, cy + S * 0.07)],
              fill=COR)
    # risco (privacidade)
    d.line((cx - S * 0.2, cy + S * 0.17, cx + S * 0.2, cy - S * 0.17), fill=BRANCO, width=int(S * 0.07))
    d.line((cx - S * 0.2, cy + S * 0.17, cx + S * 0.2, cy - S * 0.17), fill=COR, width=int(S * 0.035))
    return img


def carregar_logo():
    caminho = os.path.join(AQUI, "logo.png")
    if os.path.exists(caminho):
        src = Image.open(caminho).convert("RGBA")
        lado = max(src.size)
        quad = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
        quad.paste(src, ((lado - src.width) // 2, (lado - src.height) // 2), src)
        print("Usando logo.png da empresa.")
        return quad.resize((1024, 1024), Image.LANCZOS)
    print("logo.png não encontrado: usando ícone padrão.")
    return logo_padrao()


def fonte(tam, negrito=False):
    nomes = ["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"] if negrito else \
            ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"]
    for n in nomes:
        for base in ("", os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"),
                     "/usr/share/fonts/truetype/dejavu"):
            try:
                return ImageFont.truetype(os.path.join(base, n) if base else n, tam)
            except OSError:
                continue
    return ImageFont.load_default()


def texto_centro(d, cx, y, txt, f, cor):
    w = d.textlength(txt, font=f)
    d.text((cx - w / 2, y), txt, font=f, fill=cor)


def imagem_wizard(w, h, logo):
    img = gradiente(w, h, COR, ESCURA)
    d = ImageDraw.Draw(img)
    lado = int(w * 0.55)
    lg = logo.resize((lado, lado), Image.LANCZOS)
    img.paste(lg, ((w - lado) // 2, int(h * 0.18)), lg)
    y = int(h * 0.18) + lado + int(h * 0.05)
    texto_centro(d, w / 2, y, marca.NOME_CURTO, fonte(int(w * 0.13), True), BRANCO)
    texto_centro(d, w / 2, y + int(w * 0.17), f"por {marca.EMPRESA}", fonte(int(w * 0.075)),
                 misturar(BRANCO, COR, 0.25))
    return img


def main():
    os.makedirs(REC, exist_ok=True)
    logo = carregar_logo()

    logo.resize((512, 512), Image.LANCZOS).save(os.path.join(REC, "logo.png"))
    logo.resize((256, 256), Image.LANCZOS).save(
        os.path.join(REC, "app.ico"),
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    # assistente de instalação (100% e 200% de escala)
    for sufixo, (w, h) in (("", (164, 314)), ("_2x", (328, 628))):
        imagem_wizard(w, h, logo).save(os.path.join(REC, f"wizard_grande{sufixo}.bmp"))
    for sufixo, lado in (("", 55), ("_2x", 110)):
        peq = Image.new("RGB", (lado, lado), BRANCO)
        lg = logo.resize((lado, lado), Image.LANCZOS)
        peq.paste(lg, (0, 0), lg)
        peq.save(os.path.join(REC, f"wizard_pequeno{sufixo}.bmp"))

    # dados para o Inno Setup (UTF-8 com BOM para aceitar acentos)
    with open(os.path.join(BUILD, "marca.iss"), "w", encoding="utf-8-sig") as f:
        f.write(f'#define Empresa "{marca.EMPRESA}"\n')
        f.write(f'#define Produto "{marca.PRODUTO}"\n')
        f.write(f'#define NomeCurto "{marca.NOME_CURTO}"\n')
        f.write(f'#define Versao "{marca.VERSAO}"\n')
        f.write(f'#define Site "{marca.SITE}"\n')
        f.write(f'#define Email "{marca.EMAIL}"\n')
        f.write(f'#define Exe "{marca.EXE}"\n')
        f.write(f'#define NomeTarefa "{marca.NOME_TAREFA}"\n')
        f.write(f'#define AppGuid "{marca.APP_GUID}"\n')

    # informações de versão do .exe (aparecem em Propriedades > Detalhes)
    v = [int(x) for x in (marca.VERSAO.split(".") + ["0", "0", "0"])[:4]]
    with open(os.path.join(BUILD, "versao.txt"), "w", encoding="utf-8") as f:
        f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={tuple(v)}, prodvers={tuple(v)}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041604B0', [
      StringStruct('CompanyName', {marca.EMPRESA!r}),
      StringStruct('FileDescription', {marca.PRODUTO!r}),
      StringStruct('FileVersion', {marca.VERSAO!r}),
      StringStruct('InternalName', {marca.EXE!r}),
      StringStruct('LegalCopyright', '© {marca.EMPRESA}'),
      StringStruct('OriginalFilename', '{marca.EXE}.exe'),
      StringStruct('ProductName', {marca.PRODUTO!r}),
      StringStruct('ProductVersion', {marca.VERSAO!r})])]),
    VarFileInfo([VarStruct('Translation', [0x0416, 1200])])
  ]
)
""")
    print("Recursos gerados em", REC)


if __name__ == "__main__":
    main()
