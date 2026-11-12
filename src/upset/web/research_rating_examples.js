/* Fictional design fixtures only. Never use these scores for actual fighters.
 * The display curves and division percentiles below are illustrative, not fitted.
 */
(function () {
  'use strict';

  const examples = Object.freeze([
    {
      id: 'champion',
      label: 'Champion',
      name: 'Sample champion',
      division: 'Light heavyweight',
      record: '22–1',
      bouts: 23,
      score: 96,
      peak: 97,
      delta: 1,
      lastResult: 'Win vs. a 91',
      parts: [
        {
          key: 'striking', label: 'Striking', score: 92,
          description: 'Damage, efficiency and defense on the feet.',
          raw: [
            { label: 'Significant-strike difference', value: '+2.40 / min', percentile: 96 },
            { label: 'Striking accuracy', value: '56.2%', percentile: 91 },
            { label: 'Striking defense', value: '63.8%', percentile: 94 },
            { label: 'Knockdowns scored', value: '1.10 / 15 min', percentile: 93 },
          ],
        },
        {
          key: 'wrestling', label: 'Wrestling', score: 96,
          description: 'Getting the fight down, stopping takedowns and controlling position.',
          raw: [
            { label: 'Takedowns landed', value: '3.80 / 15 min', percentile: 96 },
            { label: 'Takedown accuracy', value: '61.4%', percentile: 95 },
            { label: 'Takedown defense', value: '92.0%', percentile: 98 },
            { label: 'Control share', value: '68.2%', percentile: 97 },
          ],
        },
        {
          key: 'grappling', label: 'Grappling', score: 90,
          description: 'Submission threat and effectiveness on the ground.',
          raw: [
            { label: 'Submission attempts', value: '0.90 / 15 min', percentile: 86 },
            { label: 'Submission wins', value: '6', percentile: 94 },
            { label: 'Submission losses', value: '0', percentile: 90 },
            { label: 'Ground-strike difference', value: '+12.4 / 15 min', percentile: 92 },
          ],
        },
        {
          key: 'resume', label: 'Résumé', score: 95.4,
          description: 'The strength of the opponents this fighter has beaten.',
          raw: [
            { label: 'Chronological Elo', value: '2,140', percentile: 99 },
            { label: 'Wins over 90+ rated opponents', value: '9', percentile: 99 },
            { label: 'UFC wins', value: '22', percentile: 98 },
          ],
        },
      ],
      curve: { combined: 94.5, percentileLabel: 'Top 0.4%', display: 96, version: 'Illustrative curve' },
      history: [
        { label: 'Fight 16', score: 88, change: 3, outcome: 'Win', opponentScore: 85 },
        { label: 'Fight 17', score: 91, change: 3, outcome: 'Win', opponentScore: 91 },
        { label: 'Fight 18', score: 93, change: 2, outcome: 'Win', opponentScore: 90 },
        { label: 'Fight 19', score: 94, change: 1, outcome: 'Win', opponentScore: 89 },
        { label: 'Fight 20', score: 95, change: 1, outcome: 'Win', opponentScore: 91 },
        { label: 'Fight 21', score: 97, change: 2, outcome: 'Win', opponentScore: 95 },
        { label: 'Fight 22', score: 95, change: -2, outcome: 'Loss', opponentScore: 94 },
        { label: 'Fight 23', score: 96, change: 1, outcome: 'Win', opponentScore: 91 },
      ],
    },
    {
      id: 'prospect',
      label: '4–0 prospect',
      name: 'Sample prospect',
      division: 'Welterweight',
      record: '4–0',
      bouts: 4,
      score: 82,
      peak: 82,
      delta: 4,
      lastResult: 'Win vs. a 79',
      parts: [
        {
          key: 'striking', label: 'Striking', score: 83,
          description: 'Promising striking, balanced against limited UFC history.',
          raw: [
            { label: 'Significant-strike difference', value: '+2.80 / min', percentile: 94 },
            { label: 'Striking accuracy', value: '61.8%', percentile: 96 },
            { label: 'Striking defense', value: '58.1%', percentile: 78 },
            { label: 'Recorded significant-strike attempts', value: '246', percentile: null },
          ],
        },
        {
          key: 'wrestling', label: 'Wrestling', score: 80,
          description: 'Early wrestling evidence with a cautious adjustment for exposure.',
          raw: [
            { label: 'Takedowns landed', value: '2.10 / 15 min', percentile: 77 },
            { label: 'Takedown accuracy', value: '50.0%', percentile: 75 },
            { label: 'Takedown defense', value: '80.0%', percentile: 85 },
            { label: 'Control share', value: '55.0%', percentile: 72 },
          ],
        },
        {
          key: 'grappling', label: 'Grappling', score: 76,
          description: 'Some ground success; the evidence is still limited.',
          raw: [
            { label: 'Submission attempts', value: '0.50 / 15 min', percentile: 65 },
            { label: 'Submission wins', value: '1', percentile: 58 },
            { label: 'Submission losses', value: '0', percentile: 76 },
            { label: 'Ground-strike difference', value: '+5.2 / 15 min', percentile: 69 },
          ],
        },
        {
          key: 'resume', label: 'Résumé', score: 79.3,
          description: 'Four wins build a record, but the strongest opponents are still ahead.',
          raw: [
            { label: 'Chronological Elo', value: '1,570', percentile: 68 },
            { label: 'Wins over 90+ rated opponents', value: '0', percentile: 48 },
            { label: 'UFC wins', value: '4', percentile: 61 },
          ],
        },
      ],
      curve: { combined: 80, percentileLabel: 'Top 28%', display: 82, version: 'Illustrative curve' },
      history: [
        { label: 'Fight 1', score: 72, change: 2, outcome: 'Win', opponentScore: 70 },
        { label: 'Fight 2', score: 75, change: 3, outcome: 'Win', opponentScore: 74 },
        { label: 'Fight 3', score: 78, change: 3, outcome: 'Win', opponentScore: 76 },
        { label: 'Fight 4', score: 82, change: 4, outcome: 'Win', opponentScore: 79 },
      ],
    },
    {
      id: 'provisional',
      label: 'Provisional',
      name: 'Sample newcomer',
      division: 'Featherweight',
      record: '2–0',
      bouts: 2,
      score: 79,
      peak: 79,
      delta: 4,
      lastResult: 'Win vs. a 75',
      parts: [
        {
          key: 'striking', label: 'Striking', score: 84,
          description: 'Strong early numbers, with very little history behind them.',
          raw: [
            { label: 'Significant-strike difference', value: '+3.10 / min', percentile: 97 },
            { label: 'Striking accuracy', value: '65.2%', percentile: 98 },
            { label: 'Striking defense', value: '60.0%', percentile: 84 },
            { label: 'Recorded significant-strike attempts', value: '92', percentile: null },
          ],
        },
        {
          key: 'wrestling', label: 'Wrestling', score: 74,
          description: 'Too few attempts to treat the early wrestling rate as settled.',
          raw: [
            { label: 'Takedowns landed', value: '1.20 / 15 min', percentile: 55 },
            { label: 'Takedown accuracy', value: '50.0%', percentile: 70 },
            { label: 'Takedown defense', value: '66.7%', percentile: 57 },
            { label: 'Control share', value: '48.0%', percentile: 54 },
          ],
        },
        {
          key: 'grappling', label: 'Grappling', score: 70,
          description: 'Limited grappling evidence remains close to the newcomer baseline.',
          raw: [
            { label: 'Submission attempts', value: '0.00 / 15 min', percentile: 30 },
            { label: 'Submission wins', value: '0', percentile: 35 },
            { label: 'Submission losses', value: '0', percentile: 69 },
            { label: 'Ground-strike difference', value: '+1.8 / 15 min', percentile: 52 },
          ],
        },
        {
          key: 'resume', label: 'Résumé', score: 75.8,
          description: 'Two UFC wins are an encouraging start, not an established résumé.',
          raw: [
            { label: 'Chronological Elo', value: '1,536', percentile: 58 },
            { label: 'Wins over 90+ rated opponents', value: '0', percentile: 44 },
            { label: 'UFC wins', value: '2', percentile: 42 },
          ],
        },
      ],
      curve: { combined: 77, percentileLabel: 'Top 40%', display: 79, version: 'Illustrative curve' },
      history: [
        { label: 'Fight 1', score: 75, change: 3, outcome: 'Win', opponentScore: 71 },
        { label: 'Fight 2', score: 79, change: 4, outcome: 'Win', opponentScore: 75 },
      ],
    },
    {
      id: 'debut',
      label: 'Debut',
      name: 'Sample debut fighter',
      division: 'Lightweight',
      record: '0–0',
      bouts: 0,
      score: null,
      peak: null,
      delta: null,
      lastResult: 'Rated after first UFC fight',
      parts: [],
      curve: null,
      history: [],
    },
  ]);

  function freezeNested(value) {
    if (value && typeof value === 'object') {
      Object.values(value).forEach(freezeNested);
      Object.freeze(value);
    }
  }
  examples.forEach(freezeNested);

  if (typeof window !== 'undefined') window.UPSETRatingExamples = examples;
  if (typeof module !== 'undefined' && module.exports) module.exports = examples;
}());
