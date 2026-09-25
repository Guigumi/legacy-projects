import discord
import logging
from discord.ext import commands
from discord.ui import Select, View

from config import Colors

logger = logging.getLogger(__name__)

# ======================== CATEGORIES CONFIG ========================
HELP_CATEGORIES = {
    "admin": {
        "label": "Administração",
        "emoji": "⚙️",
        "color": Colors.INFO,
        "commands": [
            ("logs", "Canal de logs"),
            ("nologs", "Desativa logs"),
            ("logconfig", "Evento específico"),
            ("prefix", "Altera prefixo"),
            ("autorole", "Cargo automático"),
            ("xpconfig", "Sistema de XP"),
            ("xprole", "Cargos por nível"),
            ("limpar", "Limpa mensagens"),
            ("configdaily", "Config do daily"),
            ("configloja", "Config da loja"),
        ]
    },
    "economia": {
        "label": "Economia",
        "emoji": "🪙",
        "color": Colors.XP,
        "commands": [
            ("banco", "Saldo e histórico"),
            ("daily", "Recompensa diária"),
            ("pagar", "Envia mora"),
            ("ricos", "Ranking de mora"),
            ("loja", "Loja de cargos"),
            ("compras", "Seus itens"),
        ]
    },
    "apostas": {
        "label": "Apostas",
        "emoji": "🎰",
        "color": Colors.WARNING,
        "commands": [
            ("moeda", "Cara ou coroa"),
            ("slots", "Caça-níqueis"),
            ("roleta", "Roleta de casino"),
        ]
    },
    "util": {
        "label": "Utilidades",
        "emoji": "🛠️",
        "color": Colors.INFO,
        "commands": [
            ("server", "Info do servidor"),
            ("bot", "Info do bot"),
            ("cargos", "Lista cargos"),
            ("yt", "Busca no YouTube"),
            ("baixar", "Baixa vídeo/áudio"),
            ("notify", "Notificações"),
        ]
    },
    "diversao": {
        "label": "Diversão",
        "emoji": "🎉",
        "color": Colors.SUCCESS,
        "commands": [
            ("perfil", "Perfil do Discord"),
            ("status", "Suas estatísticas"),
            ("call", "Ranking de voz"),
            ("chat", "Ranking de chat"),
            ("dado", "Rolagem de dados"),
            ("escolher", "Escolha aleatória"),
            ("carta", "Carta aleatória"),
        ]
    },
    "jogos": {
        "label": "Jogos",
        "emoji": "🎮",
        "color": Colors.XP,
        "commands": [
            ("steam", "Busca na Steam"),
            ("batalha", "Batalha PvP"),
            ("osu", "Perfil osu!"),
        ]
    },
    "xp": {
        "label": "Sistema XP",
        "emoji": "⭐",
        "color": Colors.XP,
        "commands": [
            ("xp", "Ver XP e nível"),
            ("ranking", "Ranking do servidor"),
        ]
    },
}

# ======================== UI COMPONENTS ========================

class HelpSelect(Select):
    """Select menu to choose categories"""
    
    def __init__(self):
        options = [
            discord.SelectOption(
                label=data["label"],
                emoji=data["emoji"],
                value=key
            )
            for key, data in HELP_CATEGORIES.items()
        ]
        
        super().__init__(
            placeholder="escolha uma categoria...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            category_key = self.values[0]
            category = HELP_CATEGORIES.get(category_key)
            
            if not category:
                await interaction.response.defer()
                return
            
            embed = discord.Embed(
                title=f"{category['emoji']} {category['label']}",
                color=category['color']
            )
            
            # Lista compacta de comandos
            cmd_lines = []
            for cmd_name, cmd_desc in category['commands']:
                cmd_lines.append(f"`/{cmd_name}` — {cmd_desc}")
            
            embed.description = "\n".join(cmd_lines)
            embed.set_footer(text="use o menu pra ver outras categorias")
            
            await interaction.response.edit_message(embed=embed, view=self.view)
        except discord.NotFound:
            # Interação expirou
            pass
        except Exception as e:
            logger.debug(f"Erro no HelpSelect: {e}")
            try:
                await interaction.response.defer()
            except:
                pass


class HelpView(View):
    """View containing the select menu"""
    
    def __init__(self):
        super().__init__(timeout=120)
        self.message: discord.Message = None
        self.add_item(HelpSelect())
    
    async def on_timeout(self) -> None:
        """Desabilita o menu quando expira"""
        for child in self.children:
            child.disabled = True
        
        if self.message:
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.HTTPException):
                pass

# ======================== HELP COG ========================

class Help(commands.Cog):
    """Cog for bot help command"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._original_help_command = bot.help_command
        bot.help_command = None

    def cog_unload(self):
        """Restores original help command"""
        self.bot.help_command = self._original_help_command

    def _create_main_embed(self) -> discord.Embed:
        """Creates main help embed"""
        embed = discord.Embed(
            title="📚 Central de Ajuda",
            description="selecione uma categoria no menu abaixo",
            color=Colors.PRIMARY
        )
        
        # Lista compacta das categorias
        categories_text = []
        for data in HELP_CATEGORIES.values():
            cmd_count = len(data['commands'])
            categories_text.append(f"{data['emoji']} **{data['label']}** — {cmd_count} comandos")
        
        embed.add_field(
            name="Categorias",
            value="\n".join(categories_text),
            inline=False
        )
        
        embed.set_footer(text="dica: use /comando pra acesso rápido")
        return embed

    @commands.hybrid_command(
        name='help',
        aliases=['ajuda', 'comandos'],
        description='Mostra comandos disponíveis do bot'
    )
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def help_command(self, ctx: commands.Context):
        """Displays help center with categories"""
        embed = self._create_main_embed()
        view = HelpView()
        msg = await ctx.reply(embed=embed, view=view, mention_author=False)
        view.message = msg

    @help_command.error
    async def help_error(self, ctx: commands.Context, error: Exception):
        """Handles command errors"""
        if isinstance(error, commands.CommandOnCooldown):
            embed = discord.Embed(
                description=f"⏳ espera `{error.retry_after:.1f}s` pra usar de novo",
                color=Colors.USER_ERROR
            )
            await ctx.send(embed=embed, delete_after=5)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Help(bot))
