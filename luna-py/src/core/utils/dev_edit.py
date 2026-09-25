"""
Utilitário de edição inline para o modo Dev.
Adiciona botões de edição a Views quando _dev_mode está ativo.
"""

from __future__ import annotations

import discord
from discord import ui

from config.settings import OWNER_ID, BotEmojis
from core.utils.embed_builder import EmbedBuilder


def is_dev_mode(bot) -> bool:
    """Verifica se o bot está em modo dev."""
    return getattr(bot, "_dev_mode", False)


class DevEditModal(ui.Modal):
    """Modal genérico para editar campos de uma tabela."""

    def __init__(
        self,
        *,
        title: str,
        table: str,
        pk_values: dict[str, int | str],
        fields: list[dict],   # [{"name": "xp", "label": "XP", "value": "1500"}, ...]
        bot,
        on_complete=None,
    ) -> None:
        super().__init__(title=title[:45])
        self.table = table
        self.pk_values = pk_values
        self.bot = bot
        self.on_complete = on_complete
        self._field_names: list[str] = []

        # Discord limita a 5 TextInputs por Modal
        for field in fields[:5]:
            text_input = ui.TextInput(
                label=field["label"][:45],
                default=str(field["value"]),
                required=False,
                max_length=100,
            )
            self.add_item(text_input)
            self._field_names.append(field["name"])

    async def on_submit(self, interaction: discord.Interaction) -> None:
        changes: list[str] = []

        for i, field_name in enumerate(self._field_names):
            new_value = self.children[i].value.strip()
            if not new_value:
                continue

            # Construir UPDATE seguro com parametrização
            pk_clause = " AND ".join(f"{k} = ?" for k in self.pk_values)
            pk_params = list(self.pk_values.values())

            await self.bot.db.execute(
                f"UPDATE {self.table} SET {field_name} = ? WHERE {pk_clause}",
                [new_value] + pk_params,
            )
            changes.append(f"`{field_name}` → `{new_value}`")

        if changes:
            await self.bot.db.commit()
            desc = "\n".join(changes)
            embed = EmbedBuilder.success(
                f"Dados atualizados:\n{desc}"
            ).build()
        else:
            embed = EmbedBuilder.alert("Nenhuma alteração feita.").build()

        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Callback para atualizar o embed original
        if self.on_complete:
            await self.on_complete()


class DevEditButton(ui.Button):
    """Botão vermelho 'Dev Edit' para adicionar a qualquer View."""

    def __init__(
        self,
        *,
        bot,
        table: str,
        pk_values: dict[str, int | str],
        fields: list[dict],
        modal_title: str = "Dev Edit",
        on_complete=None,
        row: int = 2,
    ) -> None:
        super().__init__(
            label="Dev Edit",
            style=discord.ButtonStyle.danger,
            emoji=BotEmojis.DEV,
            row=row,
        )
        self.bot = bot
        self.table = table
        self.pk_values = pk_values
        self.fields = fields
        self.modal_title = modal_title
        self.on_complete = on_complete

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == OWNER_ID

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != OWNER_ID:
            return

        modal = DevEditModal(
            title=self.modal_title,
            table=self.table,
            pk_values=self.pk_values,
            fields=self.fields,
            bot=self.bot,
            on_complete=self.on_complete,
        )
        await interaction.response.send_modal(modal)


def inject_dev_edit(
    view: ui.View,
    *,
    bot,
    table: str,
    pk_values: dict[str, int | str],
    fields: list[dict],
    modal_title: str = "Dev Edit",
    on_complete=None,
    row: int = 2,
) -> None:
    """Injeta o botão Dev Edit em uma View SE o modo dev estiver ativo."""
    if not is_dev_mode(bot):
        return

    view.add_item(
        DevEditButton(
            bot=bot,
            table=table,
            pk_values=pk_values,
            fields=fields,
            modal_title=modal_title,
            on_complete=on_complete,
            row=row,
        )
    )
