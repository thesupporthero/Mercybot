from __future__ import annotations

import re
import asyncio
import datetime
import logging
from typing import TYPE_CHECKING, Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

from .utils import checks

if TYPE_CHECKING:
    from bot import Mercybot
    from .utils.context import Context, GuildContext

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config class
# ---------------------------------------------------------------------------

class TicketConfig:
    __slots__ = ('bot', 'id', 'channel_id', 'log_channel_id', 'category_id', 'auto_delete')

    def __init__(self) -> None:
        pass

    @classmethod
    def from_record(cls, record: Any, bot: Mercybot) -> TicketConfig:
        self = cls()
        self.bot = bot
        self.id: int = record['id']
        self.channel_id: Optional[int] = record['channel_id']
        self.log_channel_id: Optional[int] = record['log_channel_id']
        self.category_id: Optional[int] = record['category_id']
        self.auto_delete: bool = record['auto_delete']
        return self

    @property
    def panel_channel(self) -> Optional[discord.TextChannel]:
        guild = self.bot.get_guild(self.id)
        if guild is None or self.channel_id is None:
            return None
        return guild.get_channel(self.channel_id)  # type: ignore

    @property
    def log_channel(self) -> Optional[discord.TextChannel]:
        guild = self.bot.get_guild(self.id)
        if guild is None or self.log_channel_id is None:
            return None
        return guild.get_channel(self.log_channel_id)  # type: ignore

    @property
    def discord_category(self) -> Optional[discord.CategoryChannel]:
        guild = self.bot.get_guild(self.id)
        if guild is None or self.category_id is None:
            return None
        return guild.get_channel(self.category_id)  # type: ignore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def get_ticket_config(bot: Mercybot, guild_id: int) -> Optional[TicketConfig]:
    query = "SELECT * FROM ticket_config WHERE id=$1;"
    record = await bot.pool.fetchrow(query, guild_id)
    if record is not None:
        return TicketConfig.from_record(record, bot)
    return None


async def get_support_role_ids(bot: Mercybot, guild_id: int) -> list[int]:
    query = "SELECT role_id FROM ticket_support_roles WHERE guild_id=$1;"
    rows = await bot.pool.fetch(query, guild_id)
    return [r['role_id'] for r in rows]


async def get_categories(bot: Mercybot, guild_id: int) -> list[dict[str, Any]]:
    query = "SELECT id, name, description FROM ticket_categories WHERE guild_id=$1 ORDER BY id;"
    return await bot.pool.fetch(query, guild_id)


async def is_support_staff(bot: Mercybot, member: discord.Member) -> bool:
    """Check if member has a support role or manage_guild permission."""
    if member.guild_permissions.manage_guild:
        return True
    role_ids = await get_support_role_ids(bot, member.guild.id)
    return any(r.id in role_ids for r in member.roles)


async def log_ticket_event(
    bot: Mercybot,
    guild_id: int,
    *,
    title: str,
    description: str,
    colour: int = 0x2F3136,
) -> None:
    config = await get_ticket_config(bot, guild_id)
    if config is None:
        return
    channel = config.log_channel
    if channel is None:
        return
    embed = discord.Embed(title=title, description=description, colour=colour, timestamp=discord.utils.utcnow())
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass


# ---------------------------------------------------------------------------
# Setup wizard views
# ---------------------------------------------------------------------------

class AddCategoryModal(discord.ui.Modal, title='Add Ticket Category'):
    cat_name = discord.ui.TextInput(label='Category Name', placeholder='e.g. Moderation', max_length=100)
    cat_desc = discord.ui.TextInput(
        label='Description',
        placeholder='e.g. Help with something in the server',
        max_length=100,
        required=False,
    )

    def __init__(self, wizard: TicketSetupView) -> None:
        super().__init__()
        self.wizard = wizard

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name = str(self.cat_name.value).strip()
        desc = str(self.cat_desc.value).strip() or None
        if not name:
            await interaction.response.send_message('Category name cannot be empty.', ephemeral=True)
            return
        if len(self.wizard.categories) >= 25:
            await interaction.response.send_message('Maximum of 25 categories reached.', ephemeral=True)
            return
        # Check for duplicates
        if any(c['name'].lower() == name.lower() for c in self.wizard.categories):
            await interaction.response.send_message(f'Category **{name}** already exists.', ephemeral=True)
            return
        self.wizard.categories.append({'name': name, 'description': desc})
        await interaction.response.defer()
        await self.wizard.refresh(interaction)


class TicketSetupView(discord.ui.View):
    message: discord.Message

    def __init__(self, cog: Tickets, ctx: GuildContext) -> None:
        super().__init__(timeout=600.0)
        self.cog = cog
        self.ctx = ctx
        self.step = 0
        # Collected data
        self.panel_channel: Optional[discord.TextChannel] = None
        self.discord_category: Optional[discord.CategoryChannel] = None
        self.categories: list[dict[str, Optional[str]]] = []
        self.support_roles: list[discord.Role] = []
        self.log_channel: Optional[discord.TextChannel] = None
        self.auto_delete: bool = False
        self._update_items()

    def _update_items(self) -> None:
        self.clear_items()
        if self.step == 0:
            self.add_item(PanelChannelSelect())
        elif self.step == 1:
            self.add_item(DiscordCategorySelect())
        elif self.step == 2:
            self.add_item(AddCategoryButton(self))
            self.add_item(DoneWithCategoriesButton(self))
        elif self.step == 3:
            self.add_item(SupportRoleSelect())
            self.add_item(SkipButton(self))
        elif self.step == 4:
            self.add_item(LogChannelSelect())
            self.add_item(SkipButton(self))
        elif self.step == 5:
            self.add_item(CloseBehaviorSelect())

    def build_embed(self) -> discord.Embed:
        e = discord.Embed(title='Ticket System Setup', colour=0x5865F2)

        steps = [
            'Select the channel where the ticket panel will be posted',
            'Select the Discord category where ticket channels will be created',
            'Add your ticket categories (at least one required)',
            'Select support staff roles (or skip)',
            'Select a logging channel (or skip)',
            'Choose what happens when a ticket is closed',
        ]

        desc_parts: list[str] = []
        for i, label in enumerate(steps):
            if i < self.step:
                desc_parts.append(f'\u2705 ~~{label}~~')
            elif i == self.step:
                desc_parts.append(f'\u27a1\ufe0f **{label}**')
            else:
                desc_parts.append(f'\u2b1c {label}')
        e.description = '\n'.join(desc_parts)

        # Show collected data
        fields: list[str] = []
        if self.panel_channel:
            fields.append(f'**Panel Channel:** {self.panel_channel.mention}')
        if self.discord_category:
            fields.append(f'**Ticket Category:** {self.discord_category.name}')
        if self.categories:
            cat_list = ', '.join(c['name'] for c in self.categories)
            fields.append(f'**Categories:** {cat_list}')
        if self.support_roles:
            role_list = ', '.join(r.mention for r in self.support_roles)
            fields.append(f'**Support Roles:** {role_list}')
        if self.log_channel:
            fields.append(f'**Log Channel:** {self.log_channel.mention}')
        if self.step > 5:
            fields.append(f'**Close Behavior:** {"Auto-delete" if self.auto_delete else "Keep (read-only)"}')

        if fields:
            e.add_field(name='Configuration', value='\n'.join(fields), inline=False)

        return e

    async def refresh(self, interaction: discord.Interaction) -> None:
        self._update_items()
        embed = self.build_embed()
        try:
            await self.message.edit(embed=embed, view=self)
        except discord.HTTPException:
            pass

    async def advance(self, interaction: discord.Interaction) -> None:
        self.step += 1
        if self.step > 5:
            await self.finish(interaction)
            return
        await self.refresh(interaction)

    async def finish(self, interaction: discord.Interaction) -> None:
        self.stop()
        guild_id = self.ctx.guild.id
        pool = self.cog.bot.pool

        # Upsert config
        query = """
            INSERT INTO ticket_config (id, channel_id, log_channel_id, category_id, auto_delete)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (id) DO UPDATE SET
                channel_id = EXCLUDED.channel_id,
                log_channel_id = EXCLUDED.log_channel_id,
                category_id = EXCLUDED.category_id,
                auto_delete = EXCLUDED.auto_delete;
        """
        await pool.execute(
            query,
            guild_id,
            self.panel_channel.id if self.panel_channel else None,
            self.log_channel.id if self.log_channel else None,
            self.discord_category.id if self.discord_category else None,
            self.auto_delete,
        )

        # Clear old categories and re-insert
        await pool.execute("DELETE FROM ticket_categories WHERE guild_id=$1;", guild_id)
        for cat in self.categories:
            await pool.execute(
                "INSERT INTO ticket_categories (guild_id, name, description) VALUES ($1, $2, $3);",
                guild_id, cat['name'], cat.get('description'),
            )

        # Clear old support roles and re-insert
        await pool.execute("DELETE FROM ticket_support_roles WHERE guild_id=$1;", guild_id)
        for role in self.support_roles:
            await pool.execute(
                "INSERT INTO ticket_support_roles (guild_id, role_id) VALUES ($1, $2);",
                guild_id, role.id,
            )

        # Post the panel
        if self.panel_channel:
            await self.cog.post_panel(self.panel_channel, guild_id)

        embed = self.build_embed()
        embed.title = 'Ticket System Setup Complete'
        embed.colour = 0x57F287
        self.clear_items()
        try:
            await self.message.edit(embed=embed, view=self)
        except discord.HTTPException:
            pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message('This setup wizard is not for you.', ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        self.clear_items()
        try:
            await self.message.edit(content='Setup timed out.', view=self)
        except discord.HTTPException:
            pass


class PanelChannelSelect(discord.ui.ChannelSelect):
    def __init__(self) -> None:
        super().__init__(
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            placeholder='Select the panel channel...',
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None and isinstance(self.view, TicketSetupView)
        channel = self.values[0].resolve()
        if channel is None:
            await interaction.response.send_message('Could not resolve that channel.', ephemeral=True)
            return
        self.view.panel_channel = channel  # type: ignore
        await interaction.response.defer()
        await self.view.advance(interaction)


class DiscordCategorySelect(discord.ui.ChannelSelect):
    def __init__(self) -> None:
        super().__init__(
            channel_types=[discord.ChannelType.category],
            placeholder='Select the category for ticket channels...',
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None and isinstance(self.view, TicketSetupView)
        channel = self.values[0].resolve()
        if channel is None:
            await interaction.response.send_message('Could not resolve that category.', ephemeral=True)
            return
        self.view.discord_category = channel  # type: ignore
        await interaction.response.defer()
        await self.view.advance(interaction)


class AddCategoryButton(discord.ui.Button):
    def __init__(self, wizard: TicketSetupView) -> None:
        count = len(wizard.categories)
        label = 'Add Category' if count == 0 else f'Add Category ({count} added)'
        super().__init__(label=label, style=discord.ButtonStyle.blurple)
        self.wizard = wizard

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(AddCategoryModal(self.wizard))


class DoneWithCategoriesButton(discord.ui.Button):
    def __init__(self, wizard: TicketSetupView) -> None:
        super().__init__(label='Done', style=discord.ButtonStyle.green, disabled=len(wizard.categories) == 0)
        self.wizard = wizard

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await self.wizard.advance(interaction)


class SupportRoleSelect(discord.ui.RoleSelect):
    def __init__(self) -> None:
        super().__init__(
            placeholder='Select support staff roles...',
            min_values=1,
            max_values=10,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None and isinstance(self.view, TicketSetupView)
        self.view.support_roles = list(self.values)
        await interaction.response.defer()
        await self.view.advance(interaction)


class SkipButton(discord.ui.Button):
    def __init__(self, wizard: TicketSetupView) -> None:
        super().__init__(label='Skip', style=discord.ButtonStyle.grey)
        self.wizard = wizard

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await self.wizard.advance(interaction)


class LogChannelSelect(discord.ui.ChannelSelect):
    def __init__(self) -> None:
        super().__init__(
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            placeholder='Select the logging channel...',
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None and isinstance(self.view, TicketSetupView)
        channel = self.values[0].resolve()
        if channel is None:
            await interaction.response.send_message('Could not resolve that channel.', ephemeral=True)
            return
        self.view.log_channel = channel  # type: ignore
        await interaction.response.defer()
        await self.view.advance(interaction)


class CloseBehaviorSelect(discord.ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(
                label='Keep channel (read-only)',
                value='keep',
                description='Channel stays visible but locked after close',
            ),
            discord.SelectOption(
                label='Auto-delete channel',
                value='delete',
                description='Channel is deleted shortly after closing',
            ),
        ]
        super().__init__(placeholder='What happens when a ticket is closed?', options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None and isinstance(self.view, TicketSetupView)
        self.view.auto_delete = self.values[0] == 'delete'
        await interaction.response.defer()
        await self.view.advance(interaction)


# ---------------------------------------------------------------------------
# Persistent DynamicItem views
# ---------------------------------------------------------------------------

class TicketCreateSelect(discord.ui.DynamicItem[discord.ui.Select], template=r'ticket:create:(?P<guild_id>[0-9]+)'):
    def __init__(self, guild_id: int, categories: Optional[list[dict[str, Any]]] = None) -> None:
        options = []
        if categories:
            for cat in categories:
                options.append(discord.SelectOption(
                    label=cat['name'],
                    value=str(cat['id']),
                    description=cat.get('description') or None,
                ))
        else:
            options.append(discord.SelectOption(label='Loading...', value='0'))

        super().__init__(
            discord.ui.Select(
                placeholder='Select a category to open a ticket...',
                options=options,
                custom_id=f'ticket:create:{guild_id}',
            )
        )
        self.guild_id = guild_id

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction[Mercybot], item: discord.ui.Select, match: re.Match[str], /
    ):
        guild_id = int(match.group('guild_id'))
        categories = await get_categories(interaction.client, guild_id)
        return cls(guild_id, categories)

    async def interaction_check(self, interaction: discord.Interaction[Mercybot], /) -> bool:
        if interaction.guild_id is None:
            return False
        return True

    async def callback(self, interaction: discord.Interaction[Mercybot]) -> None:
        assert interaction.guild is not None
        assert isinstance(interaction.user, discord.Member)

        cog: Optional[Tickets] = interaction.client.get_cog('Tickets')  # type: ignore
        if cog is None:
            await interaction.response.send_message('Ticket system is currently unavailable.', ephemeral=True)
            return

        category_id = int(self.item.values[0])
        if category_id == 0:
            await interaction.response.send_message('Ticket system is not configured yet.', ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Check if user already has an open ticket
        query = "SELECT id FROM tickets WHERE guild_id=$1 AND author_id=$2 AND status='open' LIMIT 1;"
        existing = await interaction.client.pool.fetchrow(query, interaction.guild_id, interaction.user.id)
        if existing:
            await interaction.followup.send('You already have an open ticket.', ephemeral=True)
            return

        config = await get_ticket_config(interaction.client, interaction.guild_id)
        if config is None:
            await interaction.followup.send('Ticket system is not configured.', ephemeral=True)
            return

        # Get category name
        cat_query = "SELECT name FROM ticket_categories WHERE id=$1;"
        cat_record = await interaction.client.pool.fetchrow(cat_query, category_id)
        cat_name = cat_record['name'] if cat_record else 'Unknown'

        # Create the ticket channel
        discord_category = config.discord_category
        support_role_ids = await get_support_role_ids(interaction.client, interaction.guild_id)

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.guild.me: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                manage_messages=True,
                manage_channels=True,
                embed_links=True,
                read_message_history=True,
            ),
            interaction.user: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True,
            ),
        }

        for role_id in support_role_ids:
            role = interaction.guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    embed_links=True,
                    attach_files=True,
                    read_message_history=True,
                )

        # Insert ticket record first to get the ID
        insert_query = """
            INSERT INTO tickets (guild_id, author_id, category_id, status)
            VALUES ($1, $2, $3, 'open')
            RETURNING id;
        """
        ticket_record = await interaction.client.pool.fetchrow(
            insert_query, interaction.guild_id, interaction.user.id, category_id
        )
        ticket_id = ticket_record['id']

        channel_name = f'ticket-{interaction.user.name}-{ticket_id}'

        try:
            channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=discord_category,
                overwrites=overwrites,
                reason=f'Ticket #{ticket_id} opened by {interaction.user} (ID: {interaction.user.id})',
            )
        except discord.HTTPException as e:
            # Clean up the ticket record
            await interaction.client.pool.execute("DELETE FROM tickets WHERE id=$1;", ticket_id)
            await interaction.followup.send(f'Could not create ticket channel: {e}', ephemeral=True)
            return

        # Update ticket with channel_id
        await interaction.client.pool.execute(
            "UPDATE tickets SET channel_id=$1 WHERE id=$2;", channel.id, ticket_id
        )

        # Send the ticket embed with controls
        embed = discord.Embed(
            title=f'Ticket #{ticket_id} — {cat_name}',
            description=f'Opened by {interaction.user.mention}\nPlease describe your issue and a staff member will assist you.',
            colour=0x5865F2,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f'Ticket #{ticket_id}')

        view = TicketControlView(ticket_id)
        await channel.send(embed=embed, view=view)

        await interaction.followup.send(f'Ticket created: {channel.mention}', ephemeral=True)

        # Log
        await log_ticket_event(
            interaction.client,
            interaction.guild_id,
            title='Ticket Opened',
            description=f'**Ticket:** #{ticket_id}\n**User:** {interaction.user.mention}\n**Category:** {cat_name}\n**Channel:** {channel.mention}',
            colour=0x57F287,
        )


class TicketCloseButton(discord.ui.DynamicItem[discord.ui.Button], template=r'ticket:close:(?P<ticket_id>[0-9]+)'):
    def __init__(self, ticket_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label='Close',
                style=discord.ButtonStyle.red,
                custom_id=f'ticket:close:{ticket_id}',
                emoji='\N{LOCK}',
            )
        )
        self.ticket_id = ticket_id

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction[Mercybot], item: discord.ui.Button, match: re.Match[str], /
    ):
        return cls(int(match.group('ticket_id')))

    async def interaction_check(self, interaction: discord.Interaction[Mercybot], /) -> bool:
        if interaction.guild_id is None:
            return False
        # The ticket author or support staff can close
        return True

    async def callback(self, interaction: discord.Interaction[Mercybot]) -> None:
        assert interaction.guild is not None
        assert isinstance(interaction.user, discord.Member)

        await interaction.response.defer(ephemeral=True)

        query = "SELECT * FROM tickets WHERE id=$1;"
        ticket = await interaction.client.pool.fetchrow(query, self.ticket_id)
        if ticket is None:
            await interaction.followup.send('Ticket not found.', ephemeral=True)
            return

        if ticket['status'] == 'closed':
            await interaction.followup.send('This ticket is already closed.', ephemeral=True)
            return

        # Check permission: author or support staff
        staff = await is_support_staff(interaction.client, interaction.user)
        if interaction.user.id != ticket['author_id'] and not staff:
            await interaction.followup.send('You do not have permission to close this ticket.', ephemeral=True)
            return

        # Update status
        await interaction.client.pool.execute("UPDATE tickets SET status='closed' WHERE id=$1;", self.ticket_id)

        config = await get_ticket_config(interaction.client, interaction.guild_id)

        if config and config.auto_delete:
            # Auto-delete flow
            embed = discord.Embed(
                description=f'\N{LOCK} Ticket closed by {interaction.user.mention} — deleting in 10 seconds.',
                colour=0xED4245,
            )
            await interaction.channel.send(embed=embed)

            # Log before deletion
            await log_ticket_event(
                interaction.client,
                interaction.guild_id,
                title='Ticket Closed & Deleted',
                description=(
                    f'**Ticket:** #{self.ticket_id}\n'
                    f'**Closed by:** {interaction.user.mention}\n'
                    f'**Author:** <@{ticket["author_id"]}>'
                ),
                colour=0xED4245,
            )

            await asyncio.sleep(10)
            try:
                await interaction.channel.delete(reason=f'Ticket #{self.ticket_id} auto-deleted')
            except discord.HTTPException:
                pass
        else:
            # Keep channel, lock it
            channel = interaction.channel
            assert isinstance(channel, discord.TextChannel)

            author = interaction.guild.get_member(ticket['author_id'])
            if author:
                overwrites = channel.overwrites_for(author)
                overwrites.send_messages = False
                try:
                    await channel.set_permissions(
                        author,
                        overwrite=overwrites,
                        reason=f'Ticket #{self.ticket_id} closed',
                    )
                except discord.HTTPException:
                    pass

            embed = discord.Embed(
                description=f'\N{LOCK} Ticket closed by {interaction.user.mention}.',
                colour=0xED4245,
            )
            view = TicketClosedControlView(self.ticket_id)
            await channel.send(embed=embed, view=view)

            # Log
            await log_ticket_event(
                interaction.client,
                interaction.guild_id,
                title='Ticket Closed',
                description=(
                    f'**Ticket:** #{self.ticket_id}\n'
                    f'**Closed by:** {interaction.user.mention}\n'
                    f'**Author:** <@{ticket["author_id"]}>'
                ),
                colour=0xFEE75C,
            )

        await interaction.followup.send('Ticket closed.', ephemeral=True)


class TicketDeleteButton(discord.ui.DynamicItem[discord.ui.Button], template=r'ticket:delete:(?P<ticket_id>[0-9]+)'):
    def __init__(self, ticket_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label='Delete',
                style=discord.ButtonStyle.grey,
                custom_id=f'ticket:delete:{ticket_id}',
                emoji='\N{WASTEBASKET}',
            )
        )
        self.ticket_id = ticket_id

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction[Mercybot], item: discord.ui.Button, match: re.Match[str], /
    ):
        return cls(int(match.group('ticket_id')))

    async def interaction_check(self, interaction: discord.Interaction[Mercybot], /) -> bool:
        if interaction.guild_id is None:
            return False

        assert isinstance(interaction.user, discord.Member)
        staff = await is_support_staff(interaction.client, interaction.user)
        if not staff:
            await interaction.response.send_message('Only support staff can delete tickets.', ephemeral=True)
            return False
        return True

    async def callback(self, interaction: discord.Interaction[Mercybot]) -> None:
        assert interaction.guild is not None

        await interaction.response.defer(ephemeral=True)

        query = "SELECT * FROM tickets WHERE id=$1;"
        ticket = await interaction.client.pool.fetchrow(query, self.ticket_id)
        if ticket is None:
            await interaction.followup.send('Ticket not found.', ephemeral=True)
            return

        # Log before deletion
        created = ticket['created_at']
        duration = discord.utils.utcnow() - created.replace(tzinfo=datetime.timezone.utc) if created else None
        duration_str = str(duration).split('.')[0] if duration else 'Unknown'

        await log_ticket_event(
            interaction.client,
            interaction.guild_id,
            title='Ticket Deleted',
            description=(
                f'**Ticket:** #{self.ticket_id}\n'
                f'**Author:** <@{ticket["author_id"]}>\n'
                f'**Deleted by:** {interaction.user.mention}\n'
                f'**Duration:** {duration_str}'
            ),
            colour=0xED4245,
        )

        # Delete channel
        try:
            await interaction.channel.delete(reason=f'Ticket #{self.ticket_id} deleted by {interaction.user}')
        except discord.HTTPException:
            await interaction.followup.send('Could not delete the channel.', ephemeral=True)
            return

        # Clean up DB
        await interaction.client.pool.execute("DELETE FROM tickets WHERE id=$1;", self.ticket_id)


class TicketReopenButton(discord.ui.DynamicItem[discord.ui.Button], template=r'ticket:reopen:(?P<ticket_id>[0-9]+)'):
    def __init__(self, ticket_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label='Reopen',
                style=discord.ButtonStyle.green,
                custom_id=f'ticket:reopen:{ticket_id}',
                emoji='\N{OPEN LOCK}',
            )
        )
        self.ticket_id = ticket_id

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction[Mercybot], item: discord.ui.Button, match: re.Match[str], /
    ):
        return cls(int(match.group('ticket_id')))

    async def interaction_check(self, interaction: discord.Interaction[Mercybot], /) -> bool:
        if interaction.guild_id is None:
            return False

        assert isinstance(interaction.user, discord.Member)
        staff = await is_support_staff(interaction.client, interaction.user)
        if not staff:
            await interaction.response.send_message('Only support staff can reopen tickets.', ephemeral=True)
            return False
        return True

    async def callback(self, interaction: discord.Interaction[Mercybot]) -> None:
        assert interaction.guild is not None
        assert isinstance(interaction.channel, discord.TextChannel)

        await interaction.response.defer(ephemeral=True)

        query = "SELECT * FROM tickets WHERE id=$1;"
        ticket = await interaction.client.pool.fetchrow(query, self.ticket_id)
        if ticket is None:
            await interaction.followup.send('Ticket not found.', ephemeral=True)
            return

        if ticket['status'] == 'open':
            await interaction.followup.send('This ticket is already open.', ephemeral=True)
            return

        # Reopen
        await interaction.client.pool.execute("UPDATE tickets SET status='open' WHERE id=$1;", self.ticket_id)

        # Restore author send permission
        author = interaction.guild.get_member(ticket['author_id'])
        if author:
            overwrites = interaction.channel.overwrites_for(author)
            overwrites.send_messages = True
            try:
                await interaction.channel.set_permissions(
                    author,
                    overwrite=overwrites,
                    reason=f'Ticket #{self.ticket_id} reopened',
                )
            except discord.HTTPException:
                pass

        embed = discord.Embed(
            description=f'\N{OPEN LOCK} Ticket reopened by {interaction.user.mention}.',
            colour=0x57F287,
        )
        view = TicketControlView(self.ticket_id)
        await interaction.channel.send(embed=embed, view=view)

        await interaction.followup.send('Ticket reopened.', ephemeral=True)

        await log_ticket_event(
            interaction.client,
            interaction.guild_id,
            title='Ticket Reopened',
            description=f'**Ticket:** #{self.ticket_id}\n**Reopened by:** {interaction.user.mention}',
            colour=0x57F287,
        )


# ---------------------------------------------------------------------------
# Non-persistent composite views (use DynamicItems so they persist)
# ---------------------------------------------------------------------------

class TicketControlView(discord.ui.View):
    """Sent inside a ticket channel — Close + Delete buttons."""
    def __init__(self, ticket_id: int) -> None:
        super().__init__(timeout=None)
        self.add_item(TicketCloseButton(ticket_id))
        self.add_item(TicketDeleteButton(ticket_id))


class TicketClosedControlView(discord.ui.View):
    """Sent when a ticket is closed — Reopen + Delete buttons."""
    def __init__(self, ticket_id: int) -> None:
        super().__init__(timeout=None)
        self.add_item(TicketReopenButton(ticket_id))
        self.add_item(TicketDeleteButton(ticket_id))


class TicketPanelView(discord.ui.View):
    """The panel posted in the panel channel — contains the create select."""
    def __init__(self, guild_id: int, categories: Optional[list[dict[str, Any]]] = None) -> None:
        super().__init__(timeout=None)
        self.add_item(TicketCreateSelect(guild_id, categories))


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class Tickets(commands.Cog):
    """Support ticket system."""

    def __init__(self, bot: Mercybot) -> None:
        self.bot = bot
        bot.add_dynamic_items(TicketCreateSelect, TicketCloseButton, TicketDeleteButton, TicketReopenButton)

    async def cog_unload(self) -> None:
        self.bot.remove_dynamic_items(TicketCreateSelect, TicketCloseButton, TicketDeleteButton, TicketReopenButton)

    @property
    def display_emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name='\N{TICKET}')

    async def post_panel(self, channel: discord.TextChannel, guild_id: int) -> None:
        """Post (or re-post) the ticket creation panel in the given channel."""
        categories = await get_categories(self.bot, guild_id)
        if not categories:
            return

        embed = discord.Embed(
            title='Open a Ticket',
            description='Select a category below to open a support ticket.',
            colour=0x5865F2,
        )
        for cat in categories:
            desc = cat.get('description') or 'No description'
            embed.add_field(name=cat['name'], value=desc, inline=False)

        view = TicketPanelView(guild_id, categories)
        await channel.send(embed=embed, view=view)

    # -- Commands --

    @commands.hybrid_group(fallback='setup')
    @commands.guild_only()
    @checks.is_manager()
    async def ticket(self, ctx: GuildContext):
        """Set up or manage the ticket system with a guided wizard."""
        view = TicketSetupView(self, ctx)
        embed = view.build_embed()
        view.message = await ctx.send(embed=embed, view=view)

    @ticket.group(name='category', fallback='list')
    @commands.guild_only()
    @checks.is_manager()
    async def ticket_category(self, ctx: GuildContext):
        """List ticket categories."""
        categories = await get_categories(self.bot, ctx.guild.id)
        if not categories:
            await ctx.send('No ticket categories configured. Run `ticket setup` first.')
            return
        lines = []
        for cat in categories:
            desc = cat.get('description') or ''
            line = f"**{cat['name']}**"
            if desc:
                line += f' — {desc}'
            lines.append(line)
        embed = discord.Embed(title='Ticket Categories', description='\n'.join(lines), colour=0x5865F2)
        await ctx.send(embed=embed)

    @ticket_category.command(name='add')
    @commands.guild_only()
    @checks.is_manager()
    @app_commands.describe(name='Category name', description='Category description shown in the dropdown')
    async def ticket_category_add(self, ctx: GuildContext, name: str, *, description: Optional[str] = None):
        """Add a ticket category."""
        # Ensure config exists
        config = await get_ticket_config(self.bot, ctx.guild.id)
        if config is None:
            await ctx.send('Ticket system not configured yet. Run `ticket setup` first.')
            return

        count_query = "SELECT COUNT(*) FROM ticket_categories WHERE guild_id=$1;"
        count = await self.bot.pool.fetchval(count_query, ctx.guild.id)
        if count >= 25:
            await ctx.send('Maximum of 25 categories reached.')
            return

        query = "INSERT INTO ticket_categories (guild_id, name, description) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING;"
        result = await self.bot.pool.execute(query, ctx.guild.id, name, description)
        if result == 'INSERT 0 0':
            await ctx.send(f'Category **{name}** already exists.')
        else:
            await ctx.send(f'Category **{name}** added.')

    @ticket_category.command(name='remove')
    @commands.guild_only()
    @checks.is_manager()
    @app_commands.describe(name='Category name to remove')
    async def ticket_category_remove(self, ctx: GuildContext, *, name: str):
        """Remove a ticket category."""
        query = "DELETE FROM ticket_categories WHERE guild_id=$1 AND name=$2;"
        result = await self.bot.pool.execute(query, ctx.guild.id, name)
        if result == 'DELETE 0':
            await ctx.send(f'Category **{name}** not found.')
        else:
            await ctx.send(f'Category **{name}** removed.')

    @ticket.command(name='support')
    @commands.guild_only()
    @checks.is_manager()
    @app_commands.describe(action='Add or remove a support role', role='The role')
    @app_commands.choices(action=[
        app_commands.Choice(value='add', name='Add'),
        app_commands.Choice(value='remove', name='Remove'),
    ])
    async def ticket_support(self, ctx: GuildContext, action: str, role: str):
        """Add or remove a support staff role."""
        config = await get_ticket_config(self.bot, ctx.guild.id)
        if config is None:
            await ctx.send('Ticket system not configured yet. Run `ticket setup` first.')
            return

        # Resolve the role from ID string or name
        resolved_role = None
        if role.isdigit():
            resolved_role = ctx.guild.get_role(int(role))
        if resolved_role is None:
            resolved_role = discord.utils.get(ctx.guild.roles, name=role)
        if resolved_role is None:
            await ctx.send('Role not found.')
            return

        if action == 'add':
            query = "INSERT INTO ticket_support_roles (guild_id, role_id) VALUES ($1, $2) ON CONFLICT DO NOTHING;"
            await self.bot.pool.execute(query, ctx.guild.id, resolved_role.id)
            await ctx.send(f'Added {resolved_role.mention} as support staff.')
        elif action == 'remove':
            query = "DELETE FROM ticket_support_roles WHERE guild_id=$1 AND role_id=$2;"
            await self.bot.pool.execute(query, ctx.guild.id, resolved_role.id)
            await ctx.send(f'Removed {resolved_role.mention} from support staff.')

    @ticket_support.autocomplete('role')
    async def _support_role_autocomplete(
        self, interaction: discord.Interaction, current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for support role — searches all guild roles by name."""
        assert interaction.guild is not None
        roles = [
            r for r in interaction.guild.roles
            if r.name != '@everyone' and not r.is_bot_managed()
            and current.lower() in r.name.lower()
        ]
        roles.sort(key=lambda r: r.name.lower())
        return [
            app_commands.Choice(name=r.name, value=str(r.id))
            for r in roles[:25]
        ]

    @ticket.command(name='panel')
    @commands.guild_only()
    @checks.is_manager()
    async def ticket_panel(self, ctx: GuildContext):
        """Re-post the ticket panel in the configured channel."""
        config = await get_ticket_config(self.bot, ctx.guild.id)
        if config is None:
            await ctx.send('Ticket system not configured yet. Run `ticket setup` first.')
            return

        channel = config.panel_channel
        if channel is None:
            await ctx.send('No panel channel configured.')
            return

        await self.post_panel(channel, ctx.guild.id)
        if channel.id != ctx.channel.id:
            await ctx.send(f'Panel posted in {channel.mention}.')
        else:
            await ctx.send('Panel posted.', ephemeral=True)


async def setup(bot: Mercybot):
    await bot.add_cog(Tickets(bot))
