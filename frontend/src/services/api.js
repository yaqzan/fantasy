import axios from 'axios';

// Same origin: Flask serves the build and the API under /api. In development the CRA proxy
// (src/setupProxy.js) forwards /api to Flask. REACT_APP_API_URL overrides it for a split setup.
const API_BASE_URL = process.env.REACT_APP_API_URL || '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Every request is about one league: the one picked in the header's league switcher.
const LEAGUE_KEY = 'fantasy.league';

export const getSelectedLeague = () => {
  try {
    return localStorage.getItem(LEAGUE_KEY);
  } catch (e) {
    return null;
  }
};

export const setSelectedLeague = (leagueId) => {
  try {
    if (leagueId) localStorage.setItem(LEAGUE_KEY, leagueId);
    else localStorage.removeItem(LEAGUE_KEY);
  } catch (e) {
    // storage blocked: the backend falls back to the active league
  }
};

api.interceptors.request.use((config) => {
  const leagueId = getSelectedLeague();
  if (leagueId) config.headers['X-League'] = leagueId;
  return config;
});

// The backend's error message, when it sent one.
// Draft Day tab: targets, max bids and past-auction evidence (the owner's gitignored draft_day.json).
export const getDraftDay = async () => (await api.get('/draft-day')).data;

export const errorMessage = (error) => error?.response?.data?.error || error?.message || 'Request failed';

export const getLeagues = async () => {
  const response = await api.get('/leagues');
  return response.data;
};

export const createLeague = async (name, settings, copyTeamsFrom = null) => {
  const response = await api.post('/leagues', { name, settings, copy_teams_from: copyTeamsFrom });
  return response.data;
};

export const updateLeague = async (leagueId, name, settings) => {
  const response = await api.put(`/leagues/${leagueId}`, { name, settings });
  return response.data;
};

export const activateLeague = async (leagueId) => {
  const response = await api.post(`/leagues/${leagueId}/activate`);
  return response.data;
};

export const deleteLeague = async (leagueId) => {
  const response = await api.delete(`/leagues/${leagueId}`);
  return response.data;
};

export const generateWeeks = async () => {
  const response = await api.get('/leagues/generate-weeks');
  return response.data;
};

export const getPlayers = async () => {
  const response = await api.get('/fantasy');
  return response.data;
};

export const getFantasyTeams = async () => {
  const response = await api.get('/fantasy-teams');
  return response.data;
};

export const createFantasyTeam = async (teamData) => {
  const response = await api.post('/fantasy-teams', teamData);
  return response.data;
};

export const updateFantasyTeam = async (teamId, teamData) => {
  const response = await api.put(`/fantasy-teams/${teamId}`, teamData);
  return response.data;
};

export const deleteFantasyTeam = async (teamId) => {
  const response = await api.delete(`/fantasy-teams/${teamId}`);
  return response.data;
};

// Guillotine: knock a team out (its players become free agents) or undo that.
export const eliminateFantasyTeam = async (teamId, stage = null) => {
  const response = await api.post(`/fantasy-teams/${teamId}/eliminate`, stage ? { stage } : {});
  return response.data;
};

export const restoreFantasyTeam = async (teamId) => {
  const response = await api.post(`/fantasy-teams/${teamId}/restore`);
  return response.data;
};

export const draftPlayer = async (playerName, fantasyTeamId) => {
  const response = await api.post('/draft-player', {
    player_name: playerName,
    fantasy_team_id: fantasyTeamId
  });
  return response.data;
};

export const undraftPlayer = async (playerName) => {
  const response = await api.post('/undraft-player', {
    player_name: playerName
  });
  return response.data;
};

export const updatePlayer = async (playerName, isInjured, isUndroppable) => {
  const response = await api.post('/update-player', {
    player_name: playerName,
    is_injured: isInjured,
    is_undroppable: isUndroppable
  });
  return response.data;
};

export const getTeamPlayers = async (teamId) => {
  const response = await api.get(`/team-players/${teamId}`);
  return response.data;
};

export const calculateCustomZScores = async (puntCategories, statType = 'projected') => {
  const response = await api.post('/calculate-zscores', {
    punt_categories: puntCategories,
    stat_type: statType
  });
  return response.data;
};

// priceExponent null: the league's own draft.price_exponent. statType: the stats the values rest on.
export const calculateCustomAuctionValues = async (priceExponent, puntCategories = [], statType = 'projected') => {
  const response = await api.post('/calculate-auction-values', {
    ...(priceExponent !== null && { price_exponent: priceExponent }),
    punt_categories: puntCategories,
    stat_type: statType
  });
  return response.data;
};

export const analyze = async (weekStart = null, timeframe = 'projected', pickup = false, pickupTimeframe = null) => {
  const params = {
    ...(weekStart && { week_start: weekStart }),
    timeframe,
    pickup: pickup.toString(),
    ...(pickupTimeframe && { pickup_timeframe: pickupTimeframe })
  };
  const response = await api.get('/analyze', { params });
  return response.data;
};

// Projections (NBA-wide): team wins by source + the owner's adjustments, player lines by source.
export const getTeamProjections = async () => (await api.get('/projections/teams')).data;
export const setTeamAdjustment = async (team, adjustment) =>
  (await api.put('/projections/teams', { team, adjustment })).data;
export const getPlayerProjections = async (q = '') =>
  (await api.get('/projections/players', { params: { ...(q && { q }) } })).data;
export const setPlayerAdjustment = async (playerId, production, games = null) =>
  (await api.put(`/projections/players/${playerId}`, { production, games })).data;

// Free agents ranked by the categories they'd add in a week (weekStart null: the current week).
export const getPickups = async (weekStart = null, timeframe = 'projected') => {
  const params = { ...(weekStart && { week_start: weekStart }), timeframe };
  const response = await api.get('/pickups', { params });
  return response.data;
};

export const analyzeCustom = async (weekStart, pickup, drop = null) => {
  const response = await api.post('/analyze/custom', { week_start: weekStart, pickup, drop });
  return response.data;
};

export const getDailyStats = async (date) => {
  const response = await api.get('/daily-stats', {
    params: { date }
  });
  return response.data;
};

export const updateDailyStats = async (date) => {
  const response = await api.post('/daily-stats/update', {
    date
  });
  return response.data;
};

// view: 'per_game' (roster strength, schedule-free) or 'week' (this fantasy week's projection)
export const getTeamStandings = async (statType, healthyOnly, view = 'per_game') => {
  const response = await api.get('/team-standings', {
    params: {
      stat_type: statType,
      healthy_only: healthyOnly,
      view
    }
  });
  return response.data;
};
