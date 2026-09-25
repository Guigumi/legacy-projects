from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta

import discord
from discord import app_commands, ui
from discord.ext import commands

from config.settings import BotEmojis, Separators, now_brt, BRT
from core.bot import LunaBot
from core.events import BotEvent
from core.utils.embed_builder import EmbedBuilder

logger = logging.getLogger(__name__)


class GiveawayCog(commands.Cog, name="Giveaway"):
    """Sistema de sorteios interativos."""

    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot
        self.bot.event_bus.subscribe(BotEvent.GIVEAWAY_ENDED, self.on_giveaway_ended)

    async def cog_load(self) -> None:
        self.bot.giveaway_service.start()
        # Registrar views persistentes
        active = await self.bot.giveaway_service.repo.get_active_giveaways()
        for gw in active:
            if gw.get("message_id"):
                self.bot.add_view(GiveawayJoinView(self.bot.giveaway_service, gw["id"]), message_id=gw["message_id"])

    async def cog_unload(self) -> None:
        self.bot.giveaway_service.stop()

    async def on_giveaway_ended(self, guild_id: int, event: BotEvent, data: dict) -> None:
        gw = data["giveaway"]
        winners = data["winners"]
        
        channel = self.bot.get_channel(gw["channel_id"])
        if not channel:
            return

        prize = gw["prize"]
        if not winners:
            embed = EmbedBuilder.error_user(f"O sorteio de **{prize}** encerrou, mas não houve participantes válidos.").build()
            await channel.send(embed=embed)
            return

        winner_mentions = ", ".join(f"<@{uid}>" for uid in winners)
        embed = (
            EmbedBuilder.success(f"Parabéns aos ganhadores de **{prize}**!")
            .description(f"{BotEmojis.COMMON_SPARKLES} Ganhadores: {winner_mentions}")
            .footer(f"ID do Sorteio: #{gw['id']}")
            .build()
        )
        
        await channel.send(content=f"🎉 {winner_mentions}", embed=embed)
        
        if gw.get("message_id"):
            try:
                msg = await channel.fetch_message(gw["message_id"])
                old_embed = msg.embeds[0]
                new_embed = discord.Embed.from_dict(old_embed.to_dict())
                new_embed.description = f"**Sorteio Encerrado!**\n\nGanhadores: {winner_mentions}"
                new_embed.color = discord.Color.red()
                await msg.edit(embed=new_embed, view=None)
            except Exception:
                logger.debug("Falha ao editar mensagem do sorteio #%s encerrado.", gw.get("id"))

    @app_commands.command(name="giveaway", description="Comandos de sorteio")
    @app_commands.describe(acao="O que fazer", premio="Prêmio", duracao="Duração (ex: 1h, 1d)", ganhadores="Qtd ganhadores", giveaway_id="ID para reroll/cancelar")
    @app_commands.choices(acao=[
        app_commands.Choice(name="Iniciar", value="start"),
        app_commands.Choice(name="Reroll (Sortear novamente)", value="reroll"),
        app_commands.Choice(name="Cancelar", value="cancel"),
    ])
    @commands.has_permissions(manage_guild=True)
    async def giveaway_cmd(
        self, interaction: discord.Interaction, acao: str, 
        premio: str | None = None, duracao: str | None = None, 
        ganhadores: int = 1, giveaway_id: int | None = None
    ) -> None:
        if acao == "start":
            if not premio or not duracao:
                await interaction.response.send_message("Para iniciar, informe o prêmio e a duração.", ephemeral=True)
                return
                
            delta = self._parse_duration(duracao)
            if not delta:
                await interaction.response.send_message("Duração inválida. Ex: `1h`, `30m`.", ephemeral=True)
                return

            ends_at = now_brt() + delta
            gw_id = await self.bot.giveaway_service.create_giveaway(
                interaction.guild_id, interaction.channel_id, interaction.user.id, premio, ganhadores, ends_at
            )

            embed = (
                EmbedBuilder.default()
                .title(f"{BotEmojis.COMMON_TROPHY} Sorteio: {premio}")
                .description(
                    f"Clique no botão abaixo para participar!\n\n"
                    f"**Ganhadores:** {ganhadores}\n"
                    f"**Encerra em:** <t:{int(ends_at.timestamp())}:R> (<t:{int(ends_at.timestamp())}:F>)"
                )
                .footer(f"ID: #{gw_id} | Criado por {interaction.user.display_name}")
                .build()
            )

            view = GiveawayJoinView(self.bot.giveaway_service, gw_id)
            await interaction.response.send_message(embed=embed, view=view)
            msg = await interaction.original_response()
            await self.bot.giveaway_service.repo.update_message_id(gw_id, msg.id)

        elif acao == "reroll":
            if not giveaway_id:
                await interaction.response.send_message("Informe o ID do sorteio.", ephemeral=True)
                return
            
            winners = await self.bot.giveaway_service.reroll(giveaway_id)
            if winners is None:
                await interaction.response.send_message("Sorteio não encontrado ou ainda não encerrou.", ephemeral=True)
            elif not winners:
                await interaction.response.send_message("Não houve participantes para o reroll.", ephemeral=True)
            else:
                mentions = ", ".join(f"<@{uid}>" for uid in winners)
                await interaction.response.send_message(f"{BotEmojis.COMMON_TROPHY} **Reroll!** Novos ganhadores: {mentions}")

        elif acao == "cancel":
            if not giveaway_id:
                await interaction.response.send_message("Informe o ID do sorteio.", ephemeral=True)
                return
            await self.bot.giveaway_service.cancel_giveaway(giveaway_id)
            await interaction.response.send_message(f"Sorteio `#{giveaway_id}` cancelado.", ephemeral=True)

    @giveaway_cmd.autocomplete("giveaway_id")
    async def giveaway_id_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[int]]:
        if not interaction.guild_id:
            return []
        try:
            giveaways = await self.bot.giveaway_service.get_giveaways(interaction.guild_id)
        except Exception:
            return []
        choices = []
        for gw in giveaways:
            status = "Encerrado" if gw["ended"] else ("Cancelado" if gw["cancelled"] else "Ativo")
            label = f"#{gw['id']} - {gw['prize']} ({status})"
            if current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label[:100], value=gw["id"]))
        return choices[:25]

    def _parse_duration(self, text: str) -> timedelta | None:
        pattern = r"^(?:(\d+)d)?\s*(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:(\d+)s)?$"
        match = re.match(pattern, text.strip().lower())
        if not match: return None
        d, h, m, s = [int(match.group(i) or 0) for i in range(1, 5)]
        if d == h == m == s == 0: return None
        return timedelta(days=d, hours=h, minutes=m, seconds=s)

class GiveawayJoinView(ui.View):
    def __init__(self, service, giveaway_id: int) -> None:
        super().__init__(timeout=None)
        self.service = service
        self.gw_id = giveaway_id
        # custom_id único por sorteio para suportar views persistentes após restart
        self.clear_items()
        btn = ui.Button(
            label="Participar",
            style=discord.ButtonStyle.success,
            emoji=BotEmojis.COMMON_GIFT,
            custom_id=f"gw_join:{giveaway_id}",
        )
        btn.callback = self.join_callback
        self.add_item(btn)

    async def join_callback(self, interaction: discord.Interaction) -> None:
        success = await self.service.add_entry(self.gw_id, interaction.user.id)
        if success:
            await interaction.response.send_message("Você entrou no sorteio!", ephemeral=True)
        else:
            await interaction.response.send_message("Você já está participando.", ephemeral=True)

async def setup(bot: LunaBot) -> None:
    await bot.add_cog(GiveawayCog(bot))
