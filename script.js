const map = L.map('map').setView([-6.225, 106.925], 11);

const baseMap = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

L.control.scale({ imperial: false }).addTo(map);

const elements = {
  districtSelect: document.getElementById('districtSelect'),
  resetViewButton: document.getElementById('resetViewButton'),
  statDistrictCount: document.getElementById('statDistrictCount'),
  statHighRiskCount: document.getElementById('statHighRiskCount'),
  statAverageRainfall: document.getElementById('statAverageRainfall'),
  statUpdatedAt: document.getElementById('statUpdatedAt'),
  statRefreshInterval: document.getElementById('statRefreshInterval'),
  mapSubtitle: document.getElementById('mapSubtitle'),
  dataStatus: document.getElementById('dataStatus'),
  detailContent: document.getElementById('detailContent'),
  hotspotList: document.getElementById('hotspotList'),
  systemSources: document.getElementById('systemSources')
};

const state = {
  meta: null,
  districtLookup: new Map(),
  districts: [],
  geojsonLayer: null,
  heatOverlay: null,
  bounds: null,
  selectedKey: null
};

function normalizeDistrictName(name) {
  return (name || '')
    .toLowerCase()
    .replace(/\s+/g, '')
    .trim();
}

function getGeoDistrictName(feature) {
  return feature.properties.name || '';
}

function formatNumber(value) {
  return new Intl.NumberFormat('id-ID').format(value);
}

function formatUpdatedAt(value) {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return 'Tidak tersedia';
  }

  return new Intl.DateTimeFormat('id-ID', {
    dateStyle: 'medium',
    timeStyle: 'short'
  }).format(date);
}

function getRiskColor(category) {
  switch ((category || '').toLowerCase()) {
    case 'rendah':
      return '#2f9e44';
    case 'sedang':
      return '#f0c419';
    case 'tinggi':
      return '#e03131';
    default:
      return '#94a3b8';
  }
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

function setStatus(text, tone) {
  elements.dataStatus.textContent = text;
  elements.dataStatus.className = 'status-pill';

  if (tone) {
    elements.dataStatus.classList.add(tone);
  }
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
  const fillColor = district ? getRiskColor(district.riskCategory) : '#94a3b8';

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
  return `
    <strong>${prediction.label}</strong><br>
    Risiko: ${prediction.riskCategory}<br>
    Curah hujan: ${prediction.predictedRainfallMm} mm<br>
    Drainase: ${prediction.drainageCondition}
  `;
}

function renderEmptyDetail() {
  elements.detailContent.innerHTML = `
    <div class="empty-state">
      Pilih kecamatan dari dropdown, daftar prioritas, atau klik langsung area pada peta untuk melihat detail wilayah.
    </div>
  `;
}

function renderDetailContent(district) {
  const prediction = district.prediction;
  const riskTone = getRiskTone(prediction.riskCategory);

  elements.detailContent.innerHTML = `
    <div class="detail-header">
      <div>
        <h3 class="detail-title">${prediction.label}</h3>
        <p class="detail-copy">${prediction.summary}</p>
      </div>
      <span class="risk-badge ${riskTone}">${prediction.riskCategory}</span>
    </div>

    <div class="detail-meta">
      <div class="detail-metric">
        <span>Prediksi Curah Hujan</span>
        <strong>${prediction.predictedRainfallMm} mm</strong>
      </div>
      <div class="detail-metric">
        <span>Kondisi Drainase</span>
        <strong>${prediction.drainageCondition}</strong>
      </div>
      <div class="detail-metric">
        <span>Skor Risiko</span>
        <strong>${Math.round(prediction.riskScore * 100)} / 100</strong>
      </div>
      <div class="detail-metric">
        <span>Rekomendasi</span>
        <strong>${prediction.recommendation}</strong>
      </div>
    </div>

    <p class="detail-footnote">
      Output ini merupakan simulasi data hasil prediksi yang telah disiapkan backend
      untuk divisualisasikan oleh frontend sesuai arsitektur proposal.
    </p>
  `;
}

function updateMapSubtitle(selectedDistrict) {
  if (selectedDistrict) {
    elements.mapSubtitle.textContent =
      `${selectedDistrict.prediction.label} sedang ditampilkan sebagai wilayah fokus dengan indikator risiko pendukung.`;
    return;
  }

  elements.mapSubtitle.textContent =
    `Menampilkan ${state.districts.length} kecamatan Jakarta Timur berdasarkan simulasi output backend terbaru.`;
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

  refreshDistrictStyles();
  renderDetailContent(district);
  updateMapSubtitle(district);

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

function renderHotspotList() {
  const topDistricts = state.districts
    .slice()
    .sort((a, b) => b.prediction.riskScore - a.prediction.riskScore)
    .slice(0, 5);

  elements.hotspotList.innerHTML = topDistricts
    .map(district => `
      <li>
        <button class="hotspot-item" type="button" data-district-key="${district.key}">
          <span class="hotspot-copy">
            <strong>${district.prediction.label}</strong>
            <small>${district.prediction.predictedRainfallMm} mm | Drainase ${district.prediction.drainageCondition}</small>
          </span>
          <span class="risk-badge ${getRiskTone(district.prediction.riskCategory)}">${district.prediction.riskCategory}</span>
        </button>
      </li>
    `)
    .join('');
}

function updateSummaryStats() {
  const totalDistricts = state.districts.length;
  const highRiskCount = state.districts.filter(
    district => district.prediction.riskCategory === 'Tinggi'
  ).length;
  const averageRainfall = totalDistricts === 0
    ? 0
    : Math.round(
        state.districts.reduce(
          (sum, district) => sum + district.prediction.predictedRainfallMm,
          0
        ) / totalDistricts
      );

  elements.statDistrictCount.textContent = formatNumber(totalDistricts);
  elements.statHighRiskCount.textContent = formatNumber(highRiskCount);
  elements.statAverageRainfall.textContent = `${formatNumber(averageRainfall)} mm`;
  elements.statUpdatedAt.textContent = formatUpdatedAt(state.meta.updatedAt);
  elements.statRefreshInterval.textContent =
    `Interval pembaruan simulasi: ${state.meta.refreshInterval}`;
  elements.systemSources.textContent =
    `Sumber simulasi: ${state.meta.rainfallSource} untuk curah hujan dan ${state.meta.drainageSource} untuk indikator drainase.`;
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
        fillColor: getRiskColor(district.prediction.riskCategory),
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
      collapsed: false
    }
  ).addTo(map);

  state.bounds = state.geojsonLayer.getBounds();
  map.fitBounds(state.bounds, { padding: [26, 26] });
}

function bindInteractions() {
  elements.districtSelect.addEventListener('change', event => {
    const key = event.target.value;

    if (!key) {
      state.selectedKey = null;
      refreshDistrictStyles();
      updateMapSubtitle();
      renderEmptyDetail();
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

  elements.hotspotList.addEventListener('click', event => {
    const button = event.target.closest('[data-district-key]');

    if (!button) {
      return;
    }

    selectDistrict(button.dataset.districtKey, {
      flyTo: true,
      openPopup: true
    });
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

function bootstrapApp() {
  setStatus('Memuat data', '');

  Promise.all([
    fetchJson('data/jkt.geojson'),
    fetchJson('data/east-jakarta-predictions.json')
  ])
    .then(([geojson, predictionPayload]) => {
      buildPredictionLookup(predictionPayload);

      const filteredGeojson = filterEastJakartaGeojson(geojson);

      if (filteredGeojson.features.length === 0) {
        throw new Error('Tidak ada fitur Jakarta Timur yang cocok dengan data prediksi.');
      }

      initializeMap(filteredGeojson);
      populateDistrictSelect();
      updateSummaryStats();
      renderHotspotList();
      updateMapSubtitle();
      setStatus('Data siap', 'success');

      const primaryDistrict = state.districts
        .slice()
        .sort((a, b) => b.prediction.riskScore - a.prediction.riskScore)[0];

      if (primaryDistrict) {
        selectDistrict(primaryDistrict.key, {
          flyTo: false,
          openPopup: false
        });
      }
    })
    .catch(error => {
      console.error('Gagal memuat Web-GIS:', error);
      elements.mapSubtitle.textContent =
        'Terjadi kendala saat memuat data peta atau data prediksi.';
      elements.detailContent.innerHTML = `
        <div class="empty-state">
          Gagal memuat data. Pastikan file GeoJSON dan JSON prediksi tersedia lalu jalankan ulang melalui local server.
        </div>
      `;
      setStatus('Gagal memuat', 'error');
    });
}

bindInteractions();
bootstrapApp();
