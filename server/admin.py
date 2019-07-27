import pymysql
import server.db as db
from sqlalchemy import func, text

from . import config
from .core import Module
from .db.models import ban
from .exceptions import ClientError

mod = Module()


@mod.route("admin")
async def command_admin(conn, message):
    action = message['action']

    if conn.player.admin:
        if action == "closeFA":
            player = conn.player_service[int(message['user_id'])]
            if player:
                conn._logger.warning(
                    'Administrative action: %s closed game for %s', conn.player, player
                )
                player.lobby_connection.sendJSON({"command": "notice", "style": "kill"})
                player.lobby_connection.sendJSON({
                    "command": "notice",
                    "style": "info",
                    "text": (
                        f"Your game was closed by an administrator ({conn.player.login}). "
                        f"Please refer to our rules for the lobby/game here {config.RULE_LINK}."
                    )
                })

        elif action == "closelobby":
            player = conn.player_service[int(message['user_id'])]
            ban_fail = None
            if player:
                if 'ban' in message:
                    reason = message['ban'].get('reason', 'Unspecified')
                    duration = int(message['ban'].get('duration', 1))
                    period = message['ban'].get('period', 'SECOND').upper()

                    conn._logger.warning(
                        'Administrative action: %s closed client for %s with %s ban (Reason: %s)',
                        conn.player, player, duration, reason
                    )
                    async with db.engine.acquire() as dbconn:
                        try:
                            result = await dbconn.execute("SELECT reason from lobby_ban WHERE idUser=%s AND expires_at > NOW()", (message['user_id']))

                            row = await result.fetchone()
                            if row:
                                ban_fail = row[0]
                            else:
                                if period not in ["SECOND", "DAY", "WEEK", "MONTH"]:
                                    conn._logger.warning('Tried to ban player with invalid period')
                                    raise ClientError(f"Period '{period}' is not allowed!")

                                # NOTE: Text formatting in sql string is only ok
                                # because we just checked it's value
                                await dbconn.execute(
                                    ban.insert().values(
                                        player_id=player.id,
                                        author_id=conn.player.id,
                                        reason=reason,
                                        expires_at=func.date_add(
                                            func.now(),
                                            text(f"interval :duration {period}")
                                        ),
                                        level='GLOBAL'
                                    ),
                                    duration=duration
                                )

                        except pymysql.MySQLError as e:
                            raise ClientError('Your ban attempt upset the database: {}'.format(e))
                else:
                    conn._logger.warning('Administrative action: %s closed client for %s', conn.player, player)
                player.lobby_connection.kick(
                    message=(
                        f"You were kicked from FAF by an administrator ({conn.player.login}). "
                        f"Please refer to our rules for the lobby/game here {config.RULE_LINK}."
                    )
                )
                if ban_fail:
                    raise ClientError("Kicked the player, but he was already banned!")

        elif action == "broadcast":
            for player in conn.player_service:
                try:
                    if player.lobby_connection:
                        player.lobby_connection.send_warning(message.get('message'))
                except Exception as ex:
                    conn._logger.debug("Could not send broadcast message to %s: %s", player, ex)

    elif conn.player.mod:
        if action == "join_channel":
            user_ids = message['user_ids']
            channel = message['channel']

            for user_id in user_ids:
                player = conn.player_service[message[user_id]]
                if player:
                    player.lobby_connection.sendJSON(dict(command="social", autojoin=[channel]))
