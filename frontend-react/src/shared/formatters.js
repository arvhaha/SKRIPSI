import { weatherIcons } from './assets';

export function normalizeDistrictToken(value) {
  return String(value ?? '')
    .toLowerCase()
    .replace(/\s+/g, '')
    .trim();
}

export function toTitleCaseWords(value) {
  return String(value ?? '')
    .toLowerCase()
    .replace(/\b\p{L}/gu, character => character.toUpperCase());
}

export function parseDateValue(value) {
  const normalizedValue = String(value ?? '').trim();

  if (!normalizedValue) {
    return null;
  }

  const date = /^\d{4}-\d{2}-\d{2}$/.test(normalizedValue)
    ? new Date(`${normalizedValue}T00:00:00`)
    : new Date(normalizedValue);

  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatNumber(value) {
  return new Intl.NumberFormat('id-ID').format(Number(value) || 0);
}

export function formatUpdatedAt(value) {
  const date = parseDateValue(value);

  if (!date) {
    return 'Tidak tersedia';
  }

  return new Intl.DateTimeFormat('id-ID', {
    dateStyle: 'medium',
    timeStyle: 'short'
  }).format(date);
}

export function formatDateOnly(value) {
  const date = parseDateValue(value);

  if (!date) {
    return 'Tidak tersedia';
  }

  return new Intl.DateTimeFormat('id-ID', {
    dateStyle: 'medium'
  }).format(date);
}

export function getPublicPayloadMode(meta = {}) {
  const source = String(meta?.publicPayloadSource || '').trim().toLowerCase();

  if (source === 'live_fallback') {
    return 'live_fallback';
  }

  if (source === 'admin_publish' || source === 'published_snapshot' || source === 'scheduled_export') {
    return 'published_snapshot';
  }

  return 'unknown';
}

export function getPublicPayloadStatus(meta = {}, sourceUrl = '') {
  const payloadMode = getPublicPayloadMode(meta);
  const labelFromMeta = String(meta?.publicPayloadSourceLabel || '').trim();

  if (payloadMode === 'published_snapshot') {
    return {
      text: labelFromMeta || 'Snapshot Publik Aktif',
      tone: 'success'
    };
  }

  if (payloadMode === 'live_fallback') {
    return {
      text: labelFromMeta || 'Fallback Live Backend',
      tone: 'warning'
    };
  }

  if (sourceUrl && sourceUrl.includes('api/')) {
    return {
      text: labelFromMeta || 'API Backend Aktif',
      tone: 'success'
    };
  }

  return {
    text: labelFromMeta || 'JSON Cadangan',
    tone: 'fallback'
  };
}

export function formatDateNumeric(value) {
  const date = parseDateValue(value);

  if (!date) {
    return '-';
  }

  const day = String(date.getDate()).padStart(2, '0');
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const year = date.getFullYear();
  return `${day}-${month}-${year}`;
}

export function formatPercent(value) {
  const numericValue = Number(value);

  if (Number.isNaN(numericValue)) {
    return 'Tidak tersedia';
  }

  return `${numericValue.toLocaleString('id-ID', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1
  })}%`;
}

export function formatMillimeter(value, fallback = '-') {
  const numericValue = Number(value);

  if (Number.isNaN(numericValue)) {
    return fallback;
  }

  return `${numericValue.toLocaleString('id-ID', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1
  })} mm`;
}

export function formatRainMm(value) {
  return formatMillimeter(value, 'Tidak tersedia');
}

export function formatScore(value) {
  const numericValue = Number(value);

  if (Number.isNaN(numericValue)) {
    return 'Tidak tersedia';
  }

  const normalized = numericValue <= 1 ? numericValue * 100 : numericValue;
  return `${normalized.toLocaleString('id-ID', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1
  })} / 100`;
}

export function formatSignedPercent(value) {
  const numericValue = Number(value);

  if (Number.isNaN(numericValue)) {
    return 'Tidak tersedia';
  }

  const sign = numericValue > 0 ? '+' : '';
  return `${sign}${numericValue.toLocaleString('id-ID', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1
  })}%`;
}

export function getPredictedClassConfidencePercentValue(prediction) {
  const dominantClassProbability = Number(prediction?.predictedClassProbabilityPercent);

  if (!Number.isNaN(dominantClassProbability)) {
    return dominantClassProbability;
  }

  const extremeProbability = Number(prediction?.probabilityWaspadaPercent);
  if (!Number.isNaN(extremeProbability)) {
    return extremeProbability;
  }

  return NaN;
}

export function getRainfallDisplayValue(prediction) {
  if (prediction?.predictedRainfallLabel) {
    const label = String(prediction.predictedRainfallLabel).trim();
    if (label.toLowerCase().includes('cerah')) {
      return 'Cerah';
    }

    return label;
  }

  if (prediction?.predictedRainfallRange) {
    const range = String(prediction.predictedRainfallRange).trim();
    if (range.toLowerCase().includes('cerah')) {
      return 'Cerah';
    }

    return range;
  }

  const rainfallMm = Number(prediction?.predictedRainfallMm);
  if (!Number.isNaN(rainfallMm)) {
    return `${rainfallMm} mm`;
  }

  return 'Tidak tersedia';
}

export function getShowcaseForecastDate(prediction) {
  const label = String(prediction?.forecastLabel || '').trim();
  return label ? label.replace(/^Prediksi\s+/i, '') : 'Prediksi aktif';
}

export function getShowcaseRiskPercent(prediction) {
  const explicitPercent = Number(prediction?.riskScorePercent);
  if (!Number.isNaN(explicitPercent)) {
    return Math.round(explicitPercent);
  }

  const riskScore = Number(prediction?.riskScore);
  if (Number.isNaN(riskScore)) {
    return null;
  }

  return Math.round(riskScore <= 1 ? riskScore * 100 : riskScore);
}

export function getShowcasePrimaryValue(prediction) {
  const temperature = Number(prediction?.latestObservedTemperatureC);
  if (Number.isNaN(temperature)) {
    return '-';
  }

  return `${temperature.toLocaleString('id-ID', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  })}\u00B0C`;
}

export function getSemanticRiskLevelLabel(prediction) {
  const level = Number(prediction?.webgisLevel);

  if (level === 1) {
    return 'Level 1: Sangat Rendah';
  }

  if (level === 2) {
    return 'Level 2: Ringan';
  }

  if (level === 3) {
    return 'Level 3: Sedang';
  }

  if (level === 4) {
    return 'Level 4: Tinggi';
  }

  return prediction?.webgisLevelLabel || prediction?.riskCategory || 'Tidak tersedia';
}

export function getCompactRiskLevelLabel(prediction) {
  const semanticLabel = getSemanticRiskLevelLabel(prediction);
  return semanticLabel.replace(/^Level\s*\d+\s*:\s*/i, '').trim();
}

export function getDetailRiskDisplay(prediction) {
  const riskLabel = getCompactRiskLevelLabel(prediction);
  const riskPercent = getShowcaseRiskPercent(prediction);

  if (riskPercent === null) {
    return riskLabel;
  }

  return `${riskLabel} (${formatNumber(riskPercent)}%)`;
}

export function getShowcaseFloodRiskLine(prediction) {
  const label = getCompactRiskLevelLabel(prediction);
  if (!label) {
    return 'Risiko : Belum tersedia';
  }

  return `Risiko : ${label}`;
}

export function getShowcaseRainSummary(prediction) {
  const label = String(prediction?.predictedRainfallLabel || prediction?.riskCategory || '').toLowerCase();

  if (label.includes('cerah')) {
    return 'Cerah';
  }

  if (label.includes('ringan')) {
    return 'Hujan Ringan';
  }

  if (label.includes('sedang')) {
    return 'Hujan Sedang';
  }

  if (label.includes('lebat')) {
    return 'Lebat / Ekstrem';
  }

  return prediction?.webgisDescription || prediction?.riskCategory || 'Tidak tersedia';
}

export function getDetailRainDisplay(prediction) {
  const summary = getShowcaseRainSummary(prediction);
  const predictedRainfallMm = Number(prediction?.predictedRainfallMm);

  if (!Number.isNaN(predictedRainfallMm)) {
    if (summary === 'Cerah') {
      return summary;
    }

    return `${summary} (${formatRainMm(predictedRainfallMm)})`;
  }

  const latestObservedRainfallMm = Number(prediction?.latestObservedRainfallMm);
  if (!Number.isNaN(latestObservedRainfallMm)) {
    if (summary === 'Cerah') {
      return summary;
    }

    return `${summary} (${formatRainMm(latestObservedRainfallMm)})`;
  }

  if (prediction?.predictedRainfallRange && summary !== 'Cerah') {
    return `${summary} (${prediction.predictedRainfallRange})`;
  }

  return summary;
}

export function getShowcaseIconSpec(prediction) {
  const rainSummary = getShowcaseRainSummary(prediction).toLowerCase();

  if (rainSummary.includes('lebat')) {
    return { key: 'thunder', path: weatherIcons.thunder };
  }

  if (rainSummary.includes('sedang') || rainSummary.includes('ringan')) {
    return { key: 'rainy', path: weatherIcons.rainy };
  }

  if (rainSummary.includes('cerah')) {
    const temperature = Number(prediction?.latestObservedTemperatureC);
    return Number.isNaN(temperature) || temperature < 29
      ? { key: 'partly-cloudy', path: weatherIcons['partly-cloudy'] }
      : { key: 'sunny', path: weatherIcons.sunny };
  }

  return { key: 'partly-cloudy', path: weatherIcons['partly-cloudy'] };
}

export function getRiskColor(value) {
  const prediction = typeof value === 'object' && value !== null ? value : null;
  const level = Number(prediction?.webgisLevel);

  if (level === 4) {
    return '#e03131';
  }

  if (level === 3) {
    return '#f76707';
  }

  if (level === 2) {
    return '#f0c419';
  }

  if (level === 1) {
    return '#2f9e44';
  }

  const category = prediction ? prediction.riskCategory : value;
  switch ((category || '').toLowerCase()) {
    case 'cerah':
    case 'rendah':
      return '#2f9e44';
    case 'ringan':
      return '#f0c419';
    case 'sedang':
      return '#f76707';
    case 'lebat':
    case 'lebat/ekstrem':
    case 'tinggi':
      return '#e03131';
    default:
      return '#94a3b8';
  }
}

export function getRiskTone(value) {
  const prediction = typeof value === 'object' && value !== null ? value : null;
  const level = Number(prediction?.webgisLevel);

  if (level === 4) {
    return 'high';
  }

  if (level === 3) {
    return 'watch';
  }

  if (level === 2) {
    return 'medium';
  }

  if (level === 1) {
    return 'low';
  }

  const category = prediction ? prediction.riskCategory : value;
  switch ((category || '').toLowerCase()) {
    case 'cerah':
    case 'rendah':
      return 'low';
    case 'ringan':
      return 'medium';
    case 'sedang':
      return 'watch';
    case 'lebat':
    case 'lebat/ekstrem':
    case 'tinggi':
      return 'high';
    default:
      return 'low';
  }
}

export function getLatestValueByDate(candidates) {
  let latestValue = null;
  let latestTimestamp = -Infinity;

  candidates.forEach(candidate => {
    const parsedDate = parseDateValue(candidate);
    if (!parsedDate) {
      return;
    }

    const timestamp = parsedDate.getTime();
    if (timestamp > latestTimestamp) {
      latestTimestamp = timestamp;
      latestValue = candidate;
    }
  });

  return latestValue;
}

export function extractForecastDateValue(prediction) {
  return String(prediction?.forecastLabel || '')
    .replace(/^Prediksi\s+/i, '')
    .trim();
}

export function differenceFromTodayInDays(value) {
  const parsedDate = parseDateValue(value);

  if (!parsedDate) {
    return null;
  }

  const today = new Date();
  const todayStart = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const targetStart = new Date(
    parsedDate.getFullYear(),
    parsedDate.getMonth(),
    parsedDate.getDate()
  );

  return Math.max(0, Math.round((todayStart - targetStart) / 86400000));
}

export function buildFreshnessInfo(meta, predictions) {
  const observationValue = meta?.latestObservationDate || getLatestValueByDate(
    predictions.map(prediction => prediction.latestObservationDate)
  );
  const forecastValue = meta?.forecastTargetDate || getLatestValueByDate(
    predictions.map(extractForecastDateValue)
  );
  const generatedValue = meta?.updatedAt || null;
  const fallbackAgeDays = Number(meta?.observationAgeDays);
  const ageDays = differenceFromTodayInDays(observationValue);
  const resolvedAgeDays = ageDays ?? (Number.isNaN(fallbackAgeDays) ? null : fallbackAgeDays);
  const configuredThreshold = Number(meta?.staleDataThresholdDays);
  const staleThresholdDays = Number.isNaN(configuredThreshold) ? 3 : configuredThreshold;

  return {
    available: Boolean(observationValue || forecastValue || generatedValue),
    observationValue,
    forecastValue,
    generatedValue,
    ageDays: resolvedAgeDays,
    staleThresholdDays
  };
}

export function formatDrainageConfidence(district) {
  const label = district?.drainageConfidence || 'Tidak tersedia';
  const score = Number(district?.drainageConfidenceScore);

  if (Number.isNaN(score) || score <= 0) {
    return label;
  }

  return `${label} (${score.toLocaleString('id-ID', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1
  })}/100)`;
}

export function getProbabilityPercentValue(district) {
  const predictedClassProbability = Number(district?.predictedClassProbabilityPercent);

  if (!Number.isNaN(predictedClassProbability)) {
    return predictedClassProbability;
  }

  const probabilityPercent = Number(district?.probabilityWaspadaPercent);
  if (!Number.isNaN(probabilityPercent)) {
    return probabilityPercent;
  }

  const riskScore = Number(district?.riskScore);
  if (!Number.isNaN(riskScore)) {
    return riskScore <= 1 ? riskScore * 100 : riskScore;
  }

  return NaN;
}

export function formatHistoryDescription(entry, districtName) {
  const fallbackDescription = 'Detail aktivitas belum tersedia.';
  const rawDescription = String(entry?.description || '').trim();
  const rawDistrictName = String(entry?.districtName || '').trim();

  if (!rawDescription) {
    return fallbackDescription;
  }

  if (!rawDistrictName || !districtName) {
    return rawDescription;
  }

  return rawDescription.replaceAll(rawDistrictName, districtName);
}
