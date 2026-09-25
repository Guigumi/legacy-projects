import asyncio
import sqlite3
import sys
from pathlib import Path

# Adicionar src ao path para poder importar core.utils.xp_calc
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.utils.xp_calc import calculate_level

DB_PATH = Path(__file__).parent.parent / "src" / "data" / "luna.db"

async def main():
    if not DB_PATH.exists():
        print(f"Banco de dados não encontrado: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Buscar configuração de base xp por servidor
    cursor.execute("SELECT guild_id, xp_per_level FROM xp_config")
    xp_configs = {row[0]: row[1] for row in cursor.fetchall()}

    cursor.execute("SELECT guild_id, user_id, xp, level FROM user_data")
    users = cursor.fetchall()

    updates = []
    for guild_id, user_id, xp, current_level in users:
        base = xp_configs.get(guild_id, 100)
        new_level = calculate_level(xp, base)
        
        if new_level != current_level:
            updates.append((new_level, guild_id, user_id))

    if updates:
        cursor.executemany("UPDATE user_data SET level = ? WHERE guild_id = ? AND user_id = ?", updates)
        conn.commit()
        print(f"{len(updates)} usuários tiveram seus níveis recalculados.")
    else:
        print("Nenhum usuário precisou ter o nível recalculado.")

    conn.close()

if __name__ == "__main__":
    asyncio.run(main())
