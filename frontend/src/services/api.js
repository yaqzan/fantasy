import axios from 'axios';

// REACT_APP_API_URL (frontend/.env.production.local) points a separately hosted build at the API.
// Unset: production calls the same origin (Flask serves the build); development uses localhost.
const API_BASE_URL = process.env.REACT_APP_API_URL
  || (process.env.NODE_ENV === 'production' ? '' : 'http://localhost:5001');

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

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

export const calculateCustomZScores = async (puntCategories) => {
  const response = await api.post('/calculate-zscores', {
    punt_categories: puntCategories
  });
  return response.data;
};

export const calculateCustomAuctionValues = async (expFactor, puntCategories = []) => {
  const response = await api.post('/calculate-auction-values', {
    exp_factor: expFactor,
    punt_categories: puntCategories
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

export const getTeamStandings = async (statType, healthyOnly) => {
  const response = await api.get('/team-standings', {
    params: {
      stat_type: statType,
      healthy_only: healthyOnly
    }
  });
  return response.data;
};
