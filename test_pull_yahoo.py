"""pull_yahoo's parsers on XML shaped like Yahoo's Fantasy API v2 responses (no network, no DB).

    py -m pytest test_pull_yahoo.py
"""
import xml.etree.ElementTree as ET

from pull_yahoo import parse_rosters, parse_slots

NS = 'xmlns="http://fantasysports.yahooapis.com/fantasy/v2/base.rng"'

ROSTERS = f"""<?xml version="1.0" encoding="UTF-8"?>
<fantasy_content {NS}><league><league_key>nba.l.1</league_key><teams count="1">
  <team><team_key>nba.l.1.t.3</team_key><team_id>3</team_id><name>Team Three</name>
    <roster><players count="2">
      <player><player_key>nba.p.1</player_key><name><full>Luka Dončić</full></name>
        <eligible_positions><position>PG</position><position>SG</position><position>G</position>
          <position>Util</position></eligible_positions><is_undroppable>1</is_undroppable></player>
      <player><player_key>nba.p.2</player_key><name><full>Test Center</full></name>
        <eligible_positions><position>C</position><position>Util</position><position>IL</position></eligible_positions>
        <is_undroppable>0</is_undroppable></player>
    </players></roster></team>
</teams></league></fantasy_content>"""

SETTINGS = f"""<?xml version="1.0" encoding="UTF-8"?>
<fantasy_content {NS}><league><settings><roster_positions>
  <roster_position><position>PG</position><count>1</count></roster_position>
  <roster_position><position>G</position><count>1</count></roster_position>
  <roster_position><position>C</position><count>2</count></roster_position>
  <roster_position><position>Util</position><count>2</count></roster_position>
  <roster_position><position>BN</position><count>4</count></roster_position>
  <roster_position><position>IL</position><count>2</count></roster_position>
</roster_positions></settings></league></fantasy_content>"""


def test_rosters_keep_slot_positions_and_cant_cut():
    [team] = parse_rosters(ET.fromstring(ROSTERS.encode()))
    assert (team['team_id'], team['name']) == ('3', 'Team Three')
    luka, center = team['players']
    assert luka == {'name': 'Luka Dončić', 'positions': ['PG', 'SG', 'G'], 'undroppable': True}
    assert center == {'name': 'Test Center', 'positions': ['C'], 'undroppable': False}


def test_settings_starting_slots():
    assert parse_slots(ET.fromstring(SETTINGS.encode())) == ['PG', 'G', 'C', 'C', 'UTIL', 'UTIL']
