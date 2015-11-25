from faf.factions import Faction
from server.games import Game
from server.players import Player
from server.stats.achievement_service import *
from server.stats.event_service import *
from server.stats.unit import *


@with_logger
class GameStatsService:
    def __init__(self, event_service: EventService, achievement_service: AchievementService):
        self._event_service = event_service
        self._achievement_service = achievement_service

    async def process_game_stats(self, player: Player, game: Game, stats_json):
        stats = None
        number_of_humans = 0

        for army_stats in json.loads(stats_json)['stats']:
            if army_stats['type'] == 'AI' and army_stats['name'] != 'civilian':
                self._logger.debug("Ignoring AI game reported by {}".format(player.login))
                return

            if army_stats['type'] == 'Human':
                number_of_humans += 1

            if army_stats['name'] == player.login:
                stats = army_stats

        if number_of_humans < 2:
            self._logger.debug("Ignoring single player game reported by {}".format(player.login))
            return

        if stats is None:
            self._logger.warn("Player {} reported foreign game stats".format(player.login))
            return

        self._logger.info("Processing game stats for player: {}".format(player.login))

        faction = stats['faction']
        # Stores achievements to batch update
        a_queue = []
        # Stores events to batch update
        e_queue = []
        survived = stats['units']['cdr']['lost'] == 0
        unit_stats = stats['units']

        if survived and game.game_mode == 'ladder1v1':
            self._unlock(ACH_FIRST_SUCCESS, a_queue)

        self._increment(ACH_NOVICE, 1, a_queue)
        self._increment(ACH_JUNIOR, 1, a_queue)
        self._increment(ACH_SENIOR, 1, a_queue)
        self._increment(ACH_VETERAN, 1, a_queue)
        self._increment(ACH_ADDICT, 1, a_queue)

        self._category_stats(unit_stats, survived, a_queue, e_queue)
        self._faction_played(faction, survived, a_queue, e_queue)
        self._killed_acus(unit_stats['cdr']['killed'], survived, a_queue)
        self._built_mercies(self._count(unit_stats, lambda x: x['built'], Unit.MERCY), a_queue)
        self._built_fire_beetles(self._count(unit_stats, lambda x: x['built'], Unit.FIRE_BEETLE), a_queue)
        self._built_salvations(self._count(unit_stats, lambda x: x['built'], Unit.SALVATION), survived, a_queue)
        self._built_yolona_oss(self._count(unit_stats, lambda x: x['built'], Unit.YOLONA_OSS), survived, a_queue)
        self._built_paragons(self._count(unit_stats, lambda x: x['built'], Unit.PARAGON), survived, a_queue)
        self._built_atlantis(self._count(unit_stats, lambda x: x['built'], Unit.ATLANTIS), a_queue)
        self._built_tempests(self._count(unit_stats, lambda x: x['built'], Unit.TEMPEST), a_queue)
        self._built_scathis(self._count(unit_stats, lambda x: x['built'], Unit.SCATHIS), survived, a_queue)
        self._built_mavors(self._count(unit_stats, lambda x: x['built'], Unit.MAVOR), survived, a_queue)
        self._built_czars(self._count(unit_stats, lambda x: x['built'], Unit.CZAR), a_queue)
        self._built_ahwassas(self._count(unit_stats, lambda x: x['built'], Unit.AHWASSA), a_queue)
        self._built_ythothas(self._count(unit_stats, lambda x: x['built'], Unit.YTHOTHA), a_queue)
        self._built_fatboys(self._count(unit_stats, lambda x: x['built'], Unit.FATBOY), a_queue)
        self._built_monkeylords(self._count(unit_stats, lambda x: x['built'], Unit.MONKEYLORD), a_queue)
        self._built_galactic_colossus(self._count(unit_stats, lambda x: x['built'], Unit.GALACTIC_COLOSSUS), a_queue)
        self._built_soul_rippers(self._count(unit_stats, lambda x: x['built'], Unit.SOUL_RIPPER), a_queue)
        self._built_megaliths(self._count(unit_stats, lambda x: x['built'], Unit.MEGALITH), a_queue)
        self._built_asfs(self._count(unit_stats, lambda x: x['built'], *ASFS), a_queue)
        self._built_transports(unit_stats['transportation']['built'], a_queue)
        self._built_sacus(unit_stats['sacu']['built'], a_queue)
        self._lowest_acu_health(self._count(unit_stats, lambda x: x.get('lowest_health', 0), *ACUS), survived, a_queue)

        updated_achievements = await self._achievement_service.execute_batch_update(player.id, a_queue)
        await self._event_service.execute_batch_update(player.id, e_queue)

        player.lobby_connection.send_updated_achievements(updated_achievements)

    def _category_stats(self, unit_stats, survived, achievements_queue, events_queue):
        built_air = unit_stats['air']['built']
        built_land = unit_stats['land']['built']
        built_naval = unit_stats['naval']['built']
        built_experimentals = unit_stats['experimental']['built']

        self._record_event(EVENT_BUILT_AIR_UNITS, built_air, events_queue)
        self._record_event(EVENT_FALLEN_AIR_UNITS, unit_stats['air']['lost'], events_queue)
        self._record_event(EVENT_BUILT_LAND_UNITS, built_land, events_queue)
        self._record_event(EVENT_FALLEN_LAND_UNITS, unit_stats['land']['lost'], events_queue)
        self._record_event(EVENT_BUILT_NAVAL_UNITS, built_naval, events_queue)
        self._record_event(EVENT_FALLEN_NAVAL_UNITS, unit_stats['naval']['lost'], events_queue)
        self._record_event(EVENT_FALLEN_ACUS, unit_stats['cdr']['lost'], events_queue)
        self._record_event(EVENT_BUILT_TECH_1_UNITS, unit_stats['tech1']['built'], events_queue)
        self._record_event(EVENT_FALLEN_TECH_1_UNITS, unit_stats['tech1']['lost'], events_queue)
        self._record_event(EVENT_BUILT_TECH_2_UNITS, unit_stats['tech2']['built'], events_queue)
        self._record_event(EVENT_FALLEN_TECH_2_UNITS, unit_stats['tech2']['lost'], events_queue)
        self._record_event(EVENT_BUILT_TECH_3_UNITS, unit_stats['tech3']['built'], events_queue)
        self._record_event(EVENT_FALLEN_TECH_3_UNITS, unit_stats['tech3']['lost'], events_queue)
        self._record_event(EVENT_BUILT_EXPERIMENTALS, built_experimentals, events_queue)
        self._record_event(EVENT_FALLEN_EXPERIMENTALS, unit_stats['experimental']['lost'], events_queue)
        self._record_event(EVENT_BUILT_ENGINEERS, unit_stats['engineer']['built'], events_queue)
        self._record_event(EVENT_FALLEN_ENGINEERS, unit_stats['engineer']['lost'], events_queue)

        if survived:
            if built_air > built_land and built_air > built_naval:
                self._increment(ACH_WRIGHT_BROTHER, 1, achievements_queue)
                self._increment(ACH_WINGMAN, 1, achievements_queue)
                self._increment(ACH_KING_OF_THE_SKIES, 1, achievements_queue)
            elif built_land > built_air and built_land > built_naval:
                self._increment(ACH_MILITIAMAN, 1, achievements_queue)
                self._increment(ACH_GRENADIER, 1, achievements_queue)
                self._increment(ACH_FIELD_MARSHAL, 1, achievements_queue)
            elif built_naval > built_land and built_naval > built_air:
                self._increment(ACH_LANDLUBBER, 1, achievements_queue)
                self._increment(ACH_SEAMAN, 1, achievements_queue)
                self._increment(ACH_ADMIRAL_OF_THE_FLEET, 1, achievements_queue)

            if built_experimentals > 0:
                self._increment(ACH_DR_EVIL, built_experimentals, achievements_queue)

                if built_experimentals >= 3:
                    self._increment(ACH_TECHIE, 1, achievements_queue)
                    self._increment(ACH_I_LOVE_BIG_TOYS, 1, achievements_queue)
                    self._increment(ACH_EXPERIMENTALIST, 1, achievements_queue)

    def _faction_played(self, faction, survived, achievements_queue, events_queue):
        if faction == Faction.aeon:
            self._record_event(EVENT_AEON_PLAYS, 1, events_queue)

            if survived:
                self._record_event(EVENT_AEON_WINS, 1, events_queue)
                self._increment(ACH_AURORA, 1, achievements_queue)
                self._increment(ACH_BLAZE, 1, achievements_queue)
                self._increment(ACH_SERENITY, 1, achievements_queue)
        elif faction == Faction.cybran:
            self._record_event(EVENT_CYBRAN_PLAYS, 1, events_queue)

            if survived:
                self._record_event(EVENT_CYBRAN_WINS, 1, events_queue)
                self._increment(ACH_MANTIS, 1, achievements_queue)
                self._increment(ACH_WAGNER, 1, achievements_queue)
                self._increment(ACH_TREBUCHET, 1, achievements_queue)
        elif faction == Faction.uef:
            self._record_event(EVENT_UEF_PLAYS, 1, events_queue)

            if survived:
                self._record_event(EVENT_UEF_WINS, 1, events_queue)
                self._increment(ACH_MA12_STRIKER, 1, achievements_queue)
                self._increment(ACH_RIPTIDE, 1, achievements_queue)
                self._increment(ACH_DEMOLISHER, 1, achievements_queue)
        elif faction == Faction.seraphim:
            self._record_event(EVENT_SERAPHIM_PLAYS, 1, events_queue)

            if survived:
                self._record_event(EVENT_SERAPHIM_WINS, 1, events_queue)
                self._increment(ACH_THAAM, 1, achievements_queue)
                self._increment(ACH_YENZYNE, 1, achievements_queue)
                self._increment(ACH_SUTHANUS, 1, achievements_queue)

    def _killed_acus(self, count, survived, achievements_queue):
        if count >= 3 and survived:
            self._unlock(ACH_HATTRICK, achievements_queue)

        self._increment(ACH_DONT_MESS_WITH_ME, count, achievements_queue)

    def _built_mercies(self, count, achievements_queue):
        self._increment(ACH_NO_MERCY, count, achievements_queue)

    def _built_fire_beetles(self, count, achievements_queue):
        self._increment(ACH_DEADLY_BUGS, count, achievements_queue)

    def _built_salvations(self, count, survived, achievements_queue):
        if survived and count > 0:
            self._unlock(ACH_RAINMAKER, achievements_queue)

    def _built_yolona_oss(self, count, survived, achievements_queue):
        if survived and count > 0:
            self._unlock(ACH_NUCLEAR_WAR, achievements_queue)

    def _built_paragons(self, count, survived, achievements_queue):
        if survived and count > 0:
            self._unlock(ACH_SO_MUCH_RESOURCES, achievements_queue)

    def _built_atlantis(self, count, achievements_queue):
        self._increment(ACH_IT_AINT_A_CITY, count, achievements_queue)

    def _built_tempests(self, count, achievements_queue):
        self._increment(ACH_STORMY_SEA, count, achievements_queue)

    def _built_scathis(self, count, survived, achievements_queue):
        if survived and count > 0:
            self._unlock(ACH_MAKE_IT_HAIL, achievements_queue)

    def _built_mavors(self, count, survived, achievements_queue):
        if survived and count > 0:
            self._unlock(ACH_I_HAVE_A_CANON, achievements_queue)

    def _built_czars(self, count, achievements_queue):
        self._increment(ACH_DEATH_FROM_ABOVE, count, achievements_queue)

    def _built_ahwassas(self, count, achievements_queue):
        self._increment(ACH_ASS_WASHER, count, achievements_queue)

    def _built_ythothas(self, count, achievements_queue):
        self._increment(ACH_ALIEN_INVASION, count, achievements_queue)

    def _built_fatboys(self, count, achievements_queue):
        self._increment(ACH_FATTER_IS_BETTER, count, achievements_queue)

    def _built_monkeylords(self, count, achievements_queue):
        self._increment(ACH_ARACHNOLOGIST, count, achievements_queue)

    def _built_galactic_colossus(self, count, achievements_queue):
        self._increment(ACH_INCOMING_ROBOTS, count, achievements_queue)

    def _built_soul_rippers(self, count, achievements_queue):
        self._increment(ACH_FLYING_DEATH, count, achievements_queue)

    def _built_megaliths(self, count, achievements_queue):
        self._increment(ACH_HOLY_CRAB, count, achievements_queue)

    def _built_transports(self, count, achievements_queue):
        self._increment(ACH_THE_TRANSPORTER, count, achievements_queue)

    def _built_sacus(self, count, achievements_queue):
        self._set_steps_at_least(ACH_WHO_NEEDS_SUPPORT, count, achievements_queue)

    def _built_asfs(self, count, achievements_queue):
        self._set_steps_at_least(ACH_WHAT_A_SWARM, count, achievements_queue)

    def _lowest_acu_health(self, health, survived, achievements_queue):
        if 0 < health < 500 and survived:
            self._unlock(ACH_THAT_WAS_CLOSE, achievements_queue)

    def _unlock(self, achievement_id, achievements_queue):
        self._achievement_service.unlock(achievement_id, achievements_queue)

    def _increment(self, achievement_id, steps, achievements_queue):
        self._achievement_service.increment(achievement_id, steps, achievements_queue)

    def _set_steps_at_least(self, achievement_id, steps, achievements_queue):
        self._achievement_service.set_steps_at_least(achievement_id, steps, achievements_queue)

    def _record_event(self, event_id, count, events_queue):
        self._event_service.record_event(event_id, count, events_queue)

    @staticmethod
    def _count(unit_stats, function, *units):
        result = 0
        for unit in units:
            if unit.value in unit_stats:
                result += function(unit_stats[unit.value])

        return result
