"""
Utilitário de geração de Rank Cards e Árvore de Progressão de Cargos usando Pillow.
Desenha imagens dinâmicas de altíssima qualidade com Mesh Gradients,
efeito Glassmorphism (vidro fosco) e fontes embutidas com suporte completo a acentos.
"""

from __future__ import annotations

import io
import os
import aiohttp
from PIL import Image, ImageDraw, ImageFilter, ImageFont

def get_contrast_accent(accent: tuple[int, int, int], bg: tuple[int, int, int]) -> tuple[int, int, int]:
    """Retorna o accent diretamente sem alteração para manter a fidelidade da cor principal (ex: #820909)."""
    return accent

def resize_and_crop(img: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    """Redimensiona e corta uma imagem mantendo a proporção para caber no target_size."""
    target_w, target_h = target_size
    img_w, img_h = img.size
    
    # Razão de aspecto
    aspect_target = target_w / target_h
    aspect_img = img_w / img_h
    
    if aspect_img > aspect_target:
        # Imagem é mais larga que o target, ajusta a altura
        new_h = target_h
        new_w = int(img_w * (target_h / img_h))
        img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        # Corta as laterais
        left = (new_w - target_w) // 2
        return img_resized.crop((left, 0, left + target_w, target_h))
    else:
        # Imagem é mais alta, ajusta a largura
        new_w = target_w
        new_h = int(img_h * (target_w / img_w))
        img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        # Corta o topo/base
        top = (new_h - target_h) // 2
        return img_resized.crop((0, top, target_w, top + target_h))

# Configuração de temas modernos para os cards de perfil e rank
THEMES = {
    "default": {
        "bg_dark": (15, 17, 21),
        "accent": (130, 9, 9),       # #820909 (Crimson Padrão)
        "text_main": (255, 255, 255),
        "text_sub": (160, 165, 172),
    },
    "discord": {
        "bg_dark": (43, 45, 49),      # #2B2D31 (Discord Dark)
        "accent": (88, 101, 242),    # #5865F2 (Discord Blurple)
        "text_main": (255, 255, 255),
        "text_sub": (148, 155, 164),  # #949BA4 (Discord Subtext)
    },
    "nature": {
        "bg_dark": (10, 20, 15),     # #0A140F (Dark Forest)
        "accent": (143, 172, 147),   # #8FAC93 (Sage Green)
        "text_main": (255, 255, 255),
        "text_sub": (178, 194, 181),
    },
    "ocean": {
        "bg_dark": (8, 14, 24),      # #080E18 (Dark Navy)
        "accent": (120, 165, 195),   # #78A5C3 (Pastel Sea Blue)
        "text_main": (255, 255, 255),
        "text_sub": (170, 188, 199),
    },
    "amethyst": {
        "bg_dark": (14, 10, 22),     # #0E0A16 (Dark Purple)
        "accent": (175, 150, 215),   # #AF96D7 (Pastel Lavender)
        "text_main": (255, 255, 255),
        "text_sub": (205, 195, 220),
    },
    "autumn": {
        "bg_dark": (22, 13, 8),      # #160D08 (Dark Amber)
        "accent": (225, 160, 110),   # #E1A06E (Pastel Autumn Orange)
        "text_main": (255, 255, 255),
        "text_sub": (220, 200, 185),
    },
}

BACKGROUNDS = {
    "fern": {
        "name": "Fern",
        "price": 5000,
        "bg_image": "src/assets/Image/Profiles/background/Fern.png",
        "accent": (240, 240, 245),
    },
    "galaxy": {
        "name": "Galaxy",
        "price": 5000,
        "bg_image": "src/assets/Image/Profiles/background/Galaxy.jpg",
        "accent": (240, 240, 245),
    },
    "hutao": {
        "name": "Hu Tao",
        "price": 5000,
        "bg_image": "src/assets/Image/Profiles/background/HuTao.jpg",
        "accent": (240, 240, 245),
    },
    "kasaneteto": {
        "name": "Kasane Teto",
        "price": 5000,
        "bg_image": "src/assets/Image/Profiles/background/Kasane_Teto.png",
        "accent": (240, 240, 245),
    },
    "luckystar": {
        "name": "Lucky Star",
        "price": 5000,
        "bg_image": "src/assets/Image/Profiles/background/LuckyStar.png",
        "accent": (240, 240, 245),
    },
    "mikuteto": {
        "name": "Miku & Teto",
        "price": 5000,
        "bg_image": "src/assets/Image/Profiles/background/Miku_Teto.png",
        "accent": (240, 240, 245),
    },
    "robin": {
        "name": "Robin",
        "price": 5000,
        "bg_image": "src/assets/Image/Profiles/background/Robin.jpg",
        "accent": (240, 240, 245),
    },
    "windowsxp": {
        "name": "Windows XP",
        "price": 5000,
        "bg_image": "src/assets/Image/Profiles/background/Windows_XP.jpg",
        "accent": (240, 240, 245),
    },
    "agnestachyon": {
        "name": "Agnes Tachyon",
        "price": 25000,
        "bg_image": "src/assets/Image/Profiles/background/Agnes_Tachyon.gif",
        "accent": (240, 240, 245),
    },
}



def get_font(size: int, bold: bool = False) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Carrega a fonte DejaVu Sans embutida ou recorre a fontes do sistema/Pillow."""
    # 1. Preferência principal: DejaVu Sans (cobertura total de símbolos unicode como ✦, ✧, ▸, acentos e emojis)
    dejavu_path = (
        "src/assets/fonts/DejaVuSans-Bold.ttf"
        if bold
        else "src/assets/fonts/DejaVuSans.ttf"
    )
    if os.path.exists(dejavu_path):
        try:
            return ImageFont.truetype(dejavu_path, size)
        except OSError:
            pass

    # 2. Fallbacks do sistema caso as fontes locais falhem
    font_names = (
        ["segoeuib.ttf", "arialbd.ttf", "LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf"]
        if bold
        else ["segoeui.ttf", "arial.ttf", "LiberationSans-Regular.ttf", "DejaVuSans.ttf"]
    )
    for name in font_names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def get_glow_mask(diameter: int) -> Image.Image:
    """Gera um mapa de transparência circular com decaimento suave (fade-out quadrático)."""
    # Usar uma textura menor para desenhar o gradiente radial e escalá-la (super rápido e suave)
    tex_size = 128
    mask = Image.new("L", (tex_size, tex_size), 0)
    draw = ImageDraw.Draw(mask)
    for r in range(tex_size // 2, 0, -1):
        t = r / (tex_size // 2)
        alpha = int(255 * (1 - t ** 2))
        draw.ellipse((tex_size // 2 - r, tex_size // 2 - r, tex_size // 2 + r, tex_size // 2 + r), fill=alpha)
    return mask.resize((diameter, diameter), Image.Resampling.LANCZOS)


def draw_glow(canvas: Image.Image, center: tuple[int, int], radius: int, color: tuple[int, int, int], max_alpha: int) -> None:
    """Desenha uma esfera brilhante de cor (Glow radial) no canvas."""
    diameter = radius * 2
    mask = get_glow_mask(diameter)
    
    # Aplica o limite máximo de opacidade
    if max_alpha < 255:
        mask = mask.point(lambda p: int(p * (max_alpha / 255.0)))
        
    glow_layer = Image.new("RGBA", (diameter, diameter), color + (255,))
    cx, cy = center
    canvas.paste(glow_layer, (cx - radius, cy - radius), mask=mask)


async def fetch_avatar_image(avatar_url: str) -> Image.Image | None:
    """Busca a imagem do avatar de forma assíncrona."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(avatar_url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    return Image.open(io.BytesIO(data))
    except Exception:
        pass
    return None


def process_avatar(avatar_img: Image.Image, size: int) -> Image.Image:
    """Redimensiona e corta o avatar no formato circular com transparência."""
    avatar_img = avatar_img.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)

    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.paste(avatar_img, (0, 0), mask=mask)
    return output


async def generate_rank_card(
    username: str,
    level: int,
    xp_current: int,
    xp_needed: int,
    rank: int,
    avatar_url: str,
    theme_name: str = "default",
) -> io.BytesIO:
    """Gera o Rank Card do usuário com visual Mesh Gradient e Glassmorphism."""
    has_bg = theme_name in BACKGROUNDS
    if has_bg:
        bg_theme = BACKGROUNDS[theme_name]
        theme: dict = {
            "bg_dark": (18, 20, 26),
            "bg_image": bg_theme["bg_image"],
            "accent": bg_theme["accent"],
            "text_main": (255, 255, 255),
            "text_sub": (200, 205, 212),
        }
    else:
        theme = THEMES.get(theme_name, THEMES["default"])
    accent_color = get_contrast_accent(theme["accent"], (24, 26, 32))

    W, H = 900, 250

    # ── 1. Canvas base & detecção de GIF animado ──────────────────────────────
    is_animated = False
    bg_img = None
    if has_bg:
        try:
            bg_path = os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__), "..", "..", "..", "..", theme["bg_image"]
                )
            )
            if os.path.exists(bg_path):
                bg_img = Image.open(bg_path)
                is_animated = getattr(bg_img, "is_animated", False) and bg_img.n_frames > 1
                if not is_animated:
                    # Converte para RGBA e cria o card estático
                    bg_img_rgba = bg_img.convert("RGBA")
                    card = Image.new("RGBA", (W, H))
                    bg_resized = resize_and_crop(bg_img_rgba, (W, H))
                    card.paste(bg_resized, (0, 0))
            else:
                card = Image.new("RGBA", (W, H), theme["bg_dark"] + (255,))
                has_bg = False
        except Exception:
            card = Image.new("RGBA", (W, H), theme["bg_dark"] + (255,))
            has_bg = False
    else:
        card = Image.new("RGBA", (W, H), theme["bg_dark"] + (255,))
        # Mesh gradient glows para profundidade visual nos temas de cor
        draw_glow(card, (0, 0), 250, accent_color, max_alpha=55)
        draw_glow(card, (W, H), 250, (35, 38, 48), max_alpha=80)
    
    # ── 2. Configuração visual do painel ─────────────────────────────────────
    if has_bg:
        panel_fill: tuple = (10, 11, 14, 155)
        panel_outline: tuple = (255, 255, 255, 35)
    else:
        panel_fill = (24, 26, 32, 255)
        panel_outline = (70, 74, 82, 255)

    BLUR = 0 if is_animated else 9

    # ── 3. Desenhar painéis de vidro e definir drawing canvas ────────────────
    if not is_animated:
        draw_glass_panel(
            card, (20, 20, 880, 230),
            blur_radius=BLUR, fill_rgba=panel_fill, outline_rgba=panel_outline,
            corner_radius=16, has_bg_image=has_bg
        )
        drawing_canvas = card
    else:
        # Camada transparente para receber o overlay de textos, avatar e progresso
        drawing_canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # 3. Avatar do membro
    avatar_size = 130
    avatar_x, avatar_y = 50, 60
    avatar = await fetch_avatar_image(avatar_url)

    if has_bg:
        # Double ring
        outer_ring = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        outer_draw = ImageDraw.Draw(outer_ring)
        outer_draw.ellipse(
            (avatar_x - 5, avatar_y - 5, avatar_x + avatar_size + 5, avatar_y + avatar_size + 5),
            outline=accent_color + (110,), width=4,
        )
        drawing_canvas.alpha_composite(outer_ring)

        inner_ring = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        inner_draw = ImageDraw.Draw(inner_ring)
        inner_draw.ellipse(
            (avatar_x - 2, avatar_y - 2, avatar_x + avatar_size + 2, avatar_y + avatar_size + 2),
            outline=accent_color + (255,), width=3,
        )
        drawing_canvas.alpha_composite(inner_ring)
    else:
        # Anel sólido simples para temas de cor
        ring_draw = ImageDraw.Draw(drawing_canvas)
        ring_draw.ellipse(
            (avatar_x - 2, avatar_y - 2, avatar_x + avatar_size + 2, avatar_y + avatar_size + 2),
            outline=accent_color, width=3,
        )

    if avatar:
        circular_avatar = process_avatar(avatar, avatar_size)
        drawing_canvas.paste(circular_avatar, (avatar_x, avatar_y), circular_avatar)
    else:
        # Placeholder se o download falhar
        placeholder_draw = ImageDraw.Draw(drawing_canvas)
        placeholder_draw.ellipse(
            (avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size),
            fill=accent_color,
        )

    # 5. Carregar Fontes Premium Embutidas (Inter)
    font_name = get_font(34, bold=True)
    font_sub = get_font(18, bold=False)
    font_bold_sm = get_font(22, bold=True)
    font_level = get_font(32, bold=True)

    # Criar draw object após operações de composição
    draw = ImageDraw.Draw(drawing_canvas)

    # 6. Desenhar textos (Username e Stats)
    rank_text = f"RANK #{rank}" if rank > 0 else "RANK #-"
    level_text = f"NÍVEL {level}"

    # Medir largura do nível e do rank para alinhamento dinâmico
    try:
        level_w = draw.textlength(level_text, font=font_level)
    except AttributeError:
        level_w, _ = font_level.getsize(level_text)

    try:
        rank_w = draw.textlength(rank_text, font=font_bold_sm)
    except AttributeError:
        rank_w, _ = font_bold_sm.getsize(rank_text)

    # Alinha o nível à direita (limite 845)
    level_x = 845 - level_w
    # Alinha o rank à esquerda do nível com espaçamento de 25px
    rank_x = level_x - rank_w - 25

    # Desenhar Nível e Rank
    draw.text((level_x, 50), level_text, fill=accent_color, font=font_level)
    draw.text((rank_x, 58), rank_text, fill=theme["text_sub"], font=font_bold_sm)

    # Truncar dinamicamente o username com base no espaço restante
    max_username_w = rank_x - 205 - 15
    display_username = username
    try:
        username_w = draw.textlength(display_username, font=font_name)
    except AttributeError:
        username_w, _ = font_name.getsize(display_username)

    while username_w > max_username_w and len(display_username) > 3:
        display_username = display_username[:-1]
        try:
            username_w = draw.textlength(display_username + "...", font=font_name)
        except AttributeError:
            username_w, _ = font_name.getsize(display_username + "...")

    if len(display_username) < len(username):
        display_username += "..."

    draw.text((205, 50), display_username, fill=theme["text_main"], font=font_name)

    # 7. Desenhar barra de progresso (com fundo)
    bar_x = 205
    bar_y = 130
    bar_w = 645
    bar_h = 18

    # Fundo da barra
    try:
        draw.rounded_rectangle(
            (bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), radius=9, fill=(38, 41, 50, 255)
        )
    except AttributeError:
        draw.rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), fill=(38, 41, 50, 255))

    # Progresso preenchido
    progress_pct = (xp_current / xp_needed) if xp_needed > 0 else 1.0
    progress_pct = min(max(progress_pct, 0.0), 1.0)
    fill_w = int(bar_w * progress_pct)

    if fill_w > 0:
        fill_w = max(fill_w, 18)  # mantém cantos arredondados
        try:
            draw.rounded_rectangle(
                (bar_x, bar_y, bar_x + fill_w, bar_y + bar_h), radius=9, fill=accent_color
            )
        except AttributeError:
            draw.rectangle((bar_x, bar_y, bar_x + fill_w, bar_y + bar_h), fill=accent_color)

    # 8. Detalhes numéricos da barra
    xp_text = f"{xp_current:,} / {xp_needed:,} XP".replace(",", ".")
    pct_text = f"{int(progress_pct * 100)}%"

    # Alinha a porcentagem à direita (limite 845)
    try:
        pct_w = draw.textlength(pct_text, font=font_bold_sm)
    except AttributeError:
        pct_w, _ = font_bold_sm.getsize(pct_text)
    pct_x = 845 - pct_w

    draw.text((bar_x, bar_y + 32), xp_text, fill=theme["text_sub"], font=font_sub)
    draw.text((pct_x, bar_y + 32), pct_text, fill=accent_color, font=font_bold_sm)

    # ── 9. Composição final e retorno do buffer ──────────────────────────────
    if is_animated and bg_img:
        # 1. Definição do skip de frames inteligente (limite de 24 frames para excelente fluidez)
        total_frames = bg_img.n_frames
        max_target_frames = 24
        step = max(1, total_frames // max_target_frames)
        
        # Obter paleta global do frame 0
        bg_img.seek(0)
        global_palette = bg_img.getpalette()
        if global_palette is None:
            global_palette = [i for i in range(256) for _ in range(3)]
        
        frames = []
        durations = []
        
        # 2. Processar frames selecionados
        for i in range(0, total_frames, step):
            bg_img.seek(i)
            
            # Guardar frame original do GIF no modo P
            orig_frame_p = bg_img.copy()
            
            # Redimensionar frame original usando NEAREST para preservar paleta
            orig_resized_p = orig_frame_p.resize((W, H), Image.Resampling.NEAREST)
            if orig_resized_p.mode != "P":
                orig_resized_p = orig_resized_p.convert("P")
            orig_resized_p.putpalette(global_palette)
            
            # Composição em RGBA
            frame_rgba = resize_and_crop(bg_img.convert("RGBA"), (W, H))
            
            frame_card = Image.new("RGBA", (W, H))
            frame_card.paste(frame_rgba, (0, 0))
            
            # Painel de vidro
            draw_glass_panel(
                frame_card, (20, 20, 880, 230),
                blur_radius=BLUR, fill_rgba=panel_fill, outline_rgba=panel_outline,
                corner_radius=16, has_bg_image=True,
            )
            
            # Compor com o overlay estático transparente
            frame_card.alpha_composite(drawing_canvas)
            
            # Converter para RGB antes de quantizar
            rgb_frame = frame_card.convert("RGB")
            
            # Quantizar usando o frame original no modo P como paleta (qualidade 100% de fábrica!)
            p_frame = rgb_frame.quantize(palette=orig_resized_p, dither=Image.Dither.NONE)
            frames.append(p_frame)
            
            # Velocidade corrigida: duração original multiplicada pelo passo (step)
            orig_dur = bg_img.info.get('duration', 100)
            durations.append(max(50, orig_dur * step))
            
        fp = io.BytesIO()
        # Salva como GIF animado de alta fidelidade e velocidade perfeita
        frames[0].save(
            fp, format="GIF", save_all=True, append_images=frames[1:], 
            loop=0, duration=durations, optimize=True
        )
        fp.seek(0)
        return fp
    else:
        fp = io.BytesIO()
        card.save(fp, format="PNG")
        fp.seek(0)
        return fp




def generate_ranks_tree(
    guild_name: str,
    roles_list: list[dict],
    user_name: str,
    user_level: int,
) -> io.BytesIO:
    """Gera a árvore de cargos do servidor com visual moderno Mesh Gradient e Glassmorphism."""
    theme = THEMES["default"]
    accent_color = get_contrast_accent(theme["accent"], (20, 22, 27))
    width = 900
    num_roles = len(roles_list)

    if num_roles == 0:
        height = 250
    else:
        height = 180 + 100 * num_roles

    # 1. Canvas base
    canvas = Image.new("RGBA", (width, height), theme["bg_dark"] + (255,))

    draw = ImageDraw.Draw(canvas)

    # 2. Fonte Premium
    font_title = get_font(30, bold=True)
    font_subtitle = get_font(18, bold=False)
    font_bold = get_font(24, bold=True)
    font_regular = get_font(22, bold=False)
    font_tag = get_font(14, bold=True)

    # 3. Cabeçalho estilizado (visual plano com ilusão de vidro)
    try:
        draw.rounded_rectangle(
            (25, 20, 875, 110),
            radius=12,
            fill=(24, 26, 32, 255),
            outline=(70, 74, 82, 255),
            width=1,
        )
    except AttributeError:
        draw.rectangle(
            (25, 20, 875, 110),
            fill=(24, 26, 32, 255),
            outline=(70, 74, 82, 255),
        )

    draw.text((45, 30), f"Trilha de Cargos — {guild_name}", fill=theme["text_main"], font=font_title)
    draw.text(
        (45, 72),
        f"Progresso de {user_name} • Nível {user_level}",
        fill=theme["text_sub"],
        font=font_subtitle,
    )

    if num_roles == 0:
        draw.text(
            (45, 160),
            "Nenhum cargo por nível configurado neste servidor.",
            fill=theme["text_sub"],
            font=font_subtitle,
        )
    else:
        line_x = 100
        start_y = 175
        end_y = start_y + 100 * (num_roles - 1)

        # Desenhar linha cinza da linha do tempo
        if num_roles > 1:
            draw.line((line_x, start_y, line_x, end_y), fill=(255, 255, 255, 20), width=6)

        for idx, r in enumerate(roles_list):
            node_y = start_y + 100 * idx

            # tag_text_color padrão (branco)
            tag_text_color = (255, 255, 255)

            # Definir cores de acordo com o progresso do usuário
            if r["is_current"]:
                fill_color = (251, 191, 36)  # Ouro
                border_color = (255, 255, 255)
                tag_text = "ATUAL"
                tag_bg = (251, 191, 36)
                text_color = (251, 191, 36)
                # Ouro é muito claro, então texto escuro para contraste
                tag_text_color = (15, 17, 21)
            elif r["is_unlocked"]:
                fill_color = accent_color
                border_color = accent_color
                tag_text = "DESBLOQUEADO"
                tag_bg = accent_color
                text_color = theme["text_main"]
                # Se o accent for muito claro, usa texto escuro para contraste
                brightness = 0.299 * accent_color[0] + 0.587 * accent_color[1] + 0.114 * accent_color[2]
                if brightness > 130:
                    tag_text_color = (15, 17, 21)
            else:
                fill_color = (75, 85, 99)  # Cinza
                border_color = (55, 65, 81)
                tag_text = "BLOQUEADO"
                tag_bg = (55, 65, 81)
                text_color = theme["text_sub"]

            # Pintar o caminho conectivo com o accent do tema se já foi desbloqueado
            if idx > 0 and r["is_unlocked"] and roles_list[idx - 1]["is_unlocked"]:
                prev_y = start_y + 100 * (idx - 1)
                draw.line((line_x, prev_y, line_x, node_y), fill=accent_color, width=6)

            # Efeito de painel plano (ilusão de vidro) para cada nó de nível
            try:
                draw.rounded_rectangle(
                    (150, node_y - 35, 875, node_y + 35),
                    radius=10,
                    fill=(20, 22, 27, 255),
                    outline=(60, 64, 72, 255),
                    width=1,
                )
            except AttributeError:
                draw.rectangle(
                    (150, node_y - 35, 875, node_y + 35),
                    fill=(20, 22, 27, 255),
                    outline=(60, 64, 72, 255),
                )

            # Nó circular da linha do tempo
            radius = 16
            draw.ellipse(
                (line_x - radius, node_y - radius, line_x + radius, node_y + radius),
                fill=fill_color,
                outline=border_color,
                width=3,
            )

            # Informações textuais do cargo
            draw.text((175, node_y - 20), f"Nível {r['level']}", fill=text_color, font=font_bold)
            draw.text((175, node_y + 6), f"@{r['role_name']}", fill=theme["text_sub"], font=font_regular)

            # Badge com status do nível
            tag_w = 140
            tag_h = 24
            tag_x = 705
            tag_y = node_y - 12

            try:
                draw.rounded_rectangle((tag_x, tag_y, tag_x + tag_w, tag_y + tag_h), radius=6, fill=tag_bg)
            except AttributeError:
                draw.rectangle((tag_x, tag_y, tag_x + tag_w, tag_y + tag_h), fill=tag_bg)

            # Centralizar levemente o texto na badge
            draw.text((tag_x + 12, tag_y + 3), tag_text, fill=tag_text_color, font=font_tag)

    fp = io.BytesIO()
    canvas.save(fp, format="PNG")
    fp.seek(0)
    return fp


def draw_top_rounded_banner(img: Image.Image, radius: int) -> Image.Image:
    """Retorna o banner com apenas os cantos superiores arredondados."""
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, img.width, img.height + radius), radius=radius, fill=255)
    
    output = Image.new("RGBA", img.size, (0, 0, 0, 0))
    output.paste(img, (0, 0), mask=mask)
    return output


def paste_emoji_icon(
    canvas: Image.Image,
    emoji_name: str,
    position: tuple[int, int] | tuple[float, float],
    size: tuple[int, int] = (24, 24)
) -> bool:
    """Carrega um ícone de emoji PNG local e cola no canvas com transparência."""
    try:
        icon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "assets", "Image", "Icons", f"{emoji_name}.png"))
        if os.path.exists(icon_path):
            icon_img = Image.open(icon_path).convert("RGBA")
            icon_img = icon_img.resize(size, Image.Resampling.LANCZOS)
            # Converte a posição para inteiros para evitar erros com floats no Pillow
            int_pos = (int(position[0]), int(position[1]))
            canvas.paste(icon_img, int_pos, mask=icon_img)
            return True
    except Exception:
        pass
    return False


def draw_icon_or_text_emoji(
    canvas: Image.Image,
    draw: ImageDraw.Draw,
    emoji_name: str,
    unicode_fallback: str,
    position: tuple[int, int],
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    text_color: tuple[int, int, int],
    icon_size: int = 24
) -> int:
    """Tenta desenhar o ícone de emoji PNG local. Se falhar, desenha o unicode_fallback como texto.
    
    Retorna a largura consumida (ou espaço reservado) para o emoji/ícone para podermos alinhar o texto adjacente.
    """
    x, y = position
    if paste_emoji_icon(canvas, emoji_name, (x, y - 2), size=(icon_size, icon_size)):
        return icon_size + 8  # Retorna a largura do ícone + espaçamento
    else:
        draw.text(position, unicode_fallback, fill=text_color, font=font)
        try:
            w = draw.textlength(unicode_fallback, font=font)
        except AttributeError:
            w, _ = font.getsize(unicode_fallback)
        return int(w) + 8


def draw_glass_panel(
    canvas: Image.Image,
    region: tuple[int, int, int, int],
    blur_radius: int = 9,
    fill_rgba: tuple[int, int, int, int] = (10, 11, 14, 155),
    outline_rgba: tuple[int, int, int, int] = (255, 255, 255, 35),
    corner_radius: int = 12,
    has_bg_image: bool = True,
) -> None:
    """Desenha um painel glassmorphism sobre o canvas.

    Com bg_image e blur_radius > 0: recorta a região, aplica blur gaussiano real e compõe um overlay
    semi-transparente escuro — efeito de vidro fosco (frosted glass) premium.
    Sem bg_image ou com blur_radius <= 0: desenha painel semi-transparente escuro simples direto.
    Em ambos os casos, adiciona borda translúcida arredondada via alpha_composite.
    """
    x1, y1, x2, y2 = int(region[0]), int(region[1]), int(region[2]), int(region[3])
    w, h = x2 - x1, y2 - y1
    if w <= 0 or h <= 0:
        return

    if has_bg_image and blur_radius > 0:
        # 1. Recortar a região de fundo e aplicar blur gaussiano
        region_crop = canvas.crop((x1, y1, x2, y2)).convert("RGBA")
        blurred = region_crop.filter(ImageFilter.GaussianBlur(radius=blur_radius))

        # 2. Overlay escuro semi-transparente sobre o blur
        overlay = Image.new("RGBA", (w, h), fill_rgba)
        panel = Image.alpha_composite(blurred, overlay)

        # 3. Máscara arredondada
        mask = Image.new("L", (w, h), 0)
        mask_draw = ImageDraw.Draw(mask)
        try:
            mask_draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=corner_radius, fill=255)
        except AttributeError:
            mask_draw.rectangle((0, 0, w - 1, h - 1), fill=255)

        # 4. Colar painel com vidro no canvas
        canvas.paste(panel, (x1, y1), mask=mask)
    else:
        # Painel semi-transparente simples — desenhado via camada para suportar alpha correto
        panel_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        p_draw = ImageDraw.Draw(panel_layer)
        try:
            p_draw.rounded_rectangle((x1, y1, x2, y2), radius=corner_radius, fill=fill_rgba)
        except AttributeError:
            p_draw.rectangle((x1, y1, x2, y2), fill=fill_rgba)
        canvas.alpha_composite(panel_layer)

    # 5. Borda translúcida (sempre via alpha_composite para suportar RGBA correto)
    border_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    b_draw = ImageDraw.Draw(border_layer)
    try:
        b_draw.rounded_rectangle(
            (x1, y1, x2, y2), radius=corner_radius, outline=outline_rgba, width=1
        )
    except AttributeError:
        b_draw.rectangle((x1, y1, x2, y2), outline=outline_rgba)
    canvas.alpha_composite(border_layer)


async def generate_profile_card(
    username: str,
    user_id: int,
    messages_sent: int,
    voice_seconds: int,
    warnings: int,
    joined_date: str,
    level: int,
    xp_current: int,
    xp_needed: int,
    avatar_url: str,
    banner_url: str | None = None,
    theme_name: str = "default",
    coins: int = 0,
) -> io.BytesIO:
    """Gera o Profile Card com glassmorphism e blur gaussiano real nos painéis.

    - Temas com bg_image (fundos comprados): imagem de fundo + painéis com blur frosted glass.
    - Temas de cor (default, discord, etc.): fundo escuro sólido com mesh gradient glows
      e painéis sólidos semi-transparentes.
    """

    # ── Selecionar tema ──────────────────────────────────────────────────────
    has_bg = theme_name in BACKGROUNDS
    if has_bg:
        bg_theme = BACKGROUNDS[theme_name]
        theme: dict = {
            "bg_dark": (18, 20, 26),
            "bg_image": bg_theme["bg_image"],
            "accent": bg_theme["accent"],
            "text_main": (255, 255, 255),
            "text_sub": (200, 205, 212),
        }
    else:
        theme = THEMES.get(theme_name, THEMES["default"])
    accent_color = get_contrast_accent(theme["accent"], (24, 26, 32))

    W, H = 900, 400

    # ── 1. Canvas base & detecção de GIF animado ──────────────────────────────
    is_animated = False
    bg_img = None
    if has_bg:
        try:
            bg_path = os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__), "..", "..", "..", "..", theme["bg_image"]
                )
            )
            if os.path.exists(bg_path):
                bg_img = Image.open(bg_path)
                is_animated = getattr(bg_img, "is_animated", False) and bg_img.n_frames > 1
                if not is_animated:
                    # Converte para RGBA e cria o card estático
                    bg_img_rgba = bg_img.convert("RGBA")
                    card = Image.new("RGBA", (W, H))
                    bg_resized = resize_and_crop(bg_img_rgba, (W, H))
                    card.paste(bg_resized, (0, 0))
            else:
                card = Image.new("RGBA", (W, H), theme["bg_dark"] + (255,))
                has_bg = False
        except Exception:
            card = Image.new("RGBA", (W, H), theme["bg_dark"] + (255,))
            has_bg = False
    else:
        card = Image.new("RGBA", (W, H), theme["bg_dark"] + (255,))
        # Mesh gradient glows para profundidade visual nos temas de cor
        draw_glow(card, (0, 0), 380, accent_color, max_alpha=55)
        draw_glow(card, (W, H), 380, (35, 38, 48), max_alpha=80)

    # ── 2. Configuração visual dos painéis ───────────────────────────────────
    if has_bg:
        panel_fill: tuple = (10, 11, 14, 155)
        panel_outline: tuple = (255, 255, 255, 35)
    else:
        panel_fill = (24, 26, 32, 255)
        panel_outline = (70, 74, 82, 255)

    BLUR = 0 if is_animated else 9  # sem desfoque se for animado

    # ── 3. Stat boxes — pré-definir col_data antes dos painéis ──────────────
    from core.utils.formatters import fmt_voice
    voice_str = fmt_voice(voice_seconds)

    stat_y  = 207
    value_y = 235
    icon_sz = 18

    col_data = [
        {"x": 40,  "cx": 55,  "icon": "chat",     "fallback": "💬", "title": "MENSAGENS", "val": f"{messages_sent:,}".replace(",", ".")},
        {"x": 250, "cx": 265, "icon": "sound",    "fallback": "🎙️", "title": "TEMPO CALL", "val": voice_str},
        {"x": 460, "cx": 475, "icon": "warns",    "fallback": "⚠️", "title": "AVISOS",    "val": str(warnings)},
        {"x": 670, "cx": 685, "icon": "monetization", "fallback": "💰", "title": "MOEDAS",   "val": f"{coins:,}".replace(",", ".")},
    ]
    xp_box_y = 297

    # ── 4. Desenhar painéis de vidro e definir drawing canvas ────────────────
    if not is_animated:
        # Painel de identidade (topo)
        draw_glass_panel(
            card, (40, 40, 860, 190),
            blur_radius=BLUR, fill_rgba=panel_fill, outline_rgba=panel_outline,
            corner_radius=14, has_bg_image=has_bg,
        )

        # 4 stat boxes
        for col in col_data:
            draw_glass_panel(
                card, (col["x"], stat_y, col["x"] + 190, stat_y + 72),
                blur_radius=BLUR, fill_rgba=panel_fill, outline_rgba=panel_outline,
                corner_radius=10, has_bg_image=has_bg,
            )

        # Painel da barra de XP
        draw_glass_panel(
            card, (40, xp_box_y, 860, xp_box_y + 62),
            blur_radius=BLUR, fill_rgba=panel_fill, outline_rgba=panel_outline,
            corner_radius=10, has_bg_image=has_bg,
        )
        drawing_canvas = card
    else:
        # Camada transparente para receber o overlay de textos, avatar e progresso
        drawing_canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # ── 5. Avatar ────────────────────────────────────────────────────────────
    avatar_x, avatar_y, avatar_size = 60, 55, 110
    avatar = await fetch_avatar_image(avatar_url)

    if has_bg:
        # Double ring: anel externo (glow semi-transparente) + anel interno (sólido)
        outer_ring = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        outer_draw = ImageDraw.Draw(outer_ring)
        outer_draw.ellipse(
            (avatar_x - 5, avatar_y - 5, avatar_x + avatar_size + 5, avatar_y + avatar_size + 5),
            outline=accent_color + (110,), width=4,
        )
        drawing_canvas.alpha_composite(outer_ring)

        inner_ring = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        inner_draw = ImageDraw.Draw(inner_ring)
        inner_draw.ellipse(
            (avatar_x - 2, avatar_y - 2, avatar_x + avatar_size + 2, avatar_y + avatar_size + 2),
            outline=accent_color + (255,), width=3,
        )
        drawing_canvas.alpha_composite(inner_ring)
    else:
        # Anel sólido simples para temas de cor
        ring_draw = ImageDraw.Draw(drawing_canvas)
        ring_draw.ellipse(
            (avatar_x - 2, avatar_y - 2, avatar_x + avatar_size + 2, avatar_y + avatar_size + 2),
            outline=accent_color, width=3,
        )

    if avatar:
        circular_avatar = process_avatar(avatar, avatar_size)
        drawing_canvas.paste(circular_avatar, (avatar_x, avatar_y), circular_avatar)
    else:
        placeholder_draw = ImageDraw.Draw(drawing_canvas)
        placeholder_draw.ellipse(
            (avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size),
            fill=accent_color,
        )

    # ── 6. Fontes ────────────────────────────────────────────────────────────
    font_name       = get_font(32, bold=True)
    font_sub        = get_font(18, bold=False)
    font_bold_sm    = get_font(20, bold=True)
    font_stat_title = get_font(13, bold=True)
    font_stat_value = get_font(20, bold=True)

    # Criar draw object no drawing_canvas
    draw = ImageDraw.Draw(drawing_canvas)

    # ── 7. Username e ID ─────────────────────────────────────────────────────
    username_x, username_y = 190, 72
    max_username_w = 840 - username_x - 20
    display_username = username
    try:
        username_w = draw.textlength(display_username, font=font_name)
    except AttributeError:
        username_w, _ = font_name.getsize(display_username)

    while username_w > max_username_w and len(display_username) > 3:
        display_username = display_username[:-1]
        try:
            username_w = draw.textlength(display_username + "...", font=font_name)
        except AttributeError:
            username_w, _ = font_name.getsize(display_username + "...")

    if len(display_username) < len(username):
        display_username += "..."

    draw.text((username_x, username_y), display_username, fill=theme["text_main"], font=font_name)
    draw.text((username_x, username_y + 46), f"ID: {user_id}", fill=theme["text_sub"], font=font_sub)

    # ── 8. Conteúdo das stat boxes ───────────────────────────────────────────
    for col in col_data:
        w = draw_icon_or_text_emoji(
            drawing_canvas, draw, col["icon"], col["fallback"],
            (col["cx"], stat_y + 12), font_stat_title, theme["text_sub"], icon_size=icon_sz,
        )
        draw.text((col["cx"] + w, stat_y + 14), col["title"], fill=theme["text_sub"], font=font_stat_title)
        draw.text((col["cx"], value_y + 5), col["val"], fill=theme["text_main"], font=font_stat_value)

    # ── 9. Conteúdo da barra de XP ───────────────────────────────────────────
    bar_x = 55
    bar_y = xp_box_y + 37
    bar_w = 750
    bar_h = 12

    # Texto do nível (acima da barra, esquerda)
    w5 = draw_icon_or_text_emoji(drawing_canvas, draw, "ray", "⚡", (bar_x, xp_box_y + 9), font_bold_sm, accent_color)
    draw.text((bar_x + w5, xp_box_y + 9), f"NÍVEL {level}", fill=accent_color, font=font_bold_sm)

    # Texto do XP (acima da barra, direita — alinhamento dinâmico)
    xp_text = f"{xp_current:,} / {xp_needed:,} XP".replace(",", ".")
    try:
        xp_text_w = draw.textlength(xp_text, font=font_sub)
    except AttributeError:
        xp_text_w, _ = font_sub.getsize(xp_text)

    stars_icon_path = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "assets", "Image", "Icons", "stars.png"
        )
    )
    stars_w = (24 + 8) if os.path.exists(stars_icon_path) else int(draw.textlength("✨", font=font_sub) + 8)
    xp_x = bar_x + bar_w - int(xp_text_w) - stars_w

    w6 = draw_icon_or_text_emoji(drawing_canvas, draw, "stars", "✨", (xp_x, xp_box_y + 9), font_sub, theme["text_sub"])
    draw.text((xp_x + w6, xp_box_y + 9), xp_text, fill=theme["text_sub"], font=font_sub)

    # Fundo da barra
    try:
        draw.rounded_rectangle(
            (bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), radius=6, fill=(38, 41, 50, 255)
        )
    except AttributeError:
        draw.rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), fill=(38, 41, 50, 255))

    # Preenchimento do progresso (sem fundo)
    progress_pct = (xp_current / xp_needed) if xp_needed > 0 else 1.0
    progress_pct = min(max(progress_pct, 0.0), 1.0)
    fill_w = int(bar_w * progress_pct)

    if fill_w > 0:
        fill_w = max(fill_w, 12)  # mantém arredondado
        try:
            draw.rounded_rectangle(
                (bar_x, bar_y, bar_x + fill_w, bar_y + bar_h), radius=6, fill=accent_color
            )
        except AttributeError:
            draw.rectangle((bar_x, bar_y, bar_x + fill_w, bar_y + bar_h), fill=accent_color)

    # ── 10. Composição final e retorno do buffer ─────────────────────────────
    if is_animated and bg_img:
        # 1. Definição do skip de frames inteligente (limite de 24 frames para excelente fluidez)
        total_frames = bg_img.n_frames
        max_target_frames = 24
        step = max(1, total_frames // max_target_frames)
        
        # Obter paleta global do frame 0
        bg_img.seek(0)
        global_palette = bg_img.getpalette()
        if global_palette is None:
            global_palette = [i for i in range(256) for _ in range(3)]
        
        frames = []
        durations = []
        
        # 2. Processar frames selecionados
        for i in range(0, total_frames, step):
            bg_img.seek(i)
            
            # Guardar frame original do GIF no modo P
            orig_frame_p = bg_img.copy()
            
            # Redimensionar frame original usando NEAREST para preservar paleta
            orig_resized_p = orig_frame_p.resize((W, H), Image.Resampling.NEAREST)
            if orig_resized_p.mode != "P":
                orig_resized_p = orig_resized_p.convert("P")
            orig_resized_p.putpalette(global_palette)
            
            # Composição em RGBA
            frame_rgba = resize_and_crop(bg_img.convert("RGBA"), (W, H))
            
            frame_card = Image.new("RGBA", (W, H))
            frame_card.paste(frame_rgba, (0, 0))
            
            # Painel de identidade (topo)
            draw_glass_panel(
                frame_card, (40, 40, 860, 190),
                blur_radius=BLUR, fill_rgba=panel_fill, outline_rgba=panel_outline,
                corner_radius=14, has_bg_image=True,
            )

            # 4 stat boxes
            for col in col_data:
                draw_glass_panel(
                    frame_card, (col["x"], stat_y, col["x"] + 190, stat_y + 72),
                    blur_radius=BLUR, fill_rgba=panel_fill, outline_rgba=panel_outline,
                    corner_radius=10, has_bg_image=True,
                )

            # Painel da barra de XP
            draw_glass_panel(
                frame_card, (40, xp_box_y, 860, xp_box_y + 62),
                blur_radius=BLUR, fill_rgba=panel_fill, outline_rgba=panel_outline,
                corner_radius=10, has_bg_image=True,
            )
            
            # Compor com a camada estática transparente
            frame_card.alpha_composite(drawing_canvas)
            
            # Converter para RGB antes de quantizar
            rgb_frame = frame_card.convert("RGB")
            
            # Quantizar usando o frame original no modo P como paleta (qualidade 100% de fábrica!)
            p_frame = rgb_frame.quantize(palette=orig_resized_p, dither=Image.Dither.NONE)
            frames.append(p_frame)
            
            # Velocidade corrigida: duração original multiplicada pelo passo (step)
            orig_dur = bg_img.info.get('duration', 100)
            durations.append(max(50, orig_dur * step))
            
        fp = io.BytesIO()
        # Salva como GIF animado de alta fidelidade e velocidade perfeita
        frames[0].save(
            fp, format="GIF", save_all=True, append_images=frames[1:], 
            loop=0, duration=durations, optimize=True
        )
        fp.seek(0)
        return fp
    else:
        fp = io.BytesIO()
        card.save(fp, format="PNG")
        fp.seek(0)
        return fp




