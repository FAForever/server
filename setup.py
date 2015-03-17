from distutils.core import setup

setup(
    name='server',
    version='0.1',
    packages=['games', 'proxy', 'stats', 'steam', 'teams', 'tests', 'tests.unit_tests', 'tests.integration_tests',
              'replays', 'updater', 'gwserver', 'gwserver.teams', 'gwserver.depots', 'gwserver.attacks',
              'gwserver.defenses', 'gwserver.newsFeed', 'gwserver.domination', 'gwserver.namegenerator', 'challonge',
              'trueSkill', 'trueSkill.Numerics', 'trueSkill.TrueSkill', 'trueSkill.TrueSkill.Layers',
              'trueSkill.TrueSkill.Factors', 'trueSkill.FactorGraphs', 'tournament', 'namegenerator'],
    url='http://www.faforever.com',
    license='GPL v3',
    author='FAForever',
    author_email='',
    description=''
)
