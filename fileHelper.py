# Ported from Archivist's archiver/fileHelper.py (shared origin -- Fantasy and Archivist were
# built side by side and split fileHelper's date helpers between them without Fantasy keeping its
# own copy). Only the two functions Fantasy actually imports are here
# (date_to_string, string_to_date) -- see fantasy_database.py, fantasy_team_helper.py,
# lineup_optimizer.py, main.py, pull_api_data.py. Do not grow this file with unrelated
# fileHelper functions Fantasy doesn't use; port them from Archivist if a real need shows up.

from dateutil.parser import parse
from dateutil.parser._parser import ParserError


def date_to_string(date, long=True):
    if date is None:
        return ''
    if long:
        return date.strftime('%B X%d, %Y').replace('X0', 'X').replace('X', '')
    else:
        return date.strftime('%y.%m.%d')


def string_to_date(datestr, dayfirst=False):
    try:
        return parse(datestr, fuzzy=True, dayfirst=dayfirst)
    except ParserError as err:
        if 'month must be in 1..12' in str(err):
            return parse(datestr, fuzzy=True, dayfirst=not dayfirst)
        raise err
