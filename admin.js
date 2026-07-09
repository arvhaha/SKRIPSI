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
  adminDataStatus: document.getElementById('adminDataStatus'),
  adminUpdatedAt: document.getElementById('adminUpdatedAt'),
  district: document.getElementById('adminDistrict'),
  rainfall: document.getElementById('predictedRainfallMm'),
  probability: document.getElementById('probabilityWaspadaPercent'),
  drainage: document.getElementById('drainageCondition'),
  drainageConfidence: document.getElementById('drainageConfidence'),
  drainageAdjustment: document.getElementById('drainageAdjustmentPercent'),
  riskCategory: document.getElementById('riskCategory'),
  riskScore: document.getElementById('riskScore'),
  webgisLevelLabel: document.getElementById('webgisLevelLabel'),
  forecastLabel: document.getElementById('forecastLabel'),
  latestObservationDate: document.getElementById('latestObservationDate'),
  latestObservedRainfallMm: document.getElementById('latestObservedRainfallMm'),
  recentThreeDayAverageMm: document.getElementById('recentThreeDayAverageMm'),
  summary: document.getElementById('summary'),
  drainageNote: document.getElementById('drainageNote'),
  recommendation: document.getElementById('recommendation'),
  tableBody: document.getElementById('predictionTableBody'),
  saveMessage: document.getElementById('saveMessage'),
  exportJsonButton: document.getElementById('exportJsonButton'),
  refreshDataButton: document.getElementById('refreshDataButton'),
  summaryDistrictCount: document.getElementById('summaryDistrictCount'),
  summaryTopRiskDistrict: document.getElementById('summaryTopRiskDistrict'),
  summaryTopRiskMeta: document.getElementById('summaryTopRiskMeta'),
  summaryAlertCount: document.getElementById('summaryAlertCount'),
  summaryAverageProbability: document.getElementById('summaryAverageProbability'),
  backendSourceLabel: document.getElementById('backendSourceLabel'),
  backendLatestObservation: document.getElementById('backendLatestObservation'),
  backendForecastTarget: document.getElementById('backendForecastTarget'),
  backendPayloadGenerated: document.getElementById('backendPayloadGenerated'),
  backendModel: document.getElementById('backendModel'),
  backendRainfallSource: document.getElementById('backendRainfallSource'),
  backendDrainageSource: document.getElementById('backendDrainageSource'),
  backendForecastHorizon: document.getElementById('backendForecastHorizon'),
  backendAccuracyNote: document.getElementById('backendAccuracyNote'),
  priorityDistrictList: document.getElementById('priorityDistrictList'),
  environmentBanner: document.getElementById('environmentBanner'),
  adminFreshnessNotice: document.getElementById('adminFreshnessNotice'),
  adminModelNoticeLead: document.getElementById('adminModelNoticeLead'),
  adminModelNoticeAccuracy: document.getElementById('adminModelNoticeAccuracy'),
  adminMapNavLink: document.getElementById('adminMapNavLink'),
  openPublicMapLink: document.getElementById('openPublicMapLink')
};

const state = {
  payload: null,
  selectedDistrictName: null,
  sourceUrl: null
};

function normalizeDistrictToken(value) {
  return String(value ?? '')
    .toLowerCase()
    .replace(/\s+/g, '')
    .trim();
}

function setTextContent(element, value) {
  if (element) {
    element.textContent = value;
  }
}

function setInputValue(element, value) {
  if (element) {
    element.value = value;
  }
}

function setInnerHtml(element, value) {
  if (element) {
    element.innerHTML = value;
  }
}

function ensureSelectedDistrict() {
  const districts = state.payload?.districts || [];

  if (districts.length === 0) {
    state.selectedDistrictName = null;
    return;
  }

  const selectedExists = districts.some(district => district.name === state.selectedDistrictName);
  state.selectedDistrictName = selectedExists ? state.selectedDistrictName : districts[0].name;
}

function scrollPreviewIntoView() {
  const previewSection = document.getElementById('previewSection');

  if (previewSection) {
    previewSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    return;
  }

  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function formatUpdatedAt(value) {
  const date = parseDateValue(value);

  if (!date) {
    return 'Belum tersedia';
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
    return 'Belum tersedia';
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

function formatMillimeter(value) {
  const numericValue = Number(value);

  if (Number.isNaN(numericValue)) {
    return '-';
  }

  return `${numericValue.toLocaleString('id-ID', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1
  })} mm`;
}

function formatScore(value) {
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

function formatDrainageConfidence(district) {
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

function getProbabilityPercentValue(district) {
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

function getRainfallDisplayValue(district) {
  if (district?.predictedRainfallLabel) {
    return district.predictedRainfallLabel;
  }

  if (district?.predictedRainfallRange) {
    return district.predictedRainfallRange;
  }

  return formatMillimeter(district?.predictedRainfallMm);
}

function getRiskTone(category, level) {
  if (Number(level) >= 4) {
    return 'high';
  }

  switch ((category || '').toLowerCase()) {
    case 'cerah':
      return 'low';
    case 'ringan':
      return 'medium';
    case 'rendah':
      return 'low';
    case 'sedang':
      return Number(level) >= 3 ? 'watch' : 'medium';
    case 'lebat/ekstrem':
    case 'lebat':
    case 'tinggi':
      return 'high';
    default:
      return 'low';
  }
}

function getSemanticRiskLevelLabel(district) {
  const level = Number(district?.webgisLevel);

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

  return district?.webgisLevelLabel || district?.riskCategory || '-';
}

function setMessage(message, tone) {
  if (!elements.saveMessage) {
    return;
  }

  elements.saveMessage.textContent = message;
  elements.saveMessage.className = `save-message ${tone || ''}`.trim();
}

function setFreshnessNotice(message, tone) {
  if (!elements.adminFreshnessNotice) {
    return;
  }

  if (!message) {
    elements.adminFreshnessNotice.hidden = true;
    elements.adminFreshnessNotice.textContent = '';
    elements.adminFreshnessNotice.className = 'data-freshness-banner';
    return;
  }

  elements.adminFreshnessNotice.hidden = false;
  elements.adminFreshnessNotice.className = `data-freshness-banner ${tone || ''}`.trim();
  elements.adminFreshnessNotice.innerHTML = message;
}

function isLiveBackendSource() {
  return Boolean(state.sourceUrl && state.sourceUrl.includes('api/predictions'));
}

function getRequestedDistrictName() {
  if (!state.payload?.districts?.length) {
    return null;
  }

  const requestedDistrict = new URLSearchParams(window.location.search).get('district');
  if (!requestedDistrict) {
    return null;
  }

  const requestedToken = normalizeDistrictToken(requestedDistrict);
  const matchedDistrict = state.payload.districts.find(district =>
    normalizeDistrictToken(district.name) === requestedToken ||
    normalizeDistrictToken(district.label) === requestedToken
  );

  return matchedDistrict ? matchedDistrict.name : null;
}

function buildPublicMapUrl(districtName) {
  if (!districtName) {
    return 'index.html';
  }

  const url = new URL('index.html', window.location.href);
  url.searchParams.set('district', districtName);
  return `${url.pathname}${url.search}`;
}

function buildLinkedUrl(baseHref, districtName) {
  const url = new URL(baseHref, window.location.href);

  if (districtName) {
    url.searchParams.set('district', districtName);
  } else {
    url.searchParams.delete('district');
  }

  return `${url.pathname}${url.search}${url.hash}`;
}

function updatePublicMapLinks() {
  const targetUrl = buildPublicMapUrl(state.selectedDistrictName);

  if (elements.adminMapNavLink) {
    elements.adminMapNavLink.href = targetUrl;
  }

  if (elements.openPublicMapLink) {
    elements.openPublicMapLink.href = targetUrl;
  }

  document.querySelectorAll('[data-preserve-district]').forEach(link => {
    const baseHref = link.dataset.baseHref || link.getAttribute('href') || '';

    if (!baseHref) {
      return;
    }

    link.dataset.baseHref = baseHref;
    link.href = buildLinkedUrl(baseHref, state.selectedDistrictName);
  });

  if (window.history?.replaceState) {
    const nextUrl = new URL(window.location.href);

    if (state.selectedDistrictName) {
      nextUrl.searchParams.set('district', state.selectedDistrictName);
    } else {
      nextUrl.searchParams.delete('district');
    }

    const nextPath = `${nextUrl.pathname}${nextUrl.search}${nextUrl.hash}`;
    const currentPath = `${window.location.pathname}${window.location.search}${window.location.hash}`;

    if (nextPath !== currentPath) {
      window.history.replaceState({}, '', nextPath);
    }
  }
}

function getPredictionEntries() {
  return state.payload?.districts || [];
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
  const observationValue = state.payload?.meta?.latestObservationDate || getLatestValueByDate(
    predictions.map(prediction => prediction.latestObservationDate)
  );
  const forecastValue = state.payload?.meta?.forecastTargetDate || getLatestValueByDate(
    predictions.map(extractForecastDateValue)
  );
  const generatedValue = state.payload?.meta?.updatedAt || null;
  const fallbackAgeDays = Number(state.payload?.meta?.observationAgeDays);
  const ageDays = differenceFromTodayInDays(observationValue);
  const resolvedAgeDays = ageDays ?? (Number.isNaN(fallbackAgeDays) ? null : fallbackAgeDays);
  const configuredThreshold = Number(state.payload?.meta?.staleDataThresholdDays);
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
      `Data observasi tertinggal ${resolvedAgeDays} hari dari tanggal akses, jadi admin perlu cek konteks sebelum membagikan hasil.`
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

  if (!freshnessInfo.available) {
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

function renderEnvironmentBanner() {
  if (!elements.environmentBanner) {
    return;
  }

  const meta = state.payload?.meta || {};
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
  elements.environmentBanner.textContent = `${appName} - ${label}: versi uji coba admin, bukan panel utama.`;
}

function renderAdminModelNotice() {
  if (!elements.adminModelNoticeLead || !elements.adminModelNoticeAccuracy) {
    return;
  }

  const meta = state.payload?.meta || {};
  elements.adminModelNoticeLead.textContent =
    'Panel ini membantu review internal hasil model dan tidak menggantikan keputusan operasional final.';

  const noteParts = [];
  if (meta.modelAccuracyNote) {
    noteParts.push(meta.modelAccuracyNote);
  }
  if (meta.conversionNote) {
    noteParts.push('Skor risiko diturunkan dari prediksi kelas curah hujan dan penyesuaian drainase terbatas.');
  }
  if (!isLiveBackendSource()) {
    noteParts.push('Saat ini admin sedang membaca file JSON cadangan, jadi hasil yang tampil bukan hitungan backend live pada saat ini.');
  }

  elements.adminModelNoticeAccuracy.textContent =
    noteParts.join(' ') || 'Catatan model belum tersedia dari payload aktif.';
}

function sortDistrictsByRisk(districts) {
  return districts
    .slice()
    .sort((left, right) => {
      const riskDifference = Number(right.riskScore || 0) - Number(left.riskScore || 0);
      if (riskDifference !== 0) {
        return riskDifference;
      }

      return String(left.label || '').localeCompare(String(right.label || ''), 'id');
    });
}

function getSelectedDistrict() {
  if (!state.payload) {
    return null;
  }

  return state.payload.districts.find(district => district.name === state.selectedDistrictName) || null;
}

function updateHeaderStatus() {
  if (!state.payload || (!elements.adminDataStatus && !elements.adminUpdatedAt)) {
    return;
  }

  const freshnessInfo = buildFreshnessInfo();
  const envLabel = state.payload.meta?.deploymentEnvironmentLabel;
  const baseStatus = isLiveBackendSource() ? 'Backend Live' : 'JSON Cadangan';
  setTextContent(elements.adminDataStatus, envLabel ? `${baseStatus} - ${envLabel}` : baseStatus);

  const noteParts = [];
  if (freshnessInfo.observationValue) {
    noteParts.push(`Observasi: ${formatDateOnly(freshnessInfo.observationValue)}`);
  }
  if (freshnessInfo.generatedValue) {
    noteParts.push(`Payload: ${formatUpdatedAt(freshnessInfo.generatedValue)}`);
  }
  if (freshnessInfo.ageDays !== null) {
    noteParts.push(`Usia: ${freshnessInfo.ageDays} hari`);
  }

  setTextContent(elements.adminUpdatedAt, noteParts.join(' | ') || 'Tanggal freshness belum tersedia.');
}

function populateBackendInfo() {
  if (
    !elements.backendSourceLabel &&
    !elements.backendLatestObservation &&
    !elements.backendForecastTarget &&
    !elements.backendPayloadGenerated &&
    !elements.backendModel &&
    !elements.backendRainfallSource &&
    !elements.backendDrainageSource &&
    !elements.backendForecastHorizon &&
    !elements.backendAccuracyNote
  ) {
    return;
  }

  const meta = state.payload?.meta || {};
  const freshnessInfo = buildFreshnessInfo();

  setTextContent(elements.backendSourceLabel, isLiveBackendSource()
    ? 'API backend live aktif'
    : 'File JSON cadangan aktif');
  setTextContent(elements.backendLatestObservation, freshnessInfo.observationValue
    ? formatDateOnly(freshnessInfo.observationValue)
    : '-');
  setTextContent(elements.backendForecastTarget, freshnessInfo.forecastValue
    ? formatDateOnly(freshnessInfo.forecastValue)
    : '-');
  setTextContent(elements.backendPayloadGenerated, freshnessInfo.generatedValue
    ? formatUpdatedAt(freshnessInfo.generatedValue)
    : '-');
  setTextContent(elements.backendModel, meta.model || '-');
  setTextContent(elements.backendRainfallSource, meta.rainfallSource || '-');
  setTextContent(elements.backendDrainageSource, meta.drainageSource || '-');

  if (meta.forecastHorizonDays) {
    setTextContent(elements.backendForecastHorizon, `${meta.forecastHorizonDays} hari`);
  } else {
    setTextContent(elements.backendForecastHorizon, '-');
  }

  setTextContent(elements.backendAccuracyNote, meta.modelAccuracyNote || meta.conversionNote || '-');
}

function populateDistrictOptions() {
  if (!state.payload) {
    return;
  }

  ensureSelectedDistrict();

  if (!elements.district) {
    return;
  }

  const options = state.payload.districts
    .slice()
    .sort((left, right) => left.label.localeCompare(right.label, 'id'))
    .map(district => `<option value="${escapeHtml(district.name)}">${escapeHtml(district.label)}</option>`)
    .join('');

  elements.district.innerHTML = options;
  elements.district.value = state.selectedDistrictName || '';
}

function clearPreview() {
  setInputValue(elements.rainfall, '');
  setInputValue(elements.probability, '');
  setInputValue(elements.drainage, '');
  setInputValue(elements.drainageConfidence, '');
  setInputValue(elements.drainageAdjustment, '');
  setInputValue(elements.riskCategory, '');
  setInputValue(elements.riskScore, '');
  setInputValue(elements.webgisLevelLabel, '');
  setInputValue(elements.forecastLabel, '');
  setInputValue(elements.latestObservationDate, '');
  setInputValue(elements.latestObservedRainfallMm, '');
  setInputValue(elements.recentThreeDayAverageMm, '');
  setInputValue(elements.summary, '');
  setInputValue(elements.drainageNote, '');
  setInputValue(elements.recommendation, '');
}

function fillPreview(district) {
  if (!district) {
    clearPreview();
    return;
  }

  setInputValue(elements.rainfall, getRainfallDisplayValue(district));
  setInputValue(elements.probability, formatPercent(getProbabilityPercentValue(district)));
  setInputValue(elements.drainage, district.drainageCondition || '-');
  setInputValue(elements.drainageConfidence, formatDrainageConfidence(district));
  setInputValue(elements.drainageAdjustment, formatSignedPercent(district.drainageAdjustmentPercent));
  setInputValue(elements.riskCategory, district.riskCategory || '-');
  setInputValue(elements.riskScore, formatScore(district.riskScore));
  setInputValue(elements.webgisLevelLabel, getSemanticRiskLevelLabel(district));
  setInputValue(elements.forecastLabel, district.forecastLabel || '-');
  setInputValue(elements.latestObservationDate, formatDateOnly(district.latestObservationDate));
  setInputValue(elements.latestObservedRainfallMm, formatMillimeter(district.latestObservedRainfallMm));
  setInputValue(elements.recentThreeDayAverageMm, formatMillimeter(district.recentThreeDayAverageMm));
  setInputValue(elements.summary, district.summary || '-');
  setInputValue(elements.drainageNote, district.drainageNote || district.drainageDataSourceName || '-');
  setInputValue(elements.recommendation, district.recommendation || '-');
}

function renderSummaryCards() {
  if (
    !elements.summaryDistrictCount &&
    !elements.summaryTopRiskDistrict &&
    !elements.summaryTopRiskMeta &&
    !elements.summaryAlertCount &&
    !elements.summaryAverageProbability
  ) {
    return;
  }

  const districts = state.payload?.districts || [];
  const topDistrict = sortDistrictsByRisk(districts)[0] || null;
  const alertCount = districts.filter(district => Number(district.webgisLevel || 0) >= 2).length;
  const averageProbability = districts.length
    ? districts.reduce((total, district) => total + (getProbabilityPercentValue(district) || 0), 0) / districts.length
    : NaN;

  setTextContent(elements.summaryDistrictCount, String(districts.length || 0));
  setTextContent(elements.summaryTopRiskDistrict, topDistrict ? topDistrict.label : '-');
  setTextContent(elements.summaryTopRiskMeta, topDistrict
    ? `${formatPercent(getProbabilityPercentValue(topDistrict))} | ${getSemanticRiskLevelLabel(topDistrict)}`
    : 'Belum ada data risiko.');
  setTextContent(elements.summaryAlertCount, String(alertCount));
  setTextContent(elements.summaryAverageProbability, formatPercent(averageProbability));
}

function renderPriorityList() {
  if (!elements.priorityDistrictList) {
    return;
  }

  const priorityDistricts = sortDistrictsByRisk(state.payload?.districts || []).slice(0, 3);

  if (priorityDistricts.length === 0) {
    elements.priorityDistrictList.innerHTML = '<div class="empty-state">Belum ada data prioritas.</div>';
    return;
  }

  elements.priorityDistrictList.innerHTML = priorityDistricts
    .map(district => {
      const tone = getRiskTone(district.riskCategory, district.webgisLevel);
      return `
        <article class="priority-card">
          <div class="priority-card-head">
            <div>
              <strong>${escapeHtml(district.label)}</strong>
              <p>${escapeHtml(district.forecastLabel || 'Prediksi aktif')}</p>
            </div>
            <span class="risk-badge ${tone}">${escapeHtml(getSemanticRiskLevelLabel(district))}</span>
          </div>
          <div class="priority-card-body">
            <span>${escapeHtml(formatPercent(getProbabilityPercentValue(district)))} confidence kelas</span>
            <span>${escapeHtml(formatDrainageConfidence(district))} confidence</span>
          </div>
          <button class="table-action priority-action" type="button" data-district="${escapeHtml(district.name)}">
            Lihat Detail
          </button>
        </article>
      `;
    })
    .join('');
}

function renderTable() {
  if (!elements.tableBody) {
    return;
  }

  elements.tableBody.innerHTML = sortDistrictsByRisk(state.payload?.districts || [])
    .map(district => {
      const tone = getRiskTone(district.riskCategory, district.webgisLevel);
      return `
        <tr>
          <td><strong>${escapeHtml(district.label)}</strong></td>
          <td>${escapeHtml(getRainfallDisplayValue(district))}</td>
          <td>${escapeHtml(district.drainageCondition || '-')}<br><small>${escapeHtml(district.drainageConfidence || 'Tidak tersedia')}</small></td>
          <td><span class="risk-badge ${tone}">${escapeHtml(district.riskCategory || '-')}</span></td>
          <td>${escapeHtml(formatScore(district.riskScore).replace(' / 100', ''))}</td>
          <td>${escapeHtml(formatPercent(getProbabilityPercentValue(district)))}</td>
          <td>
            <button class="table-action" type="button" data-district="${escapeHtml(district.name)}">Lihat</button>
          </td>
        </tr>
      `;
    })
    .join('');
}

function selectDistrict(districtName) {
  state.selectedDistrictName = districtName;
  if (elements.district) {
    elements.district.value = districtName;
  }
  fillPreview(getSelectedDistrict());
  updatePublicMapLinks();
  setMessage('', '');
}

function exportJson() {
  if (!state.payload) {
    setMessage('Belum ada data yang bisa diexport.', 'error');
    return;
  }

  const blob = new Blob([JSON.stringify(state.payload, null, 2)], {
    type: 'application/json'
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');

  link.href = url;
  link.download = 'east-jakarta-predictions.json';
  link.click();
  URL.revokeObjectURL(url);
  setMessage('JSON berhasil diexport.', 'success');
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
      const payload = await fetchJson(url);
      return { payload, sourceUrl: url };
    } catch (error) {
      lastError = error;
      console.warn(`Sumber data ${url} gagal dimuat.`, error);
    }
  }

  throw lastError || new Error('Tidak ada sumber data prediksi yang berhasil dimuat.');
}

function resetDashboardToErrorState() {
  state.payload = null;
  state.sourceUrl = null;
  setTextContent(elements.adminDataStatus, 'Gagal Memuat');
  setTextContent(elements.adminUpdatedAt, 'Pastikan backend lokal sedang berjalan.');
  setTextContent(elements.summaryDistrictCount, '-');
  setTextContent(elements.summaryTopRiskDistrict, '-');
  setTextContent(elements.summaryTopRiskMeta, 'Data ringkasan belum tersedia.');
  setTextContent(elements.summaryAlertCount, '-');
  setTextContent(elements.summaryAverageProbability, '-');
  setTextContent(elements.backendSourceLabel, '-');
  setTextContent(elements.backendLatestObservation, '-');
  setTextContent(elements.backendForecastTarget, '-');
  setTextContent(elements.backendPayloadGenerated, '-');
  setTextContent(elements.backendModel, '-');
  setTextContent(elements.backendRainfallSource, '-');
  setTextContent(elements.backendDrainageSource, '-');
  setTextContent(elements.backendForecastHorizon, '-');
  setTextContent(elements.backendAccuracyNote, '-');
  if (elements.adminModelNoticeLead) {
    elements.adminModelNoticeLead.textContent =
      'Panel ini membantu review internal hasil model dan tidak menggantikan keputusan operasional final.';
  }
  if (elements.adminModelNoticeAccuracy) {
    elements.adminModelNoticeAccuracy.textContent =
      'Catatan model belum tersedia karena sumber prediksi aktif gagal dimuat.';
  }
  setInnerHtml(
    elements.priorityDistrictList,
    '<div class="empty-state">Prioritas tidak bisa dimuat karena data backend gagal dibaca.</div>'
  );
  setInnerHtml(elements.tableBody, '');
  clearPreview();
  updatePublicMapLinks();
  setFreshnessNotice(
    '<strong>Freshness data tidak tersedia.</strong> Gagal membaca sumber prediksi aktif maupun fallback JSON.',
    'error'
  );
}

function loadPayload(message) {
  fetchFirstAvailableJson(PREDICTION_ENDPOINTS)
    .then(({ payload, sourceUrl }) => {
      state.payload = payload;
      state.sourceUrl = sourceUrl;
      state.selectedDistrictName = getRequestedDistrictName() || state.selectedDistrictName;
      ensureSelectedDistrict();
      renderEnvironmentBanner();
      populateDistrictOptions();
      fillPreview(getSelectedDistrict());
      renderSummaryCards();
      populateBackendInfo();
      renderAdminModelNotice();
      renderPriorityList();
      renderTable();
      updateHeaderStatus();
      renderFreshnessNotice();
      updatePublicMapLinks();
      const successMessage = isLiveBackendSource()
        ? 'Preview model berhasil dimuat dari backend live.'
        : 'Preview model dimuat dari file JSON cadangan.';
      setMessage(message || successMessage, 'success');
    })
    .catch(error => {
      console.error('Gagal memuat data admin:', error);
      resetDashboardToErrorState();
      setMessage('Data backend gagal dimuat.', 'error');
    });
}

function bindEvents() {
  if (elements.district) {
    elements.district.addEventListener('change', event => {
      selectDistrict(event.target.value);
    });
  }

  if (elements.tableBody) {
    elements.tableBody.addEventListener('click', event => {
      const button = event.target.closest('[data-district]');

      if (!button) {
        return;
      }

      selectDistrict(button.dataset.district);
      scrollPreviewIntoView();
    });
  }

  if (elements.priorityDistrictList) {
    elements.priorityDistrictList.addEventListener('click', event => {
      const button = event.target.closest('[data-district]');

      if (!button) {
        return;
      }

      selectDistrict(button.dataset.district);
      scrollPreviewIntoView();
    });
  }

  if (elements.exportJsonButton) {
    elements.exportJsonButton.addEventListener('click', exportJson);
  }
  document.querySelectorAll('[data-admin-action="export-json"]').forEach(button => {
    button.addEventListener('click', exportJson);
  });
  if (elements.refreshDataButton) {
    elements.refreshDataButton.addEventListener('click', () => {
      loadPayload('Preview model berhasil diperbarui dari backend.');
    });
  }
}

bindEvents();
loadPayload('Preview model berhasil dimuat.');
