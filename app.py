import os
import discord
from discord import app_commands
from discord.ui import Button, View
import aiohttp
import asyncio
from typing import Optional
from datetime import datetime

# Bot setup
intents = discord.Intents.default()
intents.message_content = True  # Required for !commands
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# API config
BASE_URL = "https://api.warframe.market/v2"
PLATFORM = "all"  # Cross-platform trading supported

class WFMBot:
    def __init__(self):
        self.session = None
        self.items_cache = {}
    
    async def init_session(self):
        """Initialize aiohttp session"""
        if not self.session:
            self.session = aiohttp.ClientSession(headers={
                "Platform": PLATFORM,
                "Language": "en"
            })
    
    async def close_session(self):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()
    
    async def get_all_items(self):
        """Fetch all tradable items and cache them"""
        if self.items_cache:
            return self.items_cache
        
        await self.init_session()
        async with self.session.get(f"{BASE_URL}/items") as resp:
            if resp.status == 200:
                data = await resp.json()
                # Create slug -> item mapping for easy lookup
                for item in data['data']:
                    self.items_cache[item['slug']] = item
                return self.items_cache
            return {}
    
    def find_item_slug(self, search_term: str) -> Optional[str]:
        """Find item slug from user input"""
        search_lower = search_term.lower().replace(" ", "_")
        
        # Direct match
        if search_lower in self.items_cache:
            return search_lower
        
        # Partial match
        for slug, item in self.items_cache.items():
            item_name = item.get('i18n', {}).get('en', {}).get('name', '').lower()
            if search_term.lower() in item_name:
                return slug
        
        return None
    
    async def get_top_orders(self, slug: str, rank: Optional[int] = None):
        """Get top 5 buy/sell orders for an item"""
        await self.init_session()
        
        # Build URL with rank parameter if provided
        url = f"{BASE_URL}/orders/item/{slug}/top"
        params = {}
        if rank is not None:
            params['rank'] = rank
        
        async with self.session.get(url, params=params) as resp:
            if resp.status == 200:
                return await resp.json()
            return None

bot_instance = WFMBot()

class RefreshView(View):
    """View with refresh button and auto-update toggle"""
    def __init__(self, slug: str, item_name: str, rank: Optional[int], max_rank: int):
        super().__init__(timeout=300)  # 5 min timeout
        self.slug = slug
        self.item_name = item_name
        self.rank = rank
        self.max_rank = max_rank
        self.auto_refresh = False
        self.message = None
        self.task = None
    
    async def update_embed(self, interaction: discord.Interaction = None):
        """Fetch new data and update embed"""
        orders_data = await bot_instance.get_top_orders(self.slug, self.rank)
        
        if not orders_data or not orders_data.get('data'):
            return None
        
        sell_orders = orders_data['data'].get('sell', [])
        if not sell_orders:
            return None
        
        # Build embed with sick design
        embed = discord.Embed(
            color=0x0a0e27,  # Deep space blue
            description=""
        )
        
        # Epic header with item name
        rank_display = f" `R{self.rank}`" if self.rank is not None else ""
        header = f"## ⚡ {self.item_name.upper()}{rank_display}\n"
        header += "```═══════════════════════════════════════════════```"
        embed.description = header
        
        # Listings with clean formatting
        listings_text = ""
        
        for i, order in enumerate(sell_orders, 1):
            user = order['user']
            username = user['ingameName']
            price = order['platinum']
            status = user['status']
            order_rank = order.get('rank', 0)
            quantity = order.get('quantity', 1)
            
            # Status emoji
            if status == "ingame":
                status_emoji = "🟢"
            elif status == "online":
                status_emoji = "🟡"
            else:
                status_emoji = "⚫"
            
            # Rank badge
            rank_badge = f"**R{order_rank}**" if 'rank' in order and self.max_rank > 0 else ""
            
            # Quantity badge
            qty_badge = f"**×{quantity}**" if quantity > 1 else ""
            
            # Build listing line with badges
            badges = " ".join(filter(None, [rank_badge, qty_badge]))
            badges_display = f" {badges}" if badges else ""
            
            listings_text += f"{status_emoji} **`{price}p`** • `{username}`{badges_display}\n"
        
        embed.add_field(
            name="",
            value=listings_text,
            inline=False
        )
        
        # Divider
        embed.add_field(
            name="",
            value="```─────────────────────────────────────────────```",
            inline=False
        )
        
        # Whisper commands with extra spacing
        whispers_text = "💬 **WHISPER COMMANDS** (click to copy)\n\n"
        for i, order in enumerate(sell_orders, 1):
            user = order['user']
            username = user['ingameName']
            price = order['platinum']
            order_rank = order.get('rank', 0)
            
            rank_text = f" (rank {order_rank})" if 'rank' in order and self.max_rank > 0 else ""
            whisper = f"/w {username} Hi! I want to buy: \"{self.item_name}{rank_text}\" for {price} platinum. (warframe.market)"
            
            whispers_text += f"**`[{i}]`**\n```{whisper}```\n"
        
        embed.add_field(
            name="",
            value=whispers_text,
            inline=False
        )
        
        # Footer with timestamp
        status_indicator = "🔄 AUTO-REFRESH" if self.auto_refresh else "⚡ LIVE"
        embed.set_footer(
            text=f"{status_indicator} • CROSS-PLATFORM • WARFRAME.MARKET",
            icon_url="https://warframe.market/static/assets/icons/wfmarket_small.png"
        )
        embed.timestamp = datetime.utcnow()
        
        return embed
    
    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.primary)
    async def refresh_button(self, interaction: discord.Interaction, button: Button):
        """Manual refresh button"""
        await interaction.response.defer()
        embed = await self.update_embed(interaction)
        if embed:
            await interaction.message.edit(embed=embed, view=self)
    
    @discord.ui.button(label="⏸️ Auto-Update OFF", style=discord.ButtonStyle.secondary)
    async def toggle_auto_refresh(self, interaction: discord.Interaction, button: Button):
        """Toggle auto-refresh"""
        await interaction.response.defer()
        self.auto_refresh = not self.auto_refresh
        
        if self.auto_refresh:
            button.label = "⏸️ Auto-Update ON"
            button.style = discord.ButtonStyle.success
            # Start auto-refresh task
            if self.task:
                self.task.cancel()
            self.task = asyncio.create_task(self.auto_refresh_loop())
        else:
            button.label = "⏸️ Auto-Update OFF"
            button.style = discord.ButtonStyle.secondary
            # Stop auto-refresh task
            if self.task:
                self.task.cancel()
                self.task = None
        
        embed = await self.update_embed(interaction)
        if embed:
            await interaction.message.edit(embed=embed, view=self)
    
    async def auto_refresh_loop(self):
        """Auto-refresh every 30 seconds"""
        try:
            while self.auto_refresh:
                await asyncio.sleep(30)
                if self.message and self.auto_refresh:
                    embed = await self.update_embed()
                    if embed:
                        await self.message.edit(embed=embed, view=self)
        except asyncio.CancelledError:
            pass
    
    async def on_timeout(self):
        """Disable buttons on timeout"""
        for item in self.children:
            item.disabled = True
        if self.message:
            await self.message.edit(view=self)
        if self.task:
            self.task.cancel()


async def handle_price_check(channel, item: str, rank: Optional[int] = None):
    """Shared logic for price checking (used by both slash and text commands)"""
    # Find item slug
    slug = bot_instance.find_item_slug(item)
    
    if not slug:
        await channel.send(f"❌ Item not found: `{item}`")
        return
    
    # Get item info
    item_data = bot_instance.items_cache.get(slug)
    item_name = item_data.get('i18n', {}).get('en', {}).get('name', slug)
    max_rank = item_data.get('maxRank', 0)
    
    # Validate rank
    if rank is not None and (rank < 0 or rank > max_rank):
        await channel.send(f"❌ Invalid rank. `{item_name}` has ranks 0-{max_rank}")
        return
    
    # Create view with buttons
    view = RefreshView(slug, item_name, rank, max_rank)
    embed = await view.update_embed()
    
    if not embed:
        await channel.send(f"❌ No sell orders found for `{item_name}`")
        return
    
    message = await channel.send(embed=embed, view=view)
    view.message = message

@client.event
async def on_ready():
    """Bot startup"""
    print(f'Logged in as {client.user}')
    await bot_instance.init_session()
    print('Loading items cache...')
    await bot_instance.get_all_items()
    print(f'Cached {len(bot_instance.items_cache)} items')
    await tree.sync()
    print('Bot ready!')

@client.event
async def on_message(message):
    """Handle text commands: !price, !buy, !p"""
    if message.author == client.user:
        return
    
    content = message.content.strip()
    
    # Check for command aliases
    if content.startswith(('!price ', '!buy ', '!p ')):
        # Parse command
        parts = content.split(maxsplit=1)
        if len(parts) < 2:
            await message.channel.send("❌ Usage: `!price <item>` or `!price <item> <rank>`")
            return
        
        args = parts[1].strip().split()
        item_parts = []
        rank = None
        
        # Parse item name and optional rank
        for arg in args:
            if arg.isdigit() and rank is None:
                rank = int(arg)
            else:
                item_parts.append(arg)
        
        if not item_parts:
            await message.channel.send("❌ Please specify an item name")
            return
        
        item = ' '.join(item_parts)
        await handle_price_check(message.channel, item, rank)

@tree.command(name="price", description="Get warframe.market prices for an item")
@app_commands.describe(
    item="Item name (e.g., 'blind rage', 'primed continuity')",
    rank="Mod rank (0-10, optional)"
)
async def price(interaction: discord.Interaction, item: str, rank: Optional[int] = None):
    """Price check command"""
    await interaction.response.defer()
    await handle_price_check(interaction.channel, item, rank)

@client.event
async def on_close():
    """Cleanup on bot shutdown"""
    await bot_instance.close_session()

# Run bot
if __name__ == "__main__":
    # This looks for your token in the host's settings instead of the code
    TOKEN = os.getenv('DISCORD_TOKEN')
    
    if TOKEN:
        client.run(TOKEN)
    else:
        print("❌ Error: 'DISCORD_TOKEN' not found in environment variables!")
