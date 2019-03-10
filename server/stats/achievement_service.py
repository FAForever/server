import json
from server.api.api_accessor import ApiAccessor
from server.decorators import with_logger

ACH_NOVICE = 'c6e6039f-c543-424e-ab5f-b34df1336e81'
ACH_JUNIOR = 'd5c759fe-a1a8-4103-888d-3ba319562867'
ACH_SENIOR = '6a37e2fc-1609-465e-9eca-91eeda4e63c4'
ACH_VETERAN = 'bd12277a-6604-466a-9ee6-af6908573585'
ACH_ADDICT = '805f268c-88aa-4073-aa2b-ea30700f70d6'
ACH_FIRST_SUCCESS = '5b7ec244-58c0-40ca-9d68-746b784f0cad'
ACH_HATTRICK = '08629902-8e18-4d92-ad14-c8ecde4a8674'
ACH_THAT_WAS_CLOSE = '290df67c-eb01-4fe7-9e32-caae1c10442f'
ACH_TOP_SCORE = '305a8d34-42fd-42f3-ba91-d9f5e437a9a6'
ACH_UNBEATABLE = 'd3d2c78b-d42d-4b65-99b8-a350f119f898'
ACH_RUSHER = '02081bb0-3b7a-4a36-99ef-5ae5d92d7146'
ACH_MA12_STRIKER = '1a3ad9e0-53eb-47d0-9404-14dbcefbed9b'
ACH_RIPTIDE = '326493d7-ce2c-4a43-bbc8-3e990e2685a1'
ACH_DEMOLISHER = '7d6d8c55-3e2a-41d0-a97e-d35513af1ec6'
ACH_MANTIS = 'd1d50fbb-7fe9-41b0-b667-4433704b8a2c'
ACH_WAGNER = 'af161922-3e52-4600-9161-d850ab0fae86'
ACH_TREBUCHET = 'ff23024e-f533-4e23-8f8f-ecc21d5283f8'
ACH_AURORA = 'd656ade4-e054-415a-a2e9-5f4105f7d724'
ACH_BLAZE = '06a39447-66a3-4160-93d5-d48337b0cbb5'
ACH_SERENITY = '7f993f98-dbec-41a5-9c9a-5f85edf30767'
ACH_THAAM = 'c964ac69-b146-43d0-bd7a-cd22144f9983'
ACH_YENZYNE = '7aa7fc88-48a2-4e49-9cd7-35e2f6ce4cec'
ACH_SUTHANUS = '6acc8bc6-1fd3-4c33-97a1-85dfed6d167a'
ACH_LANDLUBBER = '53173f4d-450c-46f0-ac59-85834cc74972'
ACH_SEAMAN = '2d5cd544-4fc8-47b9-8ebb-e72ed6423d51'
ACH_ADMIRAL_OF_THE_FLEET = 'bd77964b-c06b-4649-bf7c-d35cb7715854'
ACH_WRIGHT_BROTHER = 'c1ccde26-8449-4625-b769-7d8f75fa8df3'
ACH_WINGMAN = 'a4ade3d4-d541-473f-9788-e92339446d75'
ACH_KING_OF_THE_SKIES = 'e220d5e6-481c-4347-ac69-b6b6f956bc0f'
ACH_MILITIAMAN = 'e5c63aec-20a0-4263-841d-b7bc45209713'
ACH_GRENADIER = 'ec8faec7-e3e1-436e-a1ac-9f7adc3d0387'
ACH_FIELD_MARSHAL = '10f17c75-1154-447d-a4f7-6217add0407e'
ACH_TECHIE = '06b19364-5aab-4bce-883d-975f663d2091'
ACH_I_LOVE_BIG_TOYS = 'cd64c5e7-b063-4543-9f52-0e87883b33a9'
ACH_EXPERIMENTALIST = 'e8af7cc9-aaa6-4d0e-8e5a-481702a83a4e'
ACH_WHAT_A_SWARM = '045342e1-ae0d-4ef6-98bc-0bb54ffe00b3'
ACH_THE_TRANSPORTER = 'd38aec23-e487-4aa2-899e-418e29ffbd36'
ACH_WHO_NEEDS_SUPPORT = 'eb1ee9ab-4828-417b-b3e8-c8281ee7a353'
ACH_DEADLY_BUGS = 'e7645e7c-7456-48a8-a562-d97521498e7e'
ACH_NO_MERCY = 'f0cde5d8-4933-4074-a2fb-819074d21abd'
ACH_FLYING_DEATH = 'a98fcfaf-29ac-4526-84c2-44f284518f8c'
ACH_INCOMING_ROBOTS = '1c8fcb6f-a5b6-497f-8b0d-ac5ac6fef408'
ACH_ARACHNOLOGIST = 'a1f87fb7-67ca-4a86-afc6-f23a41b40e9f'
ACH_HOLY_CRAB = 'db141e87-5818-435f-80a3-08cc6f1fdac6'
ACH_FATTER_IS_BETTER = 'ab241de5-e773-412e-b073-090da8e38c4c'
ACH_ALIEN_INVASION = '1f140add-b0ae-4e02-91a0-45d62b988a22'
ACH_ASS_WASHER = '60d1e60d-036b-491e-a992-2b18321848c2'
ACH_DEATH_FROM_ABOVE = '539da20b-5026-4c49-8e22-e4a305d58845'
ACH_STORMY_SEA = 'e603f306-ba6b-4507-9556-37a308e5a722'
ACH_IT_AINT_A_CITY = 'a909629f-46f5-469e-afd1-192d42f55e4d'
ACH_RAINMAKER = '50260d04-90ff-45c8-816b-4ad8d7b97ecd'
ACH_I_HAVE_A_CANON = '31a728f8-ace9-45fa-a3f2-57084bc9e461'
ACH_MAKE_IT_HAIL = '987ca192-26e1-4b96-b593-40c115451cc0'
ACH_SO_MUCH_RESOURCES = '46a6e900-88bb-4eae-92d1-4f31b53faedc'
ACH_NUCLEAR_WAR = '9ad697bb-441e-45a5-b682-b9227e8eef3e'
ACH_DR_EVIL = 'a6b7dfa1-1ebc-4c6d-9305-4a9d623e1b4f'
ACH_DONT_MESS_WITH_ME = '2103e0de-1c87-4fba-bc1b-0bba66669607'


@with_logger
class AchievementService:
    def __init__(self, api_accessor: ApiAccessor):
        self.api_accessor = api_accessor

    async def execute_batch_update(self, player_id, queue):
        """
        Sends a batch of achievement updates.

        :param player_id: the player to update the achievements for
        :param queue: an array of achievement updates in the form::

            [{
                "achievement_id": string,
                "update_type": string,
                "steps": integer
            }]

            ``updateType`` being one of "REVEAL", "INCREMENT", "UNLOCK" or "SET_STEPS_AT_LEAST"
            ``steps`` being mandatory only for update type `` INCREMENT`` and ``SET_STEPS_AT_LEAST``

        :return
        If successful, this method returns an array with the following structure::

            [{
                "achievement_id": string,
                "current_state": string,
                "current_steps": integer,
                "newly_unlocked": boolean
            }]

        Else, it returns None
        """
        self._logger.debug("Updating %d achievements", len(queue))
        response, content = await self.api_accessor.update_achievements(queue, player_id)
        if response < 300:
            """
            Converting the Java API data to the structure mentioned above
            """
            api_data = json.loads(content)['data']
            achievements_data = []
            for achievement in api_data:
                converted_achievement = dict(
                    achievement_id=achievement['attributes']['achievementId'],
                    current_state=achievement['attributes']['state'],
                    newly_unlocked=achievement['attributes']['newlyUnlocked']
                )
                if 'steps' in achievement['attributes']:
                    converted_achievement['current_steps'] = achievement['attributes']['steps']

                achievements_data.append(converted_achievement)

            return achievements_data
        return None

    def unlock(self, achievement_id, queue):
        """
        Enqueues an achievement update that reveals an achievement.

        :param achievement_id: the achievement to unlock
        :param queue: the queue to put this update into so it can be batch executed later
        """
        queue.append(dict(achievement_id=achievement_id, update_type='UNLOCK'))

    def reveal(self, achievement_id, queue):
        """
        Enqueues an achievement update that reveals an achievement.

        :param achievement_id: the achievement to unlock
        :param queue: the queue to put this update into so it can be batch executed later
        """
        queue.append(dict(achievement_id=achievement_id, update_type='REVEAL'))

    def increment(self, achievement_id, steps, queue):
        """
        Enqueues an achievement update that increments an achievement.

        :param achievement_id: the achievement to unlock
        :param steps the number of steps to increment
        :param queue: the queue to put this update into so it can be batch executed later
        """
        if steps == 0:
            return

        queue.append(dict(achievement_id=achievement_id, update_type='INCREMENT', steps=steps))

    def set_steps_at_least(self, achievement_id, steps, queue):
        """
        Enqueues an achievement update that sets the steps to the specified minimum steps.

        :param achievement_id: the achievement to update
        :param steps the minimum number of steps to set
        :param queue: the queue to put this update into so it can be batch executed later
        """
        if steps == 0:
            return

        queue.append(dict(achievement_id=achievement_id, update_type='SET_STEPS_AT_LEAST', steps=steps))
