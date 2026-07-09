const map = L.map('map').setView([-6.225, 106.925], 11);

const baseMap = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
  attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
  subdomains: 'abcd',
  maxZoom: 20
}).addTo(map);

L.control.scale({ imperial: false }).addTo(map);

function buildPredictionEndpoints() {
  const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
  const hostName = window.location.hostname || '127.0.0.1';
  const liveCandidates = [
    'api/predictions',
    `${protocol}//${hostName}:8000/api/predictions`
  ];

  if (hostName !== 'localhost') {
    liveCandidates.push(`${protocol}//localhost:8000/api/predictions`);
  }

  if (hostName !== '127.0.0.1') {
    liveCandidates.push(`${protocol}//127.0.0.1:8000/api/predictions`);
  }

  liveCandidates.push('data/east-jakarta-predictions.json');
  return [...new Set(liveCandidates)];
}

const PREDICTION_ENDPOINTS = buildPredictionEndpoints();

const elements = {
  districtSelect: document.getElementById('districtSelect'),
  resetViewButton: document.getElementById('resetViewButton'),
  statDistrictCount: document.getElementById('statDistrictCount'),
  statHighRiskCount: document.getElementById('statHighRiskCount'),
  statAverageRainfall: document.getElementById('statAverageRainfall'),
  statUpdatedAt: document.getElementById('statUpdatedAt'),
  statRefreshInterval: document.getElementById('statRefreshInterval'),
  districtCardsTrack: document.getElementById('districtCardsTrack'),
  districtCardsPrev: document.getElementById('districtCardsPrev'),
  districtCardsNext: document.getElementById('districtCardsNext'),
  environmentBanner: document.getElementById('environmentBanner'),
  dataFreshnessNotice: document.getElementById('dataFreshnessNotice'),
  publicModelNoticeLead: document.getElementById('publicModelNoticeLead'),
  publicModelNoticeAccuracy: document.getElementById('publicModelNoticeAccuracy'),
  mapSubtitle: document.getElementById('mapSubtitle'),
  dataStatus: document.getElementById('dataStatus'),
  detailContent: document.getElementById('detailContent')
};

const state = {
  meta: null,
  districtLookup: new Map(),
  districts: [],
  geojsonLayer: null,
  heatOverlay: null,
  bounds: null,
  selectedKey: null,
  sourceUrl: null
};

function normalizeDistrictName(name) {
  return (name || '')
    .toLowerCase()
    .replace(/\s+/g, '')
    .trim();
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function getGeoDistrictName(feature) {
  return feature.properties.name || '';
}

function formatNumber(value) {
  return new Intl.NumberFormat('id-ID').format(value);
}

function formatUpdatedAt(value) {
  const date = parseDateValue(value);

  if (!date) {
    return 'Tidak tersedia';
  }

  return new Intl.DateTimeFormat('id-ID', {
    dateStyle: 'medium',
    timeStyle: 'short'
  }).format(date);
}

function parseDateValue(value) {
  const normalizedValue = String(value ?? '').trim();

  if (!normalizedValue) {
    return null;
  }

  const date = /^\d{4}-\d{2}-\d{2}$/.test(normalizedValue)
    ? new Date(`${normalizedValue}T00:00:00`)
    : new Date(normalizedValue);

  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDateOnly(value) {
  const date = parseDateValue(value);

  if (!date) {
    return 'Tidak tersedia';
  }

  return new Intl.DateTimeFormat('id-ID', {
    dateStyle: 'medium'
  }).format(date);
}

function formatPercent(value) {
  const numericValue = Number(value);

  if (Number.isNaN(numericValue)) {
    return 'Tidak tersedia';
  }

  return `${numericValue.toLocaleString('id-ID', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1
  })}%`;
}

function renderEnvironmentBanner() {
  if (!elements.environmentBanner) {
    return;
  }

  const meta = state.meta || {};
  if (!meta.isStaging) {
    elements.environmentBanner.hidden = true;
    elements.environmentBanner.textContent = '';
    elements.environmentBanner.className = 'environment-banner';
    return;
  }

  const label = meta.deploymentEnvironmentLabel || 'STAGING';
  const appName = meta.appName || 'FloodGIS Jakarta Timur';
  elements.environmentBanner.hidden = false;
  elements.environmentBanner.className = 'environment-banner staging';
  elements.environmentBanner.textContent = `${appName} - ${label}: versi uji coba, bukan web utama.`;
}

function formatSignedPercent(value) {
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

function formatRiskScore(value) {
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

function formatRainMm(value) {
  if (value === null || value === undefined || value === '') {
    return 'Tidak tersedia';
  }

  const numericValue = Number(value);

  if (Number.isNaN(numericValue)) {
    return 'Tidak tersedia';
  }

  return `${numericValue.toLocaleString('id-ID', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1
  })} mm`;
}

function getPredictedClassConfidencePercentValue(prediction) {
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

function getRainfallDisplayValue(prediction) {
  if (prediction?.predictedRainfallLabel) {
    return prediction.predictedRainfallLabel;
  }

  if (prediction?.predictedRainfallRange) {
    return prediction.predictedRainfallRange;
  }

  const rainfallMm = Number(prediction?.predictedRainfallMm);
  if (!Number.isNaN(rainfallMm)) {
    return `${rainfallMm} mm`;
  }

  return 'Tidak tersedia';
}

function getShowcaseForecastDate(prediction) {
  const label = String(prediction?.forecastLabel || '').trim();
  return label ? label.replace(/^Prediksi\s+/i, '') : 'Prediksi aktif';
}

function getShowcaseRiskPercent(prediction) {
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

function formatDateNumeric(value) {
  const date = parseDateValue(value);

  if (!date) {
    return '-';
  }

  const day = String(date.getDate()).padStart(2, '0');
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const year = date.getFullYear();
  return `${day}-${month}-${year}`;
}

function getSemanticRiskLevelLabel(prediction) {
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

function getDetailRiskLabel(prediction) {
  const level = Number(prediction?.webgisLevel);

  if (level === 1) {
    return 'Sangat Rendah';
  }

  if (level === 2) {
    return 'Ringan';
  }

  if (level === 3) {
    return 'Sedang';
  }

  if (level === 4) {
    return 'Tinggi';
  }

  return getSemanticRiskLevelLabel(prediction);
}

function getDetailRiskDisplay(prediction) {
  const riskLabel = getDetailRiskLabel(prediction);
  const riskPercent = getShowcaseRiskPercent(prediction);

  if (riskPercent === null) {
    return riskLabel;
  }

  return `${riskLabel} (${formatNumber(riskPercent)}%)`;
}

function getDetailRainDisplay(prediction) {
  const summary = getShowcaseRainSummary(prediction);
  const predictedRainfallMm = Number(prediction?.predictedRainfallMm);

  if (!Number.isNaN(predictedRainfallMm)) {
    return `${summary} (${formatRainMm(predictedRainfallMm)})`;
  }

  const latestObservedRainfallMm = Number(prediction?.latestObservedRainfallMm);
  if (!Number.isNaN(latestObservedRainfallMm)) {
    return `${summary} (${formatRainMm(latestObservedRainfallMm)})`;
  }

  if (prediction?.predictedRainfallRange) {
    return `${summary} (${prediction.predictedRainfallRange})`;
  }

  return summary;
}

function getShowcaseRainSummary(prediction) {
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

function getShowcaseIconMarkup(prediction) {
  switch (Number(prediction?.predictedRainfallClassIndex)) {
    case 0:
      return `
        <svg viewBox="0 0 120 90" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <circle cx="44" cy="30" r="18" fill="#FFF1A8" stroke="#324A72" stroke-width="3"/>
          <path d="M44 5V12M44 48V55M19 30H12M76 30H69M26 12L31 17M26 48L31 43M62 12L57 17M62 48L57 43" stroke="#324A72" stroke-width="3" stroke-linecap="round"/>
          <path d="M39 63C31 63 25 57 25 49C25 42 31 36 38 36C40 27 48 21 58 21C70 21 79 30 79 42C85 43 90 49 90 56C90 64 83 70 75 70H39Z" fill="#D2EBEE" stroke="#324A72" stroke-width="3" stroke-linejoin="round"/>
        </svg>
      `;
    case 1:
      return `
        <svg viewBox="0 0 120 90" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <path d="M37 18C44 18 50 24 50 31C50 35 48 39 45 42C54 42 61 49 61 58C61 66 54 73 46 73C38 73 31 67 31 58H27C18 58 11 51 11 42C11 33 18 26 27 26C30 21 33 18 37 18Z" fill="#E8EDF7" stroke="#324A72" stroke-width="3" stroke-linejoin="round"/>
          <path d="M45 63C37 63 31 57 31 49C31 42 37 36 44 36C46 28 54 22 64 22C76 22 85 31 85 43C91 44 96 50 96 57C96 65 89 71 81 71H45Z" fill="#D2EBEE" stroke="#324A72" stroke-width="3" stroke-linejoin="round"/>
        </svg>
      `;
    case 2:
      return `
        <svg viewBox="0 0 120 90" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <path d="M34 58C25 58 18 51 18 42C18 33 25 26 34 26C37 18 44 13 54 13C66 13 75 22 76 34C83 35 88 41 88 48C88 56 81 62 73 62H34V58Z" fill="#D9EAF4" stroke="#324A72" stroke-width="3" stroke-linejoin="round"/>
          <path d="M40 69L35 79" stroke="#2A7FB0" stroke-width="4" stroke-linecap="round"/>
          <path d="M57 69L52 79" stroke="#2A7FB0" stroke-width="4" stroke-linecap="round"/>
          <path d="M74 69L69 79" stroke="#2A7FB0" stroke-width="4" stroke-linecap="round"/>
        </svg>
      `;
    case 3:
      return `
        <svg viewBox="0 0 120 90" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <path d="M34 56C25 56 18 49 18 40C18 31 25 24 34 24C37 16 45 11 55 11C68 11 77 20 78 33C85 34 90 40 90 47C90 55 83 61 75 61H34V56Z" fill="#D7DEE9" stroke="#324A72" stroke-width="3" stroke-linejoin="round"/>
          <path d="M52 61L44 76H55L49 88L71 67H58L65 61H52Z" fill="#F4C542" stroke="#324A72" stroke-width="3" stroke-linejoin="round"/>
          <path d="M78 66L73 76" stroke="#2A7FB0" stroke-width="4" stroke-linecap="round"/>
        </svg>
      `;
    default:
      return `
        <svg viewBox="0 0 120 90" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <path d="M39 63C31 63 25 57 25 49C25 42 31 36 38 36C40 27 48 21 58 21C70 21 79 30 79 42C85 43 90 49 90 56C90 64 83 70 75 70H39Z" fill="#D2EBEE" stroke="#324A72" stroke-width="3" stroke-linejoin="round"/>
        </svg>
      `;
  }
}

function getRiskColor(value) {
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
      return '#2f9e44';
    case 'ringan':
      return '#f0c419';
    case 'rendah':
      return '#2f9e44';
    case 'sedang':
      return '#f76707';
    case 'lebat/ekstrem':
    case 'lebat':
    case 'tinggi':
      return '#e03131';
    default:
      return '#94a3b8';
  }
}

function getRiskTone(value) {
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
      return 'low';
    case 'ringan':
      return 'medium';
    case 'rendah':
      return 'low';
    case 'sedang':
      return level >= 3 ? 'watch' : 'medium';
    case 'lebat/ekstrem':
    case 'lebat':
      return 'high';
    case 'tinggi':
      return 'high';
    default:
      return 'low';
  }
}

function setStatus(text, tone) {
  elements.dataStatus.textContent = text;
  elements.dataStatus.className = 'status-pill';

  if (tone) {
    elements.dataStatus.classList.add(tone);
  }
}

function setFreshnessNotice(message, tone) {
  if (!elements.dataFreshnessNotice) {
    return;
  }

  if (!message) {
    elements.dataFreshnessNotice.hidden = true;
    elements.dataFreshnessNotice.textContent = '';
    elements.dataFreshnessNotice.className = 'data-freshness-banner';
    return;
  }

  elements.dataFreshnessNotice.hidden = false;
  elements.dataFreshnessNotice.className = `data-freshness-banner ${tone || ''}`.trim();
  elements.dataFreshnessNotice.innerHTML = message;
}

function isLiveBackendSource() {
  return Boolean(state.sourceUrl && state.sourceUrl.includes('api/predictions'));
}

function getSourceStatus() {
  if (isLiveBackendSource()) {
    return {
      text: 'Backend Live',
      tone: 'success'
    };
  }

  return {
    text: 'JSON Cadangan',
    tone: 'fallback'
  };
}

function getRequestedDistrictKeyFromUrl() {
  const url = new URL(window.location.href);
  return normalizeDistrictName(url.searchParams.get('district') || '');
}

function updateDistrictUrlState(key) {
  const url = new URL(window.location.href);

  if (key) {
    url.searchParams.set('district', key);
  } else {
    url.searchParams.delete('district');
  }

  const nextUrl = `${url.pathname}${url.search}${url.hash}`;
  if (nextUrl !== `${window.location.pathname}${window.location.search}${window.location.hash}`) {
    window.history.replaceState({}, '', nextUrl);
  }
}

function getPredictionEntries() {
  return Array.from(state.districtLookup.values());
}

function getLatestValueByDate(candidates) {
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

function extractForecastDateValue(prediction) {
  return String(prediction?.forecastLabel || '')
    .replace(/^Prediksi\s+/i, '')
    .trim();
}

function differenceFromTodayInDays(value) {
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

function buildFreshnessInfo() {
  const predictions = getPredictionEntries();
  const observationValue = state.meta?.latestObservationDate || getLatestValueByDate(
    predictions.map(prediction => prediction.latestObservationDate)
  );
  const forecastValue = state.meta?.forecastTargetDate || getLatestValueByDate(
    predictions.map(extractForecastDateValue)
  );
  const generatedValue = state.meta?.updatedAt || null;
  const fallbackAgeDays = Number(state.meta?.observationAgeDays);
  const ageDays = differenceFromTodayInDays(observationValue);
  const resolvedAgeDays = ageDays ?? (Number.isNaN(fallbackAgeDays) ? null : fallbackAgeDays);
  const configuredThreshold = Number(state.meta?.staleDataThresholdDays);
  const staleThresholdDays = Number.isNaN(configuredThreshold) ? 3 : configuredThreshold;

  if (!observationValue && !forecastValue && !generatedValue) {
    return {
      available: false
    };
  }

  const messageParts = [];
  if (observationValue) {
    messageParts.push(`Observasi terakhir ${formatDateOnly(observationValue)}.`);
  }
  if (forecastValue) {
    messageParts.push(`Prediksi ditujukan untuk ${formatDateOnly(forecastValue)}.`);
  }
  if (generatedValue) {
    messageParts.push(`Payload dibuat ${formatUpdatedAt(generatedValue)}.`);
  }

  let tone = 'fresh';
  if (!isLiveBackendSource()) {
    tone = 'warning';
    messageParts.unshift(
      'Sumber data saat ini memakai file JSON cadangan karena backend live tidak tersedia.'
    );
  }

  if (resolvedAgeDays !== null && resolvedAgeDays >= staleThresholdDays) {
    tone = 'warning';
    messageParts.push(
      `Data observasi tertinggal ${resolvedAgeDays} hari dari tanggal akses, jadi hasil perlu dibaca dengan lebih hati-hati.`
    );
  } else if (resolvedAgeDays !== null) {
    messageParts.push(`Usia data observasi saat dibuka sekitar ${resolvedAgeDays} hari.`);
  }

  return {
    available: true,
    tone: tone,
    message: messageParts.join(' '),
    observationValue: observationValue,
    forecastValue: forecastValue,
    generatedValue: generatedValue,
    ageDays: resolvedAgeDays
  };
}

function renderFreshnessNotice() {
  const freshnessInfo = buildFreshnessInfo();

  if (!freshnessInfo.available || (isLiveBackendSource() && freshnessInfo.tone === 'fresh')) {
    setFreshnessNotice('', '');
    return;
  }

  const title = !isLiveBackendSource()
    ? 'Sedang memakai JSON cadangan.'
    : freshnessInfo.tone === 'warning'
    ? 'Perlu cek freshness data.'
    : 'Status freshness data.';
  setFreshnessNotice(
    `<strong>${escapeHtml(title)}</strong> ${escapeHtml(freshnessInfo.message)}`,
    freshnessInfo.tone
  );
}

function renderModelNotice() {
  if (!elements.publicModelNoticeLead || !elements.publicModelNoticeAccuracy) {
    return;
  }

  const meta = state.meta || {};
  elements.publicModelNoticeLead.textContent =
    'Web ini membantu visualisasi awal risiko banjir per kecamatan dan tidak menggantikan peringatan operasional final.';

  const noteParts = [];
  if (meta.modelAccuracyNote) {
    noteParts.push(meta.modelAccuracyNote);
  }
  if (meta.conversionNote) {
    noteParts.push('Skor risiko diturunkan dari prediksi kelas curah hujan dan penyesuaian drainase terbatas.');
  }
  if (!isLiveBackendSource()) {
    noteParts.push('Saat ini tampilan menggunakan file JSON cadangan, sehingga data yang terlihat bukan hasil hitung backend live pada saat ini.');
  }

  elements.publicModelNoticeAccuracy.textContent = noteParts.join(' ');
}

function getPredictionByKey(key) {
  return state.districtLookup.get(key);
}

function buildPredictionLookup(predictionPayload) {
  state.meta = predictionPayload.meta;
  state.districtLookup = new Map(
    predictionPayload.districts.map(district => [
      normalizeDistrictName(district.name),
      district
    ])
  );
  renderEnvironmentBanner();
  renderFreshnessNotice();
  renderModelNotice();
}

function filterEastJakartaGeojson(geojson) {
  return {
    ...geojson,
    features: geojson.features.filter(feature =>
      state.districtLookup.has(normalizeDistrictName(getGeoDistrictName(feature)))
    )
  };
}

function getFeatureStyle(feature, isSelected) {
  const district = getPredictionByKey(normalizeDistrictName(getGeoDistrictName(feature)));
  const fillColor = district ? getRiskColor(district) : '#94a3b8';

  return {
    fillColor: fillColor,
    weight: isSelected ? 3 : 1.4,
    color: isSelected ? '#17324d' : '#ffffff',
    dashArray: isSelected ? '' : '3',
    fillOpacity: isSelected ? 0.88 : 0.76
  };
}

function refreshDistrictStyles() {
  if (!state.geojsonLayer) {
    return;
  }

  state.geojsonLayer.eachLayer(layer => {
    const featureKey = normalizeDistrictName(getGeoDistrictName(layer.feature));
    const isSelected = featureKey === state.selectedKey;
    layer.setStyle(getFeatureStyle(layer.feature, isSelected));
  });
}

function renderPopupContent(prediction) {
  const forecastText = prediction.forecastLabel || 'Prediksi aktif';
  const modelInfo = !Number.isNaN(getPredictedClassConfidencePercentValue(prediction))
    ? `<br>Confidence kelas dominan: ${formatPercent(getPredictedClassConfidencePercentValue(prediction))}`
    : '';
  const semanticRiskLabel = getSemanticRiskLevelLabel(prediction);
  const riskInfo = semanticRiskLabel
    ? `<br>Tingkat risiko: ${semanticRiskLabel}`
    : '';
  const drainageInfo = prediction.drainageCondition
    ? `<br>Drainase: ${prediction.drainageCondition}`
    : '';

  return `
    <strong>${prediction.label}</strong><br>
    ${forecastText}: ${getRainfallDisplayValue(prediction)}
    ${drainageInfo}
    ${riskInfo}
    ${modelInfo}
  `;
}

function renderEmptyDetail() {
  elements.detailContent.innerHTML = `
    <div class="detail-sheet detail-sheet-empty">
      <div class="empty-state">
        Pilih kecamatan dari peta atau dropdown untuk melihat detail wilayah.
      </div>
    </div>
  `;
}

function renderDetailMetric(label, value) {
  return `
    <div class="detail-stack-card">
      <span>${label}</span>
      <strong>${value}</strong>
    </div>
  `;
}

function csvEscape(value) {
  const text = String(value ?? '');

  if (text.includes('"') || text.includes(',') || text.includes('\n')) {
    return `"${text.replaceAll('"', '""')}"`;
  }

  return text;
}

function downloadSelectedDistrictCsv() {
  const district = state.districts.find(item => item.key === state.selectedKey);

  if (!district) {
    return;
  }

  const prediction = district.prediction;
  const rows = [
    ['Kecamatan', prediction.label],
    ['Tanggal Prediksi', prediction.forecastLabel || '-'],
    ['Tingkat Risiko', getDetailRiskDisplay(prediction)],
    ['Curah Hujan', getDetailRainDisplay(prediction)],
    ['Kondisi Drainase', prediction.drainageCondition || '-'],
    ['Rata-Rata 3 Hari', formatRainMm(prediction.recentThreeDayAverageMm)],
    ['Potensi Hujan Lebat/Ekstrem', formatPercent(prediction.probabilityWaspadaPercent)],
    ['Confidence Kelas Dominan', formatPercent(getPredictedClassConfidencePercentValue(prediction))],
    ['Rekomendasi', prediction.recommendation || '-'],
    ['Catatan Drainase', prediction.drainageNote || '-']
  ];
  const csv = rows.map(row => row.map(csvEscape).join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');

  link.href = url;
  link.download = `detail-${prediction.label.toLowerCase().replace(/\s+/g, '-')}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

function renderDetailContent(district) {
  const prediction = district.prediction;
  const forecastValue = String(prediction.forecastLabel || '').replace(/^Prediksi\s+/i, '').trim();

  elements.detailContent.innerHTML = `
    <div class="detail-sheet">
      <div class="detail-sheet-head">
        <h3 class="detail-sheet-title">${prediction.label}</h3>
        <p class="detail-sheet-date">${formatDateNumeric(forecastValue || prediction.latestObservationDate)}</p>
      </div>

      <div class="detail-sheet-stack">
        ${renderDetailMetric('Tingkat Risiko', getDetailRiskDisplay(prediction))}
        ${renderDetailMetric('Curah Hujan', getDetailRainDisplay(prediction))}
        ${renderDetailMetric('Kondisi Drainase', prediction.drainageCondition || 'Tidak tersedia')}
        ${renderDetailMetric('Rata-Rata 3 Hari', formatRainMm(prediction.recentThreeDayAverageMm))}
        ${renderDetailMetric('Potensi Hujan Lebat/Ekstrem', formatPercent(prediction.probabilityWaspadaPercent))}
      </div>

      <button id="downloadDistrictCsvButton" class="detail-download-button" type="button">
        Download File CSV
      </button>
    </div>
  `;
}

function updateMapSubtitle(selectedDistrict) {
  if (selectedDistrict) {
    const forecastLabel = selectedDistrict.prediction.forecastLabel
      ? ` (${selectedDistrict.prediction.forecastLabel})`
      : '';

    elements.mapSubtitle.textContent =
      `${selectedDistrict.prediction.label}${forecastLabel} sedang ditampilkan sebagai wilayah fokus.`;
    return;
  }

  elements.mapSubtitle.textContent =
    `Menampilkan ${state.districts.length} kecamatan berdasarkan prediksi aktif dan kondisi wilayah terbaru.`;
}

function selectDistrict(key, options) {
  const config = {
    flyTo: false,
    openPopup: false,
    ...options
  };

  const district = state.districts.find(item => item.key === key);

  if (!district) {
    return;
  }

  state.selectedKey = key;
  elements.districtSelect.value = key;
  updateDistrictUrlState(key);

  refreshDistrictStyles();
  renderDetailContent(district);
  updateMapSubtitle(district);
  syncShowcaseSelection(config.keepCardInView !== false);

  if (config.flyTo) {
    map.flyToBounds(district.layer.getBounds(), {
      padding: [36, 36],
      duration: 0.8
    });
  }

  if (config.openPopup) {
    district.layer.openPopup();
  }
}

function populateDistrictSelect() {
  const options = state.districts
    .slice()
    .sort((a, b) => a.prediction.label.localeCompare(b.prediction.label, 'id'))
    .map(district =>
      `<option value="${district.key}">${district.prediction.label}</option>`
    );

  elements.districtSelect.innerHTML = `
    <option value="">Pilih kecamatan</option>
    ${options.join('')}
  `;
}

function updateShowcaseButtons() {
  if (!elements.districtCardsTrack || !elements.districtCardsPrev || !elements.districtCardsNext) {
    return;
  }

  const track = elements.districtCardsTrack;
  const hasOverflow = track.scrollWidth > track.clientWidth + 8;
  const maxScroll = Math.max(0, track.scrollWidth - track.clientWidth - 4);

  elements.districtCardsPrev.disabled = !hasOverflow || track.scrollLeft <= 4;
  elements.districtCardsNext.disabled = !hasOverflow || track.scrollLeft >= maxScroll;
}

function syncShowcaseSelection(scrollIntoView) {
  if (!elements.districtCardsTrack) {
    return;
  }

  const track = elements.districtCardsTrack;
  const cards = elements.districtCardsTrack.querySelectorAll('.showcase-card');
  cards.forEach(card => {
    card.classList.toggle('active', card.dataset.key === state.selectedKey);
  });

  if (scrollIntoView && state.selectedKey) {
    const selector = `.showcase-card[data-key="${state.selectedKey}"]`;
    const activeCard = track.querySelector(selector);
    if (activeCard) {
      const cardCenter = activeCard.offsetLeft + (activeCard.offsetWidth / 2);
      const targetLeft = Math.max(0, cardCenter - (track.clientWidth / 2));

      track.scrollTo({
        left: targetLeft,
        behavior: 'smooth'
      });
    }
  }

  updateShowcaseButtons();
}

function renderDistrictShowcase() {
  if (!elements.districtCardsTrack) {
    return;
  }

  const orderedDistricts = state.districts
    .slice()
    .sort((left, right) => {
      const riskDifference = Number(right.prediction.riskScore || 0) - Number(left.prediction.riskScore || 0);
      if (riskDifference !== 0) {
        return riskDifference;
      }

      return left.prediction.label.localeCompare(right.prediction.label, 'id');
    });

  if (orderedDistricts.length === 0) {
    elements.districtCardsTrack.innerHTML = `
      <article class="showcase-empty-card">
        Ringkasan kecamatan belum tersedia.
      </article>
    `;
    updateShowcaseButtons();
    return;
  }

  elements.districtCardsTrack.innerHTML = orderedDistricts
    .map(district => {
      const prediction = district.prediction;
      const tone = getRiskTone(prediction);
      const riskPercent = getShowcaseRiskPercent(prediction);
      const valueMarkup = riskPercent === null
        ? '-'
        : `${formatNumber(riskPercent)}<span>%</span>`;

      return `
        <article class="showcase-card ${tone}" data-key="${district.key}" tabindex="0" role="button" aria-label="Pilih ${escapeHtml(prediction.label)}">
          <div class="showcase-card-top">
            <h3 class="showcase-card-title">${escapeHtml(prediction.label)}</h3>
            <p class="showcase-card-subtitle">${escapeHtml(getShowcaseForecastDate(prediction))}</p>
          </div>
          <div class="showcase-card-icon">
            ${getShowcaseIconMarkup(prediction)}
          </div>
          <p class="showcase-card-value">${valueMarkup}</p>
          <p class="showcase-card-label">${escapeHtml(getShowcaseRainSummary(prediction))}</p>
          <span class="risk-badge showcase-card-badge ${tone}">${escapeHtml(getSemanticRiskLevelLabel(prediction))}</span>
        </article>
      `;
    })
    .join('');

  syncShowcaseSelection(false);
  requestAnimationFrame(updateShowcaseButtons);
}

function scrollDistrictCards(direction) {
  if (!elements.districtCardsTrack) {
    return;
  }

  elements.districtCardsTrack.scrollBy({
    left: direction * Math.max(220, elements.districtCardsTrack.clientWidth * 0.82),
    behavior: 'smooth'
  });
}

function updateSummaryStats() {
  const freshnessInfo = buildFreshnessInfo();
  const totalDistricts = state.districts.length;
  const highRiskCount = state.districts.filter(
    district => Number(district.prediction.webgisLevel) >= 3
  ).length;
  const averageRiskScore = totalDistricts === 0
    ? 0
    : Math.round(
        state.districts.reduce(
          (sum, district) => sum + ((Number(district.prediction.riskScore) || 0) * 100),
          0
        ) / totalDistricts
      );

  elements.statDistrictCount.textContent = formatNumber(totalDistricts);
  elements.statHighRiskCount.textContent = formatNumber(highRiskCount);
  elements.statAverageRainfall.textContent = `${formatNumber(averageRiskScore)} / 100`;
  elements.statUpdatedAt.textContent = freshnessInfo.observationValue
    ? formatDateOnly(freshnessInfo.observationValue)
    : formatUpdatedAt(state.meta.updatedAt);

  const noteParts = [];
  if (freshnessInfo.forecastValue) {
    noteParts.push(`Prediksi: ${formatDateOnly(freshnessInfo.forecastValue)}`);
  }
  if (freshnessInfo.generatedValue) {
    noteParts.push(`Payload: ${formatUpdatedAt(freshnessInfo.generatedValue)}`);
  }
  if (freshnessInfo.ageDays !== null) {
    noteParts.push(`Usia data: ${freshnessInfo.ageDays} hari`);
  } else if (state.meta.refreshInterval) {
    noteParts.push(`Pembaruan: ${state.meta.refreshInterval}`);
  }

  elements.statRefreshInterval.textContent = noteParts.join(' | ') || 'Menunggu informasi pembaruan data';
}

function createHeatOverlay() {
  const heatPoints = state.districts.map(district => [
    district.center.lat,
    district.center.lng,
    district.prediction.riskScore
  ]);

  const heatLayer = L.heatLayer(heatPoints, {
    radius: 42,
    blur: 30,
    minOpacity: 0.4,
    maxZoom: 13,
    gradient: {
      0.2: '#2f9e44',
      0.55: '#f0c419',
      1.0: '#e03131'
    }
  });

  const labelLayer = L.layerGroup(
    state.districts.map(district => {
      const marker = L.circleMarker(district.center, {
        radius: 7,
        weight: 1.5,
        color: '#ffffff',
        fillColor: getRiskColor(district.prediction),
        fillOpacity: 0.98
      });

      marker.bindTooltip(district.prediction.label, {
        permanent: true,
        direction: 'top',
        offset: [0, -12],
        className: 'heat-label'
      });

      marker.bindPopup(renderPopupContent(district.prediction));
      marker.on('click', () => {
        selectDistrict(district.key, {
          flyTo: true,
          openPopup: false
        });
      });

      return marker;
    })
  );

  state.heatOverlay = L.layerGroup([heatLayer, labelLayer]).addTo(map);
}

function addRiskLegendControl() {
  const legend = L.control({ position: 'bottomright' });

  legend.onAdd = function onAdd() {
    const container = L.DomUtil.create('div', 'map-risk-legend');
    container.innerHTML = `
      <strong>Legenda Risiko</strong>
      <ul>
        <li><span class="map-risk-legend-swatch level-1"></span>Level 1: Sangat Rendah</li>
        <li><span class="map-risk-legend-swatch level-2"></span>Level 2: Ringan</li>
        <li><span class="map-risk-legend-swatch level-3"></span>Level 3: Sedang</li>
        <li><span class="map-risk-legend-swatch level-4"></span>Level 4: Tinggi</li>
      </ul>
    `;

    L.DomEvent.disableClickPropagation(container);
    return container;
  };

  legend.addTo(map);
}

function initializeMap(filteredGeojson) {
  state.districts = [];

  state.geojsonLayer = L.geoJSON(filteredGeojson, {
    style: feature => getFeatureStyle(feature, false),
    onEachFeature: (feature, layer) => {
      const key = normalizeDistrictName(getGeoDistrictName(feature));
      const prediction = getPredictionByKey(key);

      if (!prediction) {
        return;
      }

      const district = {
        key: key,
        prediction: prediction,
        layer: layer,
        center: layer.getBounds().getCenter()
      };

      state.districts.push(district);

      layer.bindPopup(renderPopupContent(prediction));
      layer.on({
        mouseover: event => {
          event.target.setStyle({
            weight: 3,
            color: '#17324d',
            fillOpacity: 0.9
          });

          if (!L.Browser.ie && !L.Browser.opera && !L.Browser.edge) {
            event.target.bringToFront();
          }
        },
        mouseout: refreshDistrictStyles,
        click: () => {
          selectDistrict(key, {
            flyTo: true,
            openPopup: true
          });
        }
      });
    }
  }).addTo(map);

  createHeatOverlay();

  L.control.layers(
    {
      'OpenStreetMap': baseMap
    },
    {
      'Peta Tematik Risiko': state.geojsonLayer,
      'Overlay Heatmap + Label': state.heatOverlay
    },
    {
      collapsed: true
    }
  ).addTo(map);

  addRiskLegendControl();

  state.bounds = state.geojsonLayer.getBounds();
  map.fitBounds(state.bounds, { padding: [26, 26] });
}

function bindInteractions() {
  elements.districtSelect.addEventListener('change', event => {
    const key = event.target.value;

    if (!key) {
      state.selectedKey = null;
      updateDistrictUrlState('');
      refreshDistrictStyles();
      updateMapSubtitle();
      renderEmptyDetail();
      syncShowcaseSelection(false);
      return;
    }

    selectDistrict(key, {
      flyTo: true,
      openPopup: true
    });
  });

  elements.resetViewButton.addEventListener('click', () => {
    if (state.bounds) {
      map.flyToBounds(state.bounds, {
        padding: [26, 26],
        duration: 0.8
      });
    }
  });

  if (elements.districtCardsPrev && elements.districtCardsNext && elements.districtCardsTrack) {
    elements.districtCardsPrev.addEventListener('click', () => {
      scrollDistrictCards(-1);
    });

    elements.districtCardsNext.addEventListener('click', () => {
      scrollDistrictCards(1);
    });

    elements.districtCardsTrack.addEventListener('click', event => {
      const card = event.target.closest('.showcase-card[data-key]');
      if (!card) {
        return;
      }

      selectDistrict(card.dataset.key, {
        flyTo: true,
        openPopup: true,
        keepCardInView: true
      });
    });

    elements.districtCardsTrack.addEventListener('keydown', event => {
      const card = event.target.closest('.showcase-card[data-key]');
      if (!card) {
        return;
      }

      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        selectDistrict(card.dataset.key, {
          flyTo: true,
          openPopup: true,
          keepCardInView: true
        });
      }
    });

    elements.districtCardsTrack.addEventListener('scroll', updateShowcaseButtons, { passive: true });
    window.addEventListener('resize', updateShowcaseButtons);
  }

  if (elements.detailContent) {
    elements.detailContent.addEventListener('click', event => {
      const button = event.target.closest('#downloadDistrictCsvButton');

      if (!button) {
        return;
      }

      downloadSelectedDistrictCsv();
    });
  }

}

function fetchJson(url) {
  return fetch(url).then(response => {
    if (!response.ok) {
      throw new Error(`Gagal memuat ${url} (${response.status})`);
    }

    return response.json();
  });
}

async function fetchFirstAvailableJson(urls) {
  let lastError = null;

  for (const url of urls) {
    try {
      return {
        payload: await fetchJson(url),
        sourceUrl: url
      };
    } catch (error) {
      lastError = error;
      console.warn(`Sumber data ${url} gagal dimuat.`, error);
    }
  }

  throw lastError || new Error('Tidak ada sumber data yang berhasil dimuat.');
}

function bootstrapApp() {
  setStatus('Memuat prediksi', '');
  setFreshnessNotice('', '');

  Promise.all([
    fetchJson('data/jkt.geojson'),
    fetchFirstAvailableJson(PREDICTION_ENDPOINTS)
  ])
    .then(([geojson, predictionResult]) => {
      const { payload: predictionPayload, sourceUrl } = predictionResult;
      state.sourceUrl = sourceUrl;
      buildPredictionLookup(predictionPayload);

      const filteredGeojson = filterEastJakartaGeojson(geojson);

      if (filteredGeojson.features.length === 0) {
        throw new Error('Tidak ada fitur Jakarta Timur yang cocok dengan data prediksi.');
      }

      initializeMap(filteredGeojson);
      populateDistrictSelect();
      renderDistrictShowcase();
      updateSummaryStats();
      updateMapSubtitle();
      const sourceStatus = getSourceStatus();
      setStatus(sourceStatus.text, sourceStatus.tone);

      const requestedDistrictKey = getRequestedDistrictKeyFromUrl();
      const primaryDistrict = state.districts
        .slice()
        .sort((a, b) => b.prediction.riskScore - a.prediction.riskScore)[0];
      const initialDistrict = state.districts.find(district => district.key === requestedDistrictKey)
        || primaryDistrict;

      if (initialDistrict) {
        selectDistrict(initialDistrict.key, {
          flyTo: false,
          openPopup: false
        });
      }
    })
    .catch(error => {
      console.error('Gagal memuat Web-GIS:', error);
      elements.mapSubtitle.textContent =
        'Terjadi kendala saat memuat peta atau data prediksi.';
      elements.detailContent.innerHTML = `
        <div class="empty-state">
          Gagal memuat data. Backend live dan file JSON cadangan sama-sama tidak bisa dibaca, jadi peta belum dapat ditampilkan.
        </div>
      `;
      if (elements.districtCardsTrack) {
        elements.districtCardsTrack.innerHTML = `
          <article class="showcase-empty-card">
            Gagal memuat ringkasan kecamatan.
          </article>
        `;
        requestAnimationFrame(updateShowcaseButtons);
      }
      setFreshnessNotice(
        '<strong>Freshness data tidak tersedia.</strong> Gagal membaca sumber prediksi aktif maupun fallback JSON.',
        'error'
      );
      setStatus('Gagal memuat', 'error');
    });
}

bindInteractions();
bootstrapApp();
