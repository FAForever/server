import server.clientmessages as clientmessages
from server.clientmessages import MessageParsingError
import pytest


def test_game_target_message_without_command():
    message = {}
    with pytest.raises(MessageParsingError):
        clientmessages.GameTargetMessage.build(message)


def test_game_target_message_default_arguments_empty():
    command = "fake_command"
    message = {"command": command}
    parsed_message = clientmessages.GameTargetMessage.build(message)

    assert parsed_message == clientmessages.GameTargetMessage(command, [])


def test_game_target_message():
    command = "fake_command"
    arguments = [1, 2, 3]
    message = {"command": command, "args": arguments}
    parsed_message = clientmessages.GameTargetMessage.build(message)

    assert parsed_message == clientmessages.GameTargetMessage(command, arguments)


def test_ping_message():
    parsed_message = clientmessages.PingMessage.build({})
    assert parsed_message.command == "ping"


def test_pong_message():
    parsed_message = clientmessages.PongMessage.build({})
    assert parsed_message.command == "pong"


def test_account_creation_message():
    parsed_message = clientmessages.AccountCreationMessage.build({})
    assert parsed_message.command == "create_account"


def test_coop_list_message():
    parsed_message = clientmessages.CoopListMessage.build({})
    assert parsed_message.command == "coop_list"


def test_matchmaker_info_message():
    parsed_message = clientmessages.MatchmakerInfoMessage.build({})
    assert parsed_message.command == "matchmaker_info"


def test_bottleneck_message():
    parsed_message = clientmessages.BottleneckMessage.build({})
    assert parsed_message.command == "Bottleneck"


def test_iceservers_message():
    parsed_message = clientmessages.ICEServersMessage.build({})
    assert parsed_message.command == "ice_servers"


def test_social_remove_message_missing_fields():
    message = {"command": "social_remove"}
    with pytest.raises(MessageParsingError):
        clientmessages.SocialRemoveMessage.build(message)


def test_social_remove_message():
    friend_message = {"command": "social_remove", "friend": 1}
    foe_message = {"command": "social_remove", "foe": 2}

    parsed_friend_message = clientmessages.SocialRemoveMessage.build(friend_message)
    parsed_foe_message = clientmessages.SocialRemoveMessage.build(foe_message)

    assert parsed_friend_message.id_to_remove == 1
    assert parsed_foe_message.id_to_remove == 2


def test_social_remove_message_if_both_specified_remove_friend():
    friend_id, foe_id = 1, 2
    ambiguous_message = {"command": "social_remove", "friend": friend_id, "foe": foe_id}
    parsed_message = clientmessages.SocialRemoveMessage.build(ambiguous_message)

    assert parsed_message.id_to_remove == friend_id


def test_social_add_message_missing_fields():
    message = {"command": "social_add"}
    with pytest.raises(MessageParsingError):
        clientmessages.SocialAddMessage.build(message)


def test_social_add_message():
    friend_message = {"command": "social_add", "friend": 1}
    foe_message = {"command": "social_add", "foe": 2}

    parsed_friend_message = clientmessages.SocialAddMessage.build(friend_message)
    parsed_foe_message = clientmessages.SocialAddMessage.build(foe_message)

    assert parsed_friend_message.id_to_add == 1
    assert parsed_friend_message.adding_a_friend is True

    assert parsed_foe_message.id_to_add == 2
    assert parsed_foe_message.adding_a_friend is False


def test_admin_message_missing_fields():
    message = {"command": "admin"}
    with pytest.raises(MessageParsingError):
        clientmessages.AdminMessage.build(message)

    message = {"command": "admin", "action": "closeFA"}
    with pytest.raises(MessageParsingError):
        clientmessages.AdminMessage.build(message)

    message = {"command": "admin", "action": "closelobby"}
    with pytest.raises(MessageParsingError):
        clientmessages.AdminMessage.build(message)

    message = {"command": "admin", "action": "join_channel"}
    with pytest.raises(MessageParsingError):
        clientmessages.AdminMessage.build(message)

    message = {"command": "admin", "action": "join_channel", "user_ids": [1, 2, 3]}
    with pytest.raises(MessageParsingError):
        clientmessages.AdminMessage.build(message)

    message = {"command": "admin", "action": "join_channel", "channel": "channel"}
    with pytest.raises(MessageParsingError):
        clientmessages.AdminMessage.build(message)


def test_admin_message_action_closeFA():
    user_id = 1
    message = {"command": "admin", "action": "closeFA", "user_id": user_id}
    parsed_message = clientmessages.AdminMessage.build(message)

    assert parsed_message.command == "admin"
    assert parsed_message.action == "closeFA"
    assert parsed_message.target_user_id == user_id


def test_admin_message_action_closelobby():
    user_id = 1
    message = {"command": "admin", "action": "closelobby", "user_id": user_id}
    parsed_message = clientmessages.AdminMessage.build(message)

    assert parsed_message.command == "admin"
    assert parsed_message.action == "closelobby"
    assert parsed_message.target_user_id == user_id


def test_admin_message_action_broadcast():
    announcement = "Good luck, Commander."
    message = {"command": "admin", "action": "broadcast", "message": announcement}
    parsed_message = clientmessages.AdminMessage.build(message)

    assert parsed_message.command == "admin"
    assert parsed_message.action == "broadcast"
    assert parsed_message.broadcast_message == announcement


def test_admin_message_action_join_channel():
    channel_name = "test_channel"
    channel_users = [1, 2, 3]
    message = {
        "command": "admin",
        "action": "join_channel",
        "channel": channel_name,
        "user_ids": channel_users,
    }
    parsed_message = clientmessages.AdminMessage.build(message)

    assert parsed_message.command == "admin"
    assert parsed_message.action == "join_channel"
    assert parsed_message.channel == channel_name
    assert parsed_message.channel_users == channel_users


def test_admin_message_ban_defaults():
    message = {"command": "admin", "action": "closelobby", "user_id": 0, "ban": {}}
    parsed_message = clientmessages.AdminMessage.build(message)

    assert parsed_message.ban_data == {
        "reason": "Unspecified",
        "duration": 1,
        "period": "SECOND",
    }


def test_admin_message_ban():
    ban_reason = "test ban"
    ban_duration = 99
    ban_period = "Month"
    message = {
        "command": "admin",
        "action": "closelobby",
        "user_id": 0,
        "ban": {"reason": ban_reason, "duration": ban_duration, "period": ban_period},
    }
    parsed_message = clientmessages.AdminMessage.build(message)

    assert parsed_message.ban_data == {
        "reason": ban_reason,
        "duration": ban_duration,
        "period": ban_period.upper(),
    }


def test_admin_message_invalid_action():
    message = {"command": "admin", "action": "invalid"}
    with pytest.raises(MessageParsingError):
        clientmessages.AdminMessage.build(message)


def test_hello_message_missing_fields():
    message = {"command": "hello"}
    with pytest.raises(MessageParsingError):
        clientmessages.HelloMessage.build(message)


def test_hello_message():
    login, password, uid = "foo", "bar", 0
    message = {
        "command": "hello",
        "login": login,
        "password": password,
        "unique_id": uid,
    }
    parsed_message = clientmessages.HelloMessage.build(message)

    assert parsed_message.login == login
    assert parsed_message.password == password
    assert parsed_message.unique_id == uid


def test_hello_message_login_stripped():
    login, password, uid = "foo   ", "bar", 0
    message = {
        "command": "hello",
        "login": login,
        "password": password,
        "unique_id": uid,
    }
    parsed_message = clientmessages.HelloMessage.build(message)

    assert parsed_message.login == login.strip()


def test_game_matchmaking_message():
    mod, state, faction = "faf", "start", 2
    message = {
        "command": "game_matchmaking",
        "mod": mod,
        "state": state,
        "faction": faction,
    }
    parsed_message = clientmessages.GameMatchmakingMessage.build(message)

    assert parsed_message.mod == mod
    assert parsed_message.state == state
    assert parsed_message.faction == faction


def test_game_matchmaking_message_defaults():
    message = {"command": "game_matchmaking", "state": "start"}
    parsed_message = clientmessages.GameMatchmakingMessage.build(message)

    assert parsed_message.mod == "ladder1v1"
    assert parsed_message.faction == "uef"


def test_game_matchmaking_message_invalid_state():
    message = {"command": "game_matchmaking", "state": "invalid"}
    with pytest.raises(MessageParsingError):
        clientmessages.GameMatchmakingMessage.build(message)


def test_game_host_message():
    title, mod, mapname, password, visibility = (
        "faketitle",
        "fakemod",
        "fakemap",
        "fakepwd",
        "fakevisibility",
    )
    message = {
        "command": "host_game",
        "title": title,
        "mod": mod,
        "mapname": mapname,
        "password": password,
        "visibility": visibility,
    }

    parsed_message = clientmessages.GameHostMessage.build(message)

    assert parsed_message.title == title
    assert parsed_message.mod == mod
    assert parsed_message.mapname == mapname
    assert parsed_message.password == password
    assert parsed_message.visibility == visibility


def test_game_host_message_defaults():
    message = {"command": "host_game"}

    parsed_message = clientmessages.GameHostMessage.build(message)

    assert parsed_message.title is None
    assert parsed_message.mod == "faf"
    assert parsed_message.mapname == "scmp_007"
    assert parsed_message.password is None
    assert parsed_message.visibility is None


def test_game_host_message_empty_mod_string_is_replaced_by_default():
    message = {"command": "host_game", "mod": ""}

    parsed_message = clientmessages.GameHostMessage.build(message)

    assert parsed_message.mod == "faf"


def test_game_join_message():
    uid, password = 0, "foo"
    message = {"command": "game_join", "uid": uid, "password": password}

    parsed_message = clientmessages.GameJoinMessage.build(message)

    assert parsed_message.uid == uid
    assert parsed_message.password == password


def test_game_join_password_default():
    message = {"command": "game_join", "uid": 1}

    parsed_message = clientmessages.GameJoinMessage.build(message)

    assert parsed_message.password is None


def test_game_join_uid_accepts_string():
    message = {"command": "game_join", "uid": "1"}

    parsed_message = clientmessages.GameJoinMessage.build(message)

    assert parsed_message.uid == 1


def test_game_join_missing_uid():
    message = {"command": "game_join"}

    with pytest.raises(MessageParsingError):
        clientmessages.GameJoinMessage.build(message)


def test_modvault_message_type_start():
    message = {"command": "modvault", "type": "start"}
    parsed_message = clientmessages.ModvaultMessage.build(message)

    assert parsed_message.type_field == "start"
    assert parsed_message.uid is None


@pytest.mark.parametrize("type_string", ["like", "download"])
def test_modvault_message_other_type(type_string):
    uid = 0
    message = {"command": "modvault", "type": type_string, "uid": uid}
    parsed_message = clientmessages.ModvaultMessage.build(message)

    assert parsed_message.type_field == type_string
    assert parsed_message.uid == uid


@pytest.mark.parametrize("type_string", ["like", "download"])
def test_modvault_message_other_types_need_uid(type_string):
    message = {"command": "modvault", "type": type_string}
    with pytest.raises(MessageParsingError):
        clientmessages.ModvaultMessage.build(message)


def test_modvault_message_invalid_type():
    message = {"command": "modvault", "type": "invalid"}
    with pytest.raises(MessageParsingError):
        clientmessages.ModvaultMessage.build(message)


def test_restore_game_message():
    game_id = 0
    message = {"command": "game_join", "game_id": game_id}

    parsed_message = clientmessages.RestoreGameSessionMessage.build(message)

    assert parsed_message.game_id == game_id


def test_restore_game_id_accepts_string():
    message = {"command": "game_join", "game_id": "1"}

    parsed_message = clientmessages.RestoreGameSessionMessage.build(message)

    assert parsed_message.game_id == 1


def test_restore_game_missing_game_id():
    message = {"command": "game_join"}

    with pytest.raises(MessageParsingError):
        clientmessages.RestoreGameSessionMessage.build(message)


def test_avatar_message_list():
    message = {"command": "avatar", "action": "list_avatar"}
    parsed_message = clientmessages.AvatarMessage.build(message)

    assert parsed_message.action == "list_avatar"


def test_avatar_message_select():
    url = "fake avatar url"
    message = {"command": "avatar", "action": "select", "avatar": url}
    parsed_message = clientmessages.AvatarMessage.build(message)

    assert parsed_message.action == "select"
    assert parsed_message.url == url


def test_avatar_message_defaults():
    message = {"command": "avatar"}
    parsed_message = clientmessages.AvatarMessage.build(message)
    assert parsed_message.action == "list_avatar"

    message = {"command": "avatar", "action": "select"}
    parsed_message = clientmessages.AvatarMessage.build(message)
    assert parsed_message.url is None


def test_avatar_message_url_accepts_null():
    message = {"command": "avatar", "action": "select", "avatar": "null"}
    parsed_message = clientmessages.AvatarMessage.build(message)

    assert parsed_message.url is None


def test_avatar_message_invalid_action():
    message = {"command": "avatar", "action": "invalid"}
    with pytest.raises(MessageParsingError):
        clientmessages.AvatarMessage.build(message)


def test_ask_session_message():
    agent, version = "downlord", "0.0.1"
    message = {"command": "ask_session", "user_agent": agent, "version": version}
    parsed_message = clientmessages.AskSessionMessage.build(message)

    assert parsed_message.user_agent == agent
    assert parsed_message.version == version


def test_ask_session_message_defaults():
    message = {"command": "ask_session"}
    parsed_message = clientmessages.AskSessionMessage.build(message)

    assert parsed_message.user_agent is None
    assert parsed_message.version is None


def test_messageparser_game_target():
    message = {"command": "fake", "target": "game"}
    parsed_message = clientmessages.MessageParser.parse(message)

    assert isinstance(parsed_message, clientmessages.GameTargetMessage)


def test_messageparser_connectivity_target():
    message = {"target": "connectivity"}
    parsed_message = clientmessages.MessageParser.parse(message)

    assert isinstance(parsed_message, clientmessages.ConnectivityTargetMessage)


@pytest.mark.xfail
def test_messageparser_no_target_goes_to_lobby():
    message = {"command": "ping"}
    parsed_message = clientmessages.MessageParser.parse(message)

    assert issubclass(parsed_message.__class__, clientmessages.LobbyTargetMessage)


@pytest.mark.xfail
def test_messageparser_invalid_target_goes_to_lobby():
    message = {"command": "ping", "target": "invalid"}
    parsed_message = clientmessages.MessageParser.parse(message)

    assert issubclass(parsed_message.__class__, clientmessages.LobbyTargetMessage)


def test_messageparser_parse_command():
    message = {"command": "ping"}
    parsed_command = clientmessages.MessageParser.parse_command(message)
    assert parsed_command is clientmessages.CommandField.ping


def test_messageparser_parse_invalid_command():
    message = {"command": "invalid"}
    with pytest.raises(MessageParsingError):
        clientmessages.MessageParser.parse_command(message)


def test_messageparser_parse_missing():
    message = {}
    with pytest.raises(MessageParsingError):
        clientmessages.MessageParser.parse_command(message)
