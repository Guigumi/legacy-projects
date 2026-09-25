"""
XP Listeners - Eventos que contabilizam XP

Processa:
- Mensagens enviadas
- Tempo em canais de voz
- Atribuicao automatica de cargos por XP
"""
import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone
from typing import Dict, Set
import asyncio
import logging

from services.user_service import user_service
from services.repositories import xp_role_repo, guild_repo
from services.event_bus import event_bus, BotEvent
from services.xp.utils import (
    calculate_level, format_xp,
    MESSAGE_XP_COOLDOWN, assign_role_safely
)
from config import Colors

logger = logging.getLogger(__name__)


class XPListeners(commands.Cog):
    """Listener de eventos para contabilizar XP"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Cooldown de mensagens: {guild_id: {user_id: timestamp}}
        self.message_cooldowns: Dict[int, Dict[int, float]] = {}

        # Usuarios em voice: {guild_id: {user_id: join_timestamp}}
        self.voice_users: Dict[int, Dict[int, datetime]] = {}

        # Iniciar task de voice XP
        self.voice_xp_task.start()

    def cog_unload(self):
        self.voice_xp_task.cancel()

    # ======================== CONFIG HELPERS ========================

    def get_xp_config(self, guild_id: int) -> dict:
        """Get XP configuration for the server from DB"""
        return guild_repo.get_xp_config(guild_id)

    def get_roles(self, guild_id: int) -> dict:
        """Get XP roles for the server"""
        return xp_role_repo.get_roles_dict(guild_id)

    def reload_config(self):
        """No-op: config is read from DB now"""
        pass

    # ======================== XP LOGIC ========================

    async def add_xp(self, guild: discord.Guild, member: discord.Member, amount: int, source: str = "message") -> bool:
        """
        Adiciona XP ao usuario e verifica level up/roles.
        Retorna True se houve level up.
        """
        if amount <= 0:
            logger.debug(f"Tentativa de adicionar XP invalido: {amount}")
            return False

        # Persistir XP via service
        result = user_service.add_xp(guild.id, member.id, amount, source=source)
        if not result.get("success"):
            logger.error(f"Failed to save XP update for user {member.id}")
            return False

        old_xp = result.get("old_xp", 0)
        new_xp = result.get("new_xp", 0)

        # Calcular levels
        old_level, _, _ = calculate_level(old_xp)
        new_level, _, _ = calculate_level(new_xp)

        logger.info(
            f"✓ Added {amount} XP ({source}) to {member.id} in {guild.id}: "
            f"{old_xp} → {new_xp} (Level {old_level} → {new_level})"
        )

        # Emit XP gained event
        await event_bus.emit(BotEvent.USER_XP_GAINED, guild.id, {
            'user_id': member.id,
            'amount': amount,
            'source': source,
            'new_xp': new_xp,
            'new_level': new_level
        })

        level_up = new_level > old_level

        # Verificar cargos por XP
        try:
            await self.check_xp_roles(guild, member, new_xp)
        except Exception as e:
            logger.error(f"Error checking XP roles for {member.id}: {e}", exc_info=True)

        # Notificar level up
        if level_up:
            try:
                await self.notify_level_up(guild, member, new_level)
                # Emit level up event
                await event_bus.emit(BotEvent.USER_LEVELED_UP, guild.id, {
                    'user_id': member.id,
                    'new_level': new_level,
                    'old_level': old_level
                })
            except Exception as e:
                logger.error(f"Error notifying level up for {member.id}: {e}", exc_info=True)

        return level_up

    async def check_xp_roles(self, guild: discord.Guild, member: discord.Member, xp: int):
        """Verifica e atribui cargos por XP - Corrigido para evitar loops"""
        config = self.get_xp_config(guild.id)
        roles_config = self.get_roles(guild.id)

        if not roles_config:
            return

        accumulate = config.get("accumulate_roles", True)

        # Ordenar cargos por XP necessario (do menor para o maior)
        sorted_roles = sorted(roles_config.items(), key=lambda x: int(x[1]))

        roles_to_add = set()
        roles_to_remove = set()

        # Determinar quais cargos o usuario DEVERIA ter
        eligible_roles = set()
        for role_id_str, xp_required in sorted_roles:
            role_id = int(role_id_str)
            role = guild.get_role(role_id)

            if not role:
                continue

            # Se tem XP suficiente, e elegivel
            if xp >= int(xp_required):
                eligible_roles.add(role)

        # Em modo nao-acumulativo, manter apenas o cargo de maior nivel
        if not accumulate and eligible_roles:
            # Encontrar o cargo de maior XP que o usuario e elegivel
            highest_role = max(eligible_roles, key=lambda r: int(roles_config.get(str(r.id), 0)))
            eligible_roles = {highest_role}

        # Comparar com cargos que o membro ja tem
        current_xp_roles = {role for role in member.roles if str(role.id) in roles_config}

        # Cargos a adicionar
        roles_to_add = eligible_roles - current_xp_roles

        # Cargos a remover (que tinha mas nao e mais elegivel)
        roles_to_remove = current_xp_roles - eligible_roles

        # Aplicar mudancas com logging e tratamento de erro robusto
        try:
            if roles_to_add:
                logger.debug(f"Adding {len(roles_to_add)} XP roles to {member.id}: {[r.name for r in roles_to_add]}")
                for role in roles_to_add:
                    success = await assign_role_safely(member, role, "XP Role - Cargo automatico por XP")
                    if not success:
                        logger.warning(f"Failed to assign role {role.id} ({role.name}) to {member.id}")

            if roles_to_remove:
                logger.debug(
                    f"Removing {len(roles_to_remove)} XP roles from {member.id}: {[r.name for r in roles_to_remove]}"
                )
                await member.remove_roles(*roles_to_remove, reason="XP Role - Usuario nao elegivel mais")
                logger.info(f"Removed {len(roles_to_remove)} XP role(s) from {member.id}")
        except discord.Forbidden:
            logger.error(f"Permission denied assigning XP roles in guild {guild.id}")
        except Exception as e:
            logger.error(f"Erro ao atribuir cargo XP: {e}")

    async def notify_level_up(self, guild: discord.Guild, member: discord.Member, new_level: int):
        """Notifica level up"""
        config = self.get_xp_config(guild.id)

        if not config.get("levelup_message", True):
            return

        # Determinar canal
        channel_id = config.get("levelup_channel")
        if channel_id:
            channel = guild.get_channel(channel_id)
        else:
            # Usar o canal do sistema ou geral
            channel = guild.system_channel

        if not channel:
            return

        embed = discord.Embed(
            title="🎉 Level Up!",
            description=f"{member.mention} alcancou o **nivel {new_level}**!",
            color=Colors.XP
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        try:
            await channel.send(embed=embed, delete_after=30)
        except discord.Forbidden:
            logger.debug(f"Sem permissao para enviar level up em {guild.name}")
        except Exception as e:
            logger.debug(f"Erro ao enviar level up: {e}")

    # ======================== MESSAGE LISTENER ========================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Processa XP de mensagens via Service"""
        # Ignorar bots, DMs e mensagens de sistema
        if message.author.bot:
            return
        if not message.guild:
            return
        if message.type != discord.MessageType.default and message.type != discord.MessageType.reply:
            return

        guild_id = message.guild.id
        user_id = message.author.id

        # Metricas de mensagens sao registradas no cog de chat

        # Verificar se XP esta ativado
        config = self.get_xp_config(guild_id)
        if not config["enabled"]:
            return

        message_xp = config["message"]
        if message_xp <= 0:
            return

        # Verificar cooldown
        now = datetime.now(timezone.utc).timestamp()

        if guild_id not in self.message_cooldowns:
            self.message_cooldowns[guild_id] = {}

        last_xp = self.message_cooldowns[guild_id].get(user_id, 0)

        if now - last_xp < MESSAGE_XP_COOLDOWN:
            return  # Ainda em cooldown

        # Atualizar cooldown
        self.message_cooldowns[guild_id][user_id] = now

        # ✓ PADRAO: Usar Service em vez de Repository direto
        try:
            result = user_service.add_xp_with_level_up(guild_id, user_id, message_xp, source="message")

            if not result.get("success"):
                logger.error(f"Failed to process message XP for user {user_id}")
                return

            # Verificar cargos por XP
            guild = message.guild
            member = guild.get_member(user_id)
            if member and result.get("level_up"):
                try:
                    await self.check_xp_roles(guild, member, result.get("new_xp", 0))
                    await self.notify_level_up(guild, member, result.get("new_level", 0))
                except Exception as e:
                    logger.error(f"Error processing level up for {user_id}: {e}", exc_info=True)

            logger.debug(f"Added {message_xp} XP to user {user_id}, level_up={result.get('level_up')}")

        except Exception as e:
            logger.error(f"Failed to add message XP for user {user_id}: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Registra reacoes: quem reagiu e quem recebeu a reacao"""
        try:
            # Ignorar reacoes em DMs
            if not payload.guild_id:
                return

            guild_id = payload.guild_id
            reactor_id = payload.user_id

            # Buscar message para saber o autor
            channel = self.bot.get_channel(payload.channel_id)
            if not channel:
                return

            try:
                message = await channel.fetch_message(payload.message_id)
            except Exception:
                return

            # Nao contar reacoes de bots
            if reactor_id is None:
                return
            user = self.bot.get_user(reactor_id)
            if user and user.bot:
                return

            author = message.author
            if author and not getattr(author, 'bot', False):
                result = user_service.record_reaction(guild_id, reactor_id, author.id)
                if result.get("success"):
                    logger.debug(f"Recorded reaction in guild {guild_id}: {reactor_id} -> {author.id}")
                else:
                    logger.error(f"Failed to record reaction in guild {guild_id}")

        except Exception as e:
            logger.error(f"Unhandled error in on_raw_reaction_add: {e}", exc_info=True)

    # ======================== VOICE LISTENERS ========================

    def _count_humans_in_channel(self, channel: discord.VoiceChannel) -> int:
        """Conta quantos humanos (nao-bots) estao no canal"""
        if not channel:
            return 0
        return sum(1 for m in channel.members if not m.bot)

    def _start_tracking(self, guild_id: int, user_id: int, channel_id: int = 0):
        """Inicia rastreamento de XP para um usuario e salva evento"""
        if guild_id not in self.voice_users:
            self.voice_users[guild_id] = {}
        self.voice_users[guild_id][user_id] = datetime.now(timezone.utc)

    def _stop_tracking(self, guild_id: int, user_id: int):
        """Para rastreamento de XP para um usuario e salva evento"""
        if guild_id in self.voice_users and user_id in self.voice_users[guild_id]:
            del self.voice_users[guild_id][user_id]

    def _is_tracking(self, guild_id: int, user_id: int) -> bool:
        """Verifica se esta rastreando XP de um usuario"""
        return guild_id in self.voice_users and user_id in self.voice_users[guild_id]

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ):
        """Rastreia entrada/saida de canais de voz"""
        if member.bot:
            return

        guild_id = member.guild.id
        user_id = member.id
        guild = member.guild

        # Inicializar dict do servidor
        if guild_id not in self.voice_users:
            self.voice_users[guild_id] = {}

        # Entrou em canal de voz
        if before.channel is None and after.channel is not None:
            humans_in_channel = self._count_humans_in_channel(after.channel)

            # Se agora ha 2+ pessoas, comecar a contar XP de todos
            if humans_in_channel >= 2:
                for m in after.channel.members:
                    if not m.bot and not self._is_tracking(guild_id, m.id):
                        self._start_tracking(guild_id, m.id, after.channel.id)
            # Se esta sozinho, nao rastrear

        # Saiu do canal de voz
        elif before.channel is not None and after.channel is None:
            # Processar XP do que saiu (se estava sendo rastreado)
            if self._is_tracking(guild_id, user_id):
                await self._process_voice_xp(member)
                self._stop_tracking(guild_id, user_id)

            # Verificar se alguem ficou sozinho no canal anterior
            humans_left = self._count_humans_in_channel(before.channel)
            if humans_left == 1:
                # Parar contagem de quem ficou sozinho
                for m in before.channel.members:
                    if not m.bot and self._is_tracking(guild_id, m.id):
                        await self._process_voice_xp(m)
                        self._stop_tracking(guild_id, m.id)

        # Mudou de canal
        elif before.channel != after.channel:
            # Processar XP do canal anterior
            if self._is_tracking(guild_id, user_id):
                await self._process_voice_xp(member)

            # Verificar canal que deixou - alguem ficou sozinho?
            humans_left = self._count_humans_in_channel(before.channel)
            if humans_left == 1:
                for m in before.channel.members:
                    if not m.bot and self._is_tracking(guild_id, m.id):
                        await self._process_voice_xp(m)
                        self._stop_tracking(guild_id, m.id)

            # Verificar novo canal - ha 2+ pessoas?
            humans_in_new = self._count_humans_in_channel(after.channel)
            if humans_in_new >= 2:
                for m in after.channel.members:
                    if not m.bot and not self._is_tracking(guild_id, m.id):
                        self._start_tracking(guild_id, m.id, after.channel.id)
            else:
                # Esta sozinho no novo canal, nao rastrear
                self._stop_tracking(guild_id, user_id)

    async def _process_voice_xp(self, member: discord.Member):
        """Processa XP acumulado em voice via Service"""
        guild_id = member.guild.id
        user_id = member.id

        if guild_id not in self.voice_users:
            return
        if user_id not in self.voice_users[guild_id]:
            return

        config = self.get_xp_config(guild_id)
        if not config["enabled"]:
            return

        voice_xp_per_min = config["voice"]
        if voice_xp_per_min <= 0:
            return

        # Calcular tempo em minutos
        join_time = self.voice_users[guild_id][user_id]
        now = datetime.now(timezone.utc)
        duration = (now - join_time).total_seconds() / 60  # em minutos

        if duration < 1:
            return  # Menos de 1 minuto, ignorar

        minutes = int(duration)
        xp_to_add = minutes * voice_xp_per_min

        if xp_to_add > 0:
            # ✓ PADRAO: Usar Service em vez de Repository direto
            try:
                # Incrementar tempo de voz
                result = user_service.record_voice_minutes(guild_id, user_id, minutes)
                if result:
                    logger.info(f"✓ Added {minutes} voice minutes to user {user_id} in guild {guild_id}")
                else:
                    logger.error(f"Failed to save voice minutes for user {user_id}")

                # Adicionar XP via Service
                xp_result = user_service.add_xp_with_level_up(guild_id, user_id, xp_to_add, source="voice")

                if xp_result.get("success") and xp_result.get("level_up"):
                    # Verificar roles e notificar level up
                    await self.check_xp_roles(member.guild, member, xp_result.get("new_xp", 0))
                    await self.notify_level_up(member.guild, member, xp_result.get("new_level", 0))

            except Exception as e:
                logger.error(f"Error adding voice XP for user {user_id}: {e}", exc_info=True)

        # Resetar timer para o proximo periodo
        self.voice_users[guild_id][user_id] = now

    @tasks.loop(minutes=5)
    async def voice_xp_task(self):
        """Task que processa XP de voice a cada 5 minutos"""
        for guild_id, users in list(self.voice_users.items()):
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            for user_id in list(users.keys()):
                member = guild.get_member(user_id)
                if not member or not member.voice or not member.voice.channel:
                    # Usuario nao esta mais em voice, remover
                    self._stop_tracking(guild_id, user_id)
                    continue

                # Verificar se ainda ha 2+ pessoas no canal
                humans = self._count_humans_in_channel(member.voice.channel)
                if humans >= 2:
                    await self._process_voice_xp(member)
                else:
                    # Ficou sozinho, parar contagem
                    self._stop_tracking(guild_id, user_id)

    @voice_xp_task.before_loop
    async def before_voice_xp_task(self):
        await self.bot.wait_until_ready()

    # ======================== SYNC COMMAND ========================

    @commands.Cog.listener()
    async def on_ready(self):
        """Ao iniciar, recuperar sessoes ativas e verificar usuarios ja em voice"""
        await self.bot.wait_until_ready()
        await asyncio.sleep(2)

        # Recovery: Finalizar sessoes ativas de crashes anteriores
        logger.info("[Voice] Iniciando recovery de sessoes...")
        await self._recover_active_sessions()

        await asyncio.sleep(3)  # Aguardar bot estar totalmente pronto

        for guild in self.bot.guilds:
            config = self.get_xp_config(guild.id)
            if not config["enabled"] or config["voice"] <= 0:
                continue

            if guild.id not in self.voice_users:
                self.voice_users[guild.id] = {}

            for vc in guild.voice_channels:
                # So contar se ha 2+ humanos no canal
                humans = self._count_humans_in_channel(vc)
                if humans >= 2:
                    for member in vc.members:
                        if not member.bot:
                            self._start_tracking(guild.id, member.id, vc.id)

    async def _recover_active_sessions(self):
        """Recovery: Finaliza sessoes ativas que nao foram encerradas (crash)"""
        try:
            recovered = user_service.recover_active_voice_sessions()
            if recovered:
                logger.info(f"[Voice] Sessoes recuperadas: {recovered}")

        except Exception as e:
            logger.error(f"[Voice] Erro ao recuperar sessoes ativas: {e}", exc_info=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(XPListeners(bot))
