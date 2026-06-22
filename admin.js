const PREDICTION_ENDPOINTS = [
  'api/predictions',
  'data/east-jakarta-predictions.json'
];

const elements = {
  adminDataStatus: document.getElementById('adminDataStatus'),
  adminUpdatedAt: document.getElementById('adminUpdatedAt'),
  district: document.getElementById('adminDistrict'),
  rainfall: document.getElementById('predictedRainfallMm'),
  probability: document.getElementById('probabilityWaspadaPercent'),
  drainage: document.getElementById('drainageCondition'),
  riskCategory: document.getElementById('riskCategory'),
  riskScore: document.getElementById('riskScore'),
  webgisLevelLabel: document.getElementById('webgisLevelLabel'),
  forecastLabel: document.getElementById('forecastLabel'),
  latestObservationDate: document.getElementById('latestObservationDate'),
  latestObservedRainfallMm: document.getElementById('latestObservedRainfallMm'),
  recentThreeDayAverageMm: document.getElementById('recentThreeDayAverageMm'),
  summary: document.getElementById('summary'),
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
  backendModel: document.getElementById('backendModel'),
  backendRainfallSource: document.getElementById('backendRainfallSource'),
  backendDrainageSource: document.getElementById('backendDrainageSource'),
  backendForecastHorizon: document.getElementById('backendForecastHorizon'),
  backendAccuracyNote: document.getElementById('backendAccuracyNote'),
  priorityDistrictList: document.getElementById('priorityDistrictList')
};

const state = {
  payload: null,
  selectedDistrictName: null,
  sourceUrl: null
};

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function formatUpdatedAt(value) {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return 'Belum tersedia';
  }

  return new Intl.DateTimeFormat('id-ID', {
    dateStyle: 'medium',
    timeStyle: 'short'
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

function getProbabilityPercentValue(district) {
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

function getRiskTone(category, level) {
  if (Number(level) >= 4) {
    return 'high';
  }

  switch ((category || '').toLowerCase()) {
    case 'rendah':
      return 'low';
    case 'sedang':
      return 'medium';
    case 'tinggi':
      return 'high';
    default:
      return 'low';
  }
}

function setMessage(message, tone) {
  elements.saveMessage.textContent = message;
  elements.saveMessage.className = `save-message ${tone || ''}`.trim();
}

function isLiveBackendSource() {
  return Boolean(state.sourceUrl && state.sourceUrl.startsWith('api/'));
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
  if (!state.payload) {
    return;
  }

  elements.adminDataStatus.textContent = isLiveBackendSource()
    ? 'Backend Live'
    : 'Fallback JSON';
  elements.adminUpdatedAt.textContent =
    `Terakhir diperbarui: ${formatUpdatedAt(state.payload.meta?.updatedAt)}`;
}

function populateBackendInfo() {
  const meta = state.payload?.meta || {};

  elements.backendSourceLabel.textContent = isLiveBackendSource()
    ? 'API backend aktif'
    : 'File JSON statis';
  elements.backendModel.textContent = meta.model || '-';
  elements.backendRainfallSource.textContent = meta.rainfallSource || '-';
  elements.backendDrainageSource.textContent = meta.drainageSource || '-';

  if (meta.forecastHorizonDays) {
    elements.backendForecastHorizon.textContent = `${meta.forecastHorizonDays} hari`;
  } else {
    elements.backendForecastHorizon.textContent = '-';
  }

  elements.backendAccuracyNote.textContent = meta.modelAccuracyNote || meta.conversionNote || '-';
}

function populateDistrictOptions() {
  const options = state.payload.districts
    .slice()
    .sort((left, right) => left.label.localeCompare(right.label, 'id'))
    .map(district => `<option value="${escapeHtml(district.name)}">${escapeHtml(district.label)}</option>`)
    .join('');

  elements.district.innerHTML = options;

  const selectedExists = state.payload.districts.some(
    district => district.name === state.selectedDistrictName
  );

  state.selectedDistrictName = selectedExists
    ? state.selectedDistrictName
    : state.payload.districts[0]?.name || null;

  elements.district.value = state.selectedDistrictName || '';
}

function clearPreview() {
  elements.rainfall.value = '';
  elements.probability.value = '';
  elements.drainage.value = '';
  elements.riskCategory.value = '';
  elements.riskScore.value = '';
  elements.webgisLevelLabel.value = '';
  elements.forecastLabel.value = '';
  elements.latestObservationDate.value = '';
  elements.latestObservedRainfallMm.value = '';
  elements.recentThreeDayAverageMm.value = '';
  elements.summary.value = '';
  elements.recommendation.value = '';
}

function fillPreview(district) {
  if (!district) {
    clearPreview();
    return;
  }

  elements.rainfall.value = formatMillimeter(district.predictedRainfallMm);
  elements.probability.value = formatPercent(getProbabilityPercentValue(district));
  elements.drainage.value = district.drainageCondition || '-';
  elements.riskCategory.value = district.riskCategory || '-';
  elements.riskScore.value = formatScore(district.riskScore);
  elements.webgisLevelLabel.value = district.webgisLevelLabel || district.riskCategory || '-';
  elements.forecastLabel.value = district.forecastLabel || '-';
  elements.latestObservationDate.value = district.latestObservationDate || '-';
  elements.latestObservedRainfallMm.value = formatMillimeter(district.latestObservedRainfallMm);
  elements.recentThreeDayAverageMm.value = formatMillimeter(district.recentThreeDayAverageMm);
  elements.summary.value = district.summary || '-';
  elements.recommendation.value = district.recommendation || '-';
}

function renderSummaryCards() {
  const districts = state.payload?.districts || [];
  const topDistrict = sortDistrictsByRisk(districts)[0] || null;
  const alertCount = districts.filter(district => Number(district.webgisLevel || 0) >= 2).length;
  const averageProbability = districts.length
    ? districts.reduce((total, district) => total + (getProbabilityPercentValue(district) || 0), 0) / districts.length
    : NaN;

  elements.summaryDistrictCount.textContent = String(districts.length || 0);
  elements.summaryTopRiskDistrict.textContent = topDistrict ? topDistrict.label : '-';
  elements.summaryTopRiskMeta.textContent = topDistrict
    ? `${formatPercent(getProbabilityPercentValue(topDistrict))} • ${topDistrict.webgisLevelLabel || topDistrict.riskCategory}`
    : 'Belum ada data risiko.';
  elements.summaryAlertCount.textContent = String(alertCount);
  elements.summaryAverageProbability.textContent = formatPercent(averageProbability);
}

function renderPriorityList() {
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
            <span class="risk-badge ${tone}">${escapeHtml(district.webgisLevelLabel || district.riskCategory || '-')}</span>
          </div>
          <div class="priority-card-body">
            <span>${escapeHtml(formatPercent(getProbabilityPercentValue(district)))} waspada</span>
            <span>${escapeHtml(formatMillimeter(district.predictedRainfallMm))} prediksi</span>
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
  elements.tableBody.innerHTML = sortDistrictsByRisk(state.payload?.districts || [])
    .map(district => {
      const tone = getRiskTone(district.riskCategory, district.webgisLevel);
      return `
        <tr>
          <td><strong>${escapeHtml(district.label)}</strong></td>
          <td>${escapeHtml(formatMillimeter(district.predictedRainfallMm))}</td>
          <td>${escapeHtml(district.drainageCondition || '-')}</td>
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
  elements.district.value = districtName;
  fillPreview(getSelectedDistrict());
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
  elements.adminDataStatus.textContent = 'Gagal Memuat';
  elements.adminUpdatedAt.textContent = 'Pastikan backend lokal sedang berjalan.';
  elements.summaryDistrictCount.textContent = '-';
  elements.summaryTopRiskDistrict.textContent = '-';
  elements.summaryTopRiskMeta.textContent = 'Data ringkasan belum tersedia.';
  elements.summaryAlertCount.textContent = '-';
  elements.summaryAverageProbability.textContent = '-';
  elements.backendSourceLabel.textContent = '-';
  elements.backendModel.textContent = '-';
  elements.backendRainfallSource.textContent = '-';
  elements.backendDrainageSource.textContent = '-';
  elements.backendForecastHorizon.textContent = '-';
  elements.backendAccuracyNote.textContent = '-';
  elements.priorityDistrictList.innerHTML =
    '<div class="empty-state">Prioritas tidak bisa dimuat karena data backend gagal dibaca.</div>';
  elements.tableBody.innerHTML = '';
  clearPreview();
}

function loadPayload(message) {
  fetchFirstAvailableJson(PREDICTION_ENDPOINTS)
    .then(({ payload, sourceUrl }) => {
      state.payload = payload;
      state.sourceUrl = sourceUrl;
      populateDistrictOptions();
      fillPreview(getSelectedDistrict());
      renderSummaryCards();
      populateBackendInfo();
      renderPriorityList();
      renderTable();
      updateHeaderStatus();
      setMessage(message || 'Preview model berhasil dimuat.', 'success');
    })
    .catch(error => {
      console.error('Gagal memuat data admin:', error);
      resetDashboardToErrorState();
      setMessage('Data backend gagal dimuat.', 'error');
    });
}

function bindEvents() {
  elements.district.addEventListener('change', event => {
    selectDistrict(event.target.value);
  });

  elements.tableBody.addEventListener('click', event => {
    const button = event.target.closest('[data-district]');

    if (!button) {
      return;
    }

    selectDistrict(button.dataset.district);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  elements.priorityDistrictList.addEventListener('click', event => {
    const button = event.target.closest('[data-district]');

    if (!button) {
      return;
    }

    selectDistrict(button.dataset.district);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  elements.exportJsonButton.addEventListener('click', exportJson);
  elements.refreshDataButton.addEventListener('click', () => {
    loadPayload('Preview model berhasil diperbarui dari backend.');
  });
}

bindEvents();
loadPayload('Preview model berhasil dimuat.');
