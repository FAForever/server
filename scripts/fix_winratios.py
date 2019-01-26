import asyncio
import csv
import sys

from server import config
from server.db import connect


async def main(loop, write_to_db: bool):
    db_pool = await connect(
        loop=loop,
        host=config.DB_SERVER,
        port=config.DB_PORT,
        user=config.DB_LOGIN,
        password=config.DB_PASSWORD,
        db=config.DB_NAME
    )

    async with db_pool.get() as conn:
        cursor = await conn.cursor()

        # Count players ladder wins by reading scores from game_stats table.
        # This assumes wins have score == 1 and losses/draws have score == 0
        sql = """
            SELECT
                count(score) totalCount,
                sum(case when score = 1 then 1 else 0 end) winCount,
                gps.playerId,
                l.login
            FROM game_stats as gs
                INNER JOIN game_player_stats as gps on gs.id = gps.gameId
                INNER JOIN game_featuredMods as gfm on gfm.id = gs.gameMod
                INNER JOIN login as l on l.id = gps.playerId
            WHERE gfm.gamemod = 'ladder1v1'
            GROUP BY gps.playerId
        """
        await cursor.execute(sql)
        rows = await cursor.fetchall()

        if write_to_db:
            # Update players aggregate ladder stats
            await cursor.executemany("""
                UPDATE ladder1v1_rating
                SET numGames = %s, winGames = %s
                WHERE id = %s
            """, map(lambda row: row[:3], rows))
        else:
            with open("player_win_ratios.csv", 'w') as f:
                writer = csv.writer(f)
                writer.writerow(['numGames', 'winGames', 'playerId', 'login'])
                writer.writerows(rows)

    db_pool.close()
    await db_pool.wait_closed()


if __name__ == '__main__':
    write_to_db = False
    if len(sys.argv) > 1:
        if sys.argv[1] == "--update-database":
            write_to_db = True
    elif sys.argv:
        print(f"python3 {sys.argv[0]} --update-database\n\nTo update the ladder1v1 results directly")
    loop = asyncio.get_event_loop()

    loop.run_until_complete(main(loop, write_to_db))

    loop.close()
