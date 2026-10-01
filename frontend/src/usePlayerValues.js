import { useState, useEffect } from 'react';
import { calculateCustomZScores, calculateCustomAuctionValues } from './services/api';

// API field suffix for each stats choice ('proj' = this season's projection).
const PERIOD_SUFFIX = { season: '_season', '5': '_5', '10': '_10', projected: '_projected', proj: '_proj' };

// Rank, score and auction $ for the selected stats, with the punted categories and the
// star-premium slider applied. Shared by the in-season table and the draft board.
// priceExponent: null means the league's own draft.price_exponent (the server's default values).
export default function usePlayerValues({ punts, statType, priceExponent }) {
  const [customScores, setCustomScores] = useState({});
  const [loadingCustomScores, setLoadingCustomScores] = useState(false);
  const [customAuctionValues, setCustomAuctionValues] = useState({});

  // Punted scores are per timeframe: fetched for the punts (restored ones too) and the timeframe.
  const puntKey = punts.join(',');
  useEffect(() => {
    if (punts.length === 0) {
      setCustomScores({});
      return;
    }
    let cancelled = false;
    setLoadingCustomScores(true);
    calculateCustomZScores(punts, statType)
      .then(response => { if (!cancelled) setCustomScores(response.custom_scores); })
      .catch(error => console.error('Error calculating custom z-scores:', error))
      .finally(() => { if (!cancelled) setLoadingCustomScores(false); });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [puntKey, statType]);

  // Auction values follow the star-premium slider and the punted categories; with neither
  // changed, the server's values (the league's own exponent, nothing punted) stand.
  useEffect(() => {
    if (priceExponent === null && punts.length === 0) {
      setCustomAuctionValues({});
      return;
    }
    let cancelled = false;
    calculateCustomAuctionValues(priceExponent, punts, statType)
      .then(response => { if (!cancelled) setCustomAuctionValues(response.auction_values || {}); })
      .catch(error => {
        console.error('Error calculating custom auction values:', error);
        if (!cancelled) setCustomAuctionValues({});
      });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [priceExponent, puntKey, statType]);

  // The field for the selected stats: periodKey('z_score') -> 'z_score_season' etc.
  const periodKey = (base) => `${base}${PERIOD_SUFFIX[statType] || '_projected'}`;
  const forPeriod = (player, base) => player[periodKey(base)] ?? player[base];

  return {
    customScores,
    loadingCustomScores,
    periodKey,
    // Auction value on the same stats as the rank (custom slider/punt values when set)
    getAuctionValue: (player) => customAuctionValues[player.name]?.auction_value || forPeriod(player, 'auction_value'),
    getZScore: (player) => forPeriod(player, 'z_score'),
    getOverallRank: (player) => forPeriod(player, 'overall_rank'),
    // Rank and score with the punts applied
    getRank: (player) => customScores[player.name]?.custom_z_rank || forPeriod(player, 'overall_rank'),
    getScore: (player) => customScores[player.name]?.custom_z_score || forPeriod(player, 'z_score'),
  };
}
