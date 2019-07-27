import server.db as db
from sqlalchemy import and_

from .core import Module
from .db.models import friends_and_foes

mod = Module()


@mod.route("social_add")
async def command_social_add(conn, message):
    if "friend" in message:
        status = "FRIEND"
        subject_id = message["friend"]
    elif "foe" in message:
        status = "FOE"
        subject_id = message["foe"]
    else:
        return

    async with db.engine.acquire() as dbconn:
        await dbconn.execute(friends_and_foes.insert().values(
            user_id=conn.player.id,
            status=status,
            subject_id=subject_id,
        ))


@mod.route("social_remove")
async def command_social_remove(conn, message):
    if "friend" in message:
        subject_id = message["friend"]
    elif "foe" in message:
        subject_id = message["foe"]
    else:
        conn.abort("No-op social_remove.")
        return

    async with db.engine.acquire() as dbconn:
        await dbconn.execute(friends_and_foes.delete().where(and_(
            friends_and_foes.c.user_id == conn.player.id,
            friends_and_foes.c.subject_id == subject_id
        )))


@mod.route("avatar")
async def command_avatar(conn, message):
    action = message['action']

    if action == "list_avatar":
        avatarList = []

        async with db.engine.acquire() as dbconn:
            result = await dbconn.execute(
                "SELECT url, tooltip FROM `avatars` "
                "LEFT JOIN `avatars_list` ON `idAvatar` = `avatars_list`.`id` WHERE `idUser` = %s", (conn.player.id,))

            async for row in result:
                avatar = {"url": row["url"], "tooltip": row["tooltip"]}
                avatarList.append(avatar)

            if avatarList:
                conn.sendJSON({"command": "avatar", "avatarlist": avatarList})

    elif action == "select":
        avatar = message['avatar']

        async with db.engine.acquire() as dbconn:
            await dbconn.execute(
                "UPDATE `avatars` SET `selected` = 0 WHERE `idUser` = %s", (conn.player.id, ))
            if avatar is not None:
                await dbconn.execute(
                    "UPDATE `avatars` SET `selected` = 1 WHERE `idAvatar` ="
                    "(SELECT id FROM avatars_list WHERE avatars_list.url = %s) and "
                    "`idUser` = %s", (avatar, conn.player.id))
    else:
        raise KeyError('invalid action')
