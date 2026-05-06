const STORAGE_KEY = 'floodgis_predictions';

const elements = {
  adminDataStatus: document.getElementById('adminDataStatus'),
  adminUpdatedAt: document.getElementById('adminUpdatedAt'),
  form: document.getElementById('predictionForm'),
  district: document.getElementById('adminDistrict'),
  rainfall: document.getElementById('predictedRainfallMm'),
  drainage: document.getElementById('drainageCondition'),
  riskCategory: document.getElementById('riskCategory'),
  riskScore: document.getElementById('riskScore'),
  summary: document.getElementById('summary'),
  recommendation: document.getElementById('recommendation'),
  tableBody: document.getElementById('predictionTableBody'),
  saveMessage: document.getElementById('saveMessage'),
  autoClassifyButton: document.getElementById('autoClassifyButton'),
  resetFormButton: document.getElementById('resetFormButton'),
  exportJsonButton: document.getElementById('exportJsonButton'),
  resetStorageButton: document.getElementById('resetStorageButton')
};

const state = {
  payload: null,
  selectedDistrictName: null
};

function cloneData(data) {
  return JSON.parse(JSON.stringify(data));
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

function setMessage(message, tone) {
  elements.saveMessage.textContent = message;
  elements.saveMessage.className = `save-message ${tone || ''}`.trim();
}

function getStoredPayload() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);

    if (!stored) {
      return null;
    }

    const parsed = JSON.parse(stored);

    if (!parsed || !Array.isArray(parsed.districts)) {
      return null;
    }

    return parsed;
  } catch (error) {
    console.warn('Data admin tidak valid:', error);
    return null;
  }
}

function persistPayload() {
  state.payload.meta.updatedAt = new Date().toISOString();
  state.payload.meta.source = 'admin-local-storage';
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.payload));
  updateHeaderStatus();
}

function getRiskCategoryFromScore(score) {
  if (score >= 70) {
    return 'Tinggi';
  }

  if (score >= 40) {
    return 'Sedang';
  }

  return 'Rendah';
}

function getRiskTone(category) {
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

function getSelectedDistrict() {
  return state.payload.districts.find(district => district.name === state.selectedDistrictName);
}

function updateHeaderStatus() {
  const isAdminData = state.payload.meta.source === 'admin-local-storage';
  elements.adminDataStatus.textContent = isAdminData ? 'Data Admin Aktif' : 'Data Bawaan';
  elements.adminUpdatedAt.textContent = `Terakhir diperbarui: ${formatUpdatedAt(state.payload.meta.updatedAt)}`;
}

function populateDistrictOptions() {
  elements.district.innerHTML = state.payload.districts
    .map(district => `<option value="${district.name}">${district.label}</option>`)
    .join('');

  state.selectedDistrictName = state.payload.districts[0]?.name || null;
  elements.district.value = state.selectedDistrictName;
}

function fillForm(district) {
  if (!district) {
    return;
  }

  elements.rainfall.value = district.predictedRainfallMm;
  elements.drainage.value = district.drainageCondition;
  elements.riskCategory.value = district.riskCategory;
  elements.riskScore.value = Math.round(district.riskScore * 100);
  elements.summary.value = district.summary;
  elements.recommendation.value = district.recommendation;
}

function renderTable() {
  elements.tableBody.innerHTML = state.payload.districts
    .map(district => `
      <tr>
        <td><strong>${district.label}</strong></td>
        <td>${district.predictedRainfallMm} mm</td>
        <td>${district.drainageCondition}</td>
        <td><span class="risk-badge ${getRiskTone(district.riskCategory)}">${district.riskCategory}</span></td>
        <td>${Math.round(district.riskScore * 100)}</td>
        <td>
          <button class="table-action" type="button" data-district="${district.name}">Edit</button>
        </td>
      </tr>
    `)
    .join('');
}

function updateSelectedDistrictFromForm() {
  const district = getSelectedDistrict();

  if (!district) {
    return;
  }

  district.predictedRainfallMm = Number(elements.rainfall.value);
  district.drainageCondition = elements.drainage.value;
  district.riskCategory = elements.riskCategory.value;
  district.riskScore = Number(elements.riskScore.value) / 100;
  district.summary = elements.summary.value.trim();
  district.recommendation = elements.recommendation.value.trim();
}

function selectDistrict(districtName) {
  state.selectedDistrictName = districtName;
  elements.district.value = districtName;
  fillForm(getSelectedDistrict());
  setMessage('', '');
}

function exportJson() {
  const blob = new Blob([JSON.stringify(state.payload, null, 2)], {
    type: 'application/json'
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');

  link.href = url;
  link.download = 'east-jakarta-predictions.json';
  link.click();
  URL.revokeObjectURL(url);
}

function bindEvents() {
  elements.district.addEventListener('change', event => {
    selectDistrict(event.target.value);
  });

  elements.autoClassifyButton.addEventListener('click', () => {
    const score = Number(elements.riskScore.value);

    if (Number.isNaN(score)) {
      setMessage('Isi skor risiko terlebih dahulu.', 'error');
      return;
    }

    elements.riskCategory.value = getRiskCategoryFromScore(score);
    setMessage('Kategori risiko berhasil dihitung dari skor.', 'success');
  });

  elements.resetFormButton.addEventListener('click', () => {
    fillForm(getSelectedDistrict());
    setMessage('Form dikembalikan ke data terakhir.', 'success');
  });

  elements.form.addEventListener('submit', event => {
    event.preventDefault();

    updateSelectedDistrictFromForm();
    persistPayload();
    renderTable();
    setMessage('Data berhasil disimpan. Buka halaman peta untuk melihat perubahan.', 'success');
  });

  elements.tableBody.addEventListener('click', event => {
    const button = event.target.closest('[data-district]');

    if (!button) {
      return;
    }

    selectDistrict(button.dataset.district);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  elements.exportJsonButton.addEventListener('click', exportJson);

  elements.resetStorageButton.addEventListener('click', () => {
    const approved = confirm('Hapus data admin dari browser dan kembali ke data bawaan?');

    if (!approved) {
      return;
    }

    localStorage.removeItem(STORAGE_KEY);
    window.location.reload();
  });
}

function fetchJson(url) {
  return fetch(url).then(response => {
    if (!response.ok) {
      throw new Error(`Gagal memuat ${url} (${response.status})`);
    }

    return response.json();
  });
}

function initializeAdmin() {
  fetchJson('data/east-jakarta-predictions.json')
    .then(defaultPayload => {
      state.payload = cloneData(getStoredPayload() || defaultPayload);
      populateDistrictOptions();
      fillForm(getSelectedDistrict());
      renderTable();
      updateHeaderStatus();
      bindEvents();
      setMessage('Data siap diedit.', 'success');
    })
    .catch(error => {
      console.error('Gagal memuat data admin:', error);
      elements.adminDataStatus.textContent = 'Gagal Memuat';
      elements.adminUpdatedAt.textContent = 'Pastikan file JSON tersedia dan jalankan melalui local server.';
      setMessage('Data admin gagal dimuat.', 'error');
    });
}

initializeAdmin();
