"""
Cog de Roleplay (RP) — comandos de interação e ações divertidas entre membros.
"""

from __future__ import annotations

import datetime
import hashlib
import io
import discord
from discord import app_commands
from discord.ext import commands

from config.settings import Colors, BotEmojis
from core.bot import LunaBot
from core.utils.embed_builder import EmbedBuilder


def get_ship_percentage(user1_id: int, user2_id: int) -> int:
    """Retorna uma porcentagem de compatibilidade determinística que muda diariamente."""
    u1, u2 = sorted([user1_id, user2_id])
    today_str = datetime.date.today().isoformat()
    hash_input = f"{u1}-{u2}-{today_str}".encode()
    hash_hex = hashlib.sha256(hash_input).hexdigest()
    # Converte os últimos 4 caracteres hexadecimais para inteiro e tira o módulo 101 (0 a 100)
    return int(hash_hex[-4:], 16) % 101


class RoleplayCog(commands.Cog, name="Roleplay"):
    """Comandos de interações sociais e ações (Roleplay)."""

    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot
        self.service = bot.roleplay_service

    async def _perform_reaction(
        self,
        ctx: commands.Context,
        user: discord.Member,
        reaction_type: str,
        action_text: str,
    ) -> None:
        """Função auxiliar genérica para lidar com comandos de ação com GIFs."""
        await ctx.defer()

        author = ctx.author
        is_self = user.id == author.id
        is_bot = user.id == self.bot.user.id if self.bot.user else False

        # Frases customizadas para auto-interação e interação com o bot
        if is_self:
            self_phrases = {
                "kiss": "Você se beijou no espelho? Que fofo...",
                "hug": "Se abraçando sozinho? Às vezes todos precisamos de um auto-abraço!",
                "slap": "Por que você está se batendo? Pare com isso!",
                "pat": "Fazendo carinho em si mesmo? Auto-cuidado é importante!",
                "bite": "Se mordendo? Tudo bem aí?",
                "cuddle": "Se aconchegando sob as cobertas sozinho... bem quentinho.",
                "poke": "Se cutucando para ver se está acordado?",
                "bonk": "Se deu um bonk na cabeça? Que atrapalhado!",
                "tickle": "Tentar fazer cócegas em si mesmo não funciona!",
                "highfive": "Bateu palma sozinho? É um high-five solitário.",
                "punch": "Se batendo? Procure ajuda!",
                "wave": "Acenando para si mesmo no espelho?",
            }
            desc = self_phrases.get(reaction_type, "Você interagiu consigo mesmo.")
        elif is_bot:
            bot_phrases = {
                "kiss": "Fico lisonjeada, mas prefiro ser apenas sua assistente!",
                "hug": "Que abraço quentinho! Obrigado por ser tão gentil.",
                "slap": "Ei! O que eu te fiz? Magoou...",
                "pat": "Amo carinho nos meus circuitos! Obrigada!",
                "bite": "Ai! Não morda a inteligência artificial, pode dar choque!",
                "cuddle": "Ficar de conchinha com um bot? Bem aconchegante e aquecido!",
                "poke": "Bip bup! Fui cutucada.",
                "bonk": "Por que o bonk? Eu me comportei bem!",
                "tickle": "Hahaha! Meus sensores de cócegas estão disparando!",
                "highfive": "Toca aqui! ✋ Fizemos um bom trabalho!",
                "punch": "Não me bata! Vou chamar a moderação!",
                "wave": "Olá! Acenando de volta!",
            }
            desc = bot_phrases.get(reaction_type, "Você interagiu comigo.")
        else:
            desc = f"{author.mention} {action_text} {user.mention}!"

        # Busca o link do GIF através do serviço
        gif_url = await self.service.get_reaction_gif(reaction_type)
        if not gif_url:
            embed = EmbedBuilder.error_user(
                f"Não consegui carregar um GIF de {reaction_type} no momento. Tente novamente mais tarde."
            ).build()
            await ctx.send(embed=embed)
            return

        embed = (
            EmbedBuilder.default()
            .color(Colors.GAMES)
            .description(desc)
            .image(gif_url)
            .build()
        )
        await ctx.send(embed=embed)

    # ── Comandos Principais ──────────────────────────────────────────

    @commands.hybrid_command(
        name="ship",
        description="Calcula a compatibilidade amorosa entre dois membros.",
    )
    @app_commands.describe(
        user1="Primeiro membro",
        user2="Segundo membro",
    )
    async def ship(
        self,
        ctx: commands.Context,
        user1: discord.Member,
        user2: discord.Member,
    ) -> None:
        await ctx.defer()

        love_pct = get_ship_percentage(user1.id, user2.id)
        active_hearts = round(love_pct / 10)

        # Monta a barra usando as constantes dos novos emojis
        bar = f"{BotEmojis.HEART_PINK * active_hearts}{BotEmojis.HEART_BLACK * (10 - active_hearts)}"

        # Determina a mensagem com base na compatibilidade
        if love_pct <= 20:
            msg = "Apenas conhecidos... a chama está bem fria."
        elif love_pct <= 50:
            msg = "Talvez como amigos? Há uma pequena faísca."
        elif love_pct <= 80:
            msg = "Sintonia muito boa! O amor pode estar a caminho."
        else:
            msg = "Almas gêmeas! Um casal perfeito e inabalável!"

        embed = (
            EmbedBuilder.default()
            .color(Colors.GAMES)
            .title("Teste de Compatibilidade")
            .description(
                f"### {user1.mention} + {user2.mention}\n\n"
                f"**Resultado:** `{love_pct}%` de compatibilidade\n"
                f"{bar}\n\n"
                f"*{msg}*"
            )
            .build()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="jail",
        description="Prende um membro na prisão da Luna com grades na foto.",
    )
    @app_commands.describe(user="O membro que você deseja prender")
    async def jail(self, ctx: commands.Context, user: discord.Member) -> None:
        await ctx.defer()

        author = ctx.author
        is_self = user.id == author.id
        is_bot = user.id == self.bot.user.id if self.bot.user else False

        avatar_url = user.display_avatar.url
        try:
            image_bytes = await self.service.get_jail_image(avatar_url)
            if not image_bytes:
                embed = EmbedBuilder.error_user("Não foi possível gerar a foto de prisão.").build()
                await ctx.send(embed=embed)
                return
        except Exception:
            self.bot.logger.exception("Comando jail falhou")
            embed = EmbedBuilder.error_user("Ocorreu um erro ao gerar a foto de prisão.").build()
            await ctx.send(embed=embed)
            return

        if is_self:
            desc = f"{author.mention} se prendeu na prisão!"
        elif is_bot:
            desc = f"{author.mention} tentou me prender, mas eu escapei e prendi ele de volta!"
        else:
            desc = f"{author.mention} prendeu {user.mention} na prisão!"

        file = discord.File(io.BytesIO(image_bytes), filename="jail.png")
        embed = (
            EmbedBuilder.default()
            .color(Colors.GAMES)
            .description(desc)
            .image("attachment://jail.png")
            .build()
        )
        await ctx.send(embed=embed, file=file)

    # ── Comandos de Ação (GIFs) ──────────────────────────────────────

    @commands.hybrid_command(name="kiss", description="Dê um beijo carinhoso em alguém.")
    @app_commands.describe(user="O membro que você deseja beijar")
    async def kiss(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._perform_reaction(ctx, user, "kiss", "deu um beijo em")

    @commands.hybrid_command(name="hug", description="Dê um abraço caloroso em alguém.")
    @app_commands.describe(user="O membro que você deseja abraçar")
    async def hug(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._perform_reaction(ctx, user, "hug", "deu um abraço em")

    @commands.hybrid_command(name="slap", description="Dê um tapa em alguém.")
    @app_commands.describe(user="O membro que você deseja dar um tapa")
    async def slap(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._perform_reaction(ctx, user, "slap", "deu um tapa em")

    @commands.hybrid_command(name="pat", description="Faça carinho em alguém.")
    @app_commands.describe(user="O membro em quem deseja fazer carinho")
    async def pat(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._perform_reaction(ctx, user, "pat", "fez carinho em")

    @commands.hybrid_command(name="bite", description="Dê uma mordida em alguém.")
    @app_commands.describe(user="O membro que você deseja morder")
    async def bite(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._perform_reaction(ctx, user, "bite", "deu uma mordidinha em")

    @commands.hybrid_command(name="cuddle", description="Aconchegue-se com alguém.")
    @app_commands.describe(user="O membro com quem deseja se aconchegar")
    async def cuddle(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._perform_reaction(ctx, user, "cuddle", "se aconchegou com")

    @commands.hybrid_command(name="poke", description="Cutuque alguém.")
    @app_commands.describe(user="O membro que você deseja cutucar")
    async def poke(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._perform_reaction(ctx, user, "poke", "cutucou")

    @commands.hybrid_command(name="bonk", description="Dê um bonk na cabeça de alguém.")
    @app_commands.describe(user="O membro que você deseja dar bonk")
    async def bonk(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._perform_reaction(ctx, user, "bonk", "deu um bonk na cabeça de")

    @commands.hybrid_command(name="tickle", description="Faça cócegas em alguém.")
    @app_commands.describe(user="O membro em quem deseja fazer cócegas")
    async def tickle(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._perform_reaction(ctx, user, "tickle", "fez cócegas em")

    @commands.hybrid_command(name="highfive", description="Dê um high five em alguém.")
    @app_commands.describe(user="O membro a quem deseja dar um high five")
    async def highfive(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._perform_reaction(ctx, user, "highfive", "deu um high-five em")

    @commands.hybrid_command(name="punch", description="Dê um soco em alguém.")
    @app_commands.describe(user="O membro que você deseja socar")
    async def punch(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._perform_reaction(ctx, user, "punch", "deu um soco em")

    @commands.hybrid_command(name="wave", description="Acene para alguém.")
    @app_commands.describe(user="O membro para quem deseja acenar")
    async def wave(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._perform_reaction(ctx, user, "wave", "acenou para")


async def setup(bot: LunaBot) -> None:
    await bot.add_cog(RoleplayCog(bot))
