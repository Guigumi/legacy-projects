import discord
import logging
from discord.ext import commands
from discord.ui import View, Button, Select
from typing import Optional

from config import Colors
from services.embed_helpers import embed_cooldown, embed_error, embed_internal_error

logger = logging.getLogger(__name__)


# Maximum quality sizes for Discord assets
AVATAR_SIZE = 4096
BANNER_SIZE = 4096


class ProfileView(View):
    """View with buttons to show avatar/banner in full quality"""
    
    def __init__(self, member: discord.Member, user: discord.User, timeout: float = 120):
        super().__init__(timeout=timeout)
        self.member = member
        self.user = user
        
        # Get high quality URLs
        self.avatar_url = self._get_avatar_url()
        self.guild_avatar_url = self._get_guild_avatar_url()
        self.banner_url = self._get_banner_url()
        
        # Add buttons dynamically
        self._add_buttons()
    
    def _get_avatar_url(self) -> Optional[str]:
        """Get global avatar URL in max quality"""
        if self.user.avatar:
            return self.user.avatar.replace(size=AVATAR_SIZE, format='png').url
        return self.user.default_avatar.url
    
    def _get_guild_avatar_url(self) -> Optional[str]:
        """Get server-specific avatar URL in max quality"""
        if self.member.guild_avatar:
            return self.member.guild_avatar.replace(size=AVATAR_SIZE, format='png').url
        return None
    
    def _get_banner_url(self) -> Optional[str]:
        """Get banner URL in max quality"""
        if self.user.banner:
            # Use gif format if animated, otherwise png
            fmt = 'gif' if self.user.banner.is_animated() else 'png'
            return self.user.banner.replace(size=BANNER_SIZE, format=fmt).url
        return None
    
    def _add_buttons(self):
        """Add appropriate buttons based on available assets"""
        # Avatar button (always available)
        avatar_btn = Button(
            label="Avatar",
            emoji="🖼️",
            style=discord.ButtonStyle.primary,
            url=self.avatar_url
        )
        self.add_item(avatar_btn)
        
        # Guild avatar button (if different from global)
        if self.guild_avatar_url and self.guild_avatar_url != self.avatar_url:
            guild_avatar_btn = Button(
                label="Avatar (Servidor)",
                emoji="🏠",
                style=discord.ButtonStyle.secondary,
                url=self.guild_avatar_url
            )
            self.add_item(guild_avatar_btn)
        
        # Banner button (if user has one)
        if self.banner_url:
            banner_btn = Button(
                label="Banner",
                emoji="🎨",
                style=discord.ButtonStyle.success,
                url=self.banner_url
            )
            self.add_item(banner_btn)


class Profile(commands.Cog):
    """Cog to display Discord user profile pictures and banners"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _fetch_user_data(self, member: discord.Member) -> discord.User:
        """Fetch full user data including banner"""
        try:
            return await self.bot.fetch_user(member.id)
        except (discord.NotFound, discord.HTTPException):
            return member._user

    async def _create_profile_embed(self, member: discord.Member, user: discord.User) -> discord.Embed:
        """Creates clean profile embed following the example style"""
        
        # Get high quality avatar
        if member.guild_avatar:
            avatar_url = member.guild_avatar.replace(size=AVATAR_SIZE, format='png').url
        elif user.avatar:
            avatar_url = user.avatar.replace(size=AVATAR_SIZE, format='png').url
        else:
            avatar_url = user.default_avatar.url
        
        # Get high quality banner
        banner_url = None
        if user.banner:
            fmt = 'gif' if user.banner.is_animated() else 'png'
            banner_url = user.banner.replace(size=BANNER_SIZE, format=fmt).url
        
        # Build embed with profile color
        embed = discord.Embed(
            title="",
            description=" ",
            color=member.accent_color or Colors.PRIMARY
        )
        
        # Author with avatar and display name
        embed.set_author(name=member.display_name, icon_url=avatar_url)
        
        # Avatar as thumbnail
        embed.set_thumbnail(url=avatar_url)
        
        embed.add_field(name="─────〔 Perfil 〕─────", value="", inline=False)
        
        # User info fields (inline)
        embed.add_field(name="ID", value=f"```{member.id}```", inline=True)
        embed.add_field(name="", value="", inline=True)
        embed.add_field(name="Username", value=f"```{member.name}```", inline=True)

        # Banner as main image
        if banner_url:
            embed.set_image(url=banner_url)
        
        return embed

    @commands.hybrid_command(
        name='perfil',
        aliases=['profile', 'avatar', 'pfp', 'banner'],
        description='Mostra foto e banner do perfil em alta qualidade'
    )
    @commands.guild_only()
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def profile(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Shows user avatar and banner in high quality with download links"""
        if not ctx.guild:
            return await ctx.send(embed=embed_error("Este comando só pode ser usado em servidores!"), ephemeral=True)

        target = member or ctx.author

        try:
            target = await ctx.guild.fetch_member(target.id)
        except discord.NotFound:
            return await ctx.send(embed=embed_error("Membro não encontrado!"), ephemeral=True)

        try:
            # Fetch full user data (needed for banner)
            user = await self._fetch_user_data(target)
            
            # Create embed and view
            embed = await self._create_profile_embed(target, user)
            view = ProfileView(target, user)
            
            await ctx.send(embed=embed, view=view)

        except Exception as e:
            await ctx.send(embed=embed_internal_error(), ephemeral=True)

    @profile.error
    async def profile_error(self, ctx: commands.Context, error: Exception):
        """Handles profile command errors"""
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(embed=embed_cooldown(error.retry_after), ephemeral=True)
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send(embed=embed_error("Comando só em servidores!"), ephemeral=True)
        else:
            await ctx.send(embed=embed_internal_error(), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Profile(bot))
