import { useCallback, useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet.heat';

import fallbackPrediction from '../../../data/east-jakarta-predictions.json';
import fallbackGeojsonUrl from '../../../data/jkt.geojson?url';

import { brandAssets } from '../shared/assets';
import {
  buildFreshnessInfo,
  formatDateNumeric,
  formatDateOnly,
  formatNumber,
  formatPercent,
  formatRainMm,
  formatUpdatedAt,
  getDetailRainDisplay,
  getDetailRiskDisplay,
  getPredictedClassConfidencePercentValue,
  getPublicPayloadMode,
  getPublicPayloadStatus,
  getRainfallDisplayValue,
  getRiskColor,
  getRiskTone,
  getSemanticRiskLevelLabel,
  getShowcaseFloodRiskLine,
  getShowcaseForecastDate,
  getShowcaseIconSpec,
  getShowcasePrimaryValue,
  getShowcaseRainSummary,
  normalizeDistrictToken
} from '../shared/formatters';
import {
  buildPublicDistrictTrendHistoryEndpoints,
  buildGeoJsonEndpoints,
  buildPredictionEndpoints,
  buildPublicPredictionSnapshotEndpoints,
  fetchFirstAvailable,
  fetchJson
} from '../shared/api';

const PUBLIC_RISK_FILTERS = [
  { key: 'all', label: 'Semua', match: () => true },
  { key: 'level-1', label: 'Sangat Rendah', match: district => Number(district?.webgisLevel) === 1 },
  { key: 'level-2', label: 'Ringan', match: district => Number(district?.webgisLevel) === 2 },
  { key: 'level-3', label: 'Sedang', match: district => Number(district?.webgisLevel) === 3 },
  { key: 'level-4', label: 'Tinggi', match: district => Number(district?.webgisLevel) >= 4 }
];

const PUBLIC_FAQ_ITEMS = [
  {
    key: 'about',
    question: 'Apa itu FloodGIS Jakarta Timur?',
    answer:
      'FloodGIS Jakarta Timur adalah website visualisasi prediksi curah hujan dan risiko banjir per kecamatan. Sistem ini membantu pengguna melihat peta risiko, ringkasan wilayah, dan detail kondisi tiap kecamatan secara lebih mudah.'
  },
  {
    key: 'sources',
    question: 'Data yang ditampilkan berasal dari mana?',
    answer:
      'Informasi pada website dibentuk dari data observasi cuaca harian, data drainase wilayah, serta hasil pengolahan model prediksi backend. Data tersebut kemudian diproses dan ditampilkan kembali dalam bentuk peta, kartu ringkasan, dan panel detail kecamatan.'
  },
  {
    key: 'risk-levels',
    question: 'Apa arti level risiko Sangat Rendah, Ringan, Sedang, dan Tinggi?',
    answer:
      'Level risiko menunjukkan interpretasi akhir hasil prediksi untuk tiap kecamatan. Semakin tinggi levelnya, semakin besar perhatian yang perlu diberikan terhadap potensi genangan atau gangguan hidrologi di wilayah tersebut.'
  },
  {
    key: 'map-reading',
    question: 'Bagaimana cara membaca peta dan detail kecamatan?',
    answer:
      'Pengguna dapat memilih hari prediksi terlebih dahulu, lalu klik kartu kecamatan atau langsung klik area pada peta. Setelah itu, panel kanan akan menampilkan tingkat risiko, curah hujan, kondisi drainase, tren risiko, dan rekomendasi singkat untuk wilayah yang dipilih.'
  },
  {
    key: 'metrics',
    question: 'Apa arti skor risiko, curah hujan, dan potensi hujan lebat/ekstrem?',
    answer:
      'Skor risiko adalah angka yang merangkum hasil prediksi curah hujan dan penyesuaian kondisi drainase. Curah hujan menunjukkan kelas hujan dominan yang diprediksi, sedangkan potensi hujan lebat atau ekstrem menunjukkan peluang model terhadap kelas hujan dengan intensitas lebih tinggi.'
  },
  {
    key: 'changes',
    question: 'Kenapa hasil prediksi bisa berubah setiap hari?',
    answer:
      'Hasil dapat berubah karena backend memperbarui data observasi terbaru dan menghitung ulang prediksi secara berkala. Dengan demikian, tampilan website akan menyesuaikan kondisi data terbaru yang tersedia pada saat dibuka.'
  }
];

function buildPredictionCandidates() {
  return [
    ...buildPredictionEndpoints().map(url => ({ url })),
    ...buildPublicPredictionSnapshotEndpoints().map(url => ({ url })),
    {
      label: 'bundled-prediction-fallback',
      sourceUrl: 'bundled-prediction-fallback',
      load: async () => fallbackPrediction
    }
  ];
}

function buildGeojsonCandidates() {
  return [
    ...buildGeoJsonEndpoints().map(url => ({ url })),
    {
      label: 'bundled-geojson-fallback',
      sourceUrl: 'bundled-geojson-fallback',
      load: () => fetchJson(fallbackGeojsonUrl)
    }
  ];
}

function getDistrictForecastForDay(district, dayOffset) {
  const normalizedDayOffset = maxSafeDayOffset(dayOffset);
  const forecasts = Array.isArray(district?.forecasts) ? district.forecasts : [];
  return forecasts.find(forecast => Number(forecast?.forecastDayOffset) === normalizedDayOffset) || null;
}

function buildDisplayDistrict(district, dayOffset) {
  const forecastPayload = getDistrictForecastForDay(district, dayOffset);
  if (!forecastPayload) {
    return district;
  }

  return {
    ...district,
    ...forecastPayload,
    name: district.name,
    label: district.label || district.name,
    forecasts: district.forecasts || [],
    availableForecastDays: district.availableForecastDays || []
  };
}

function maxSafeDayOffset(value) {
  const numericValue = Number(value);
  return Number.isNaN(numericValue) || numericValue < 1 ? 1 : Math.trunc(numericValue);
}

function getForecastTabLabel(dayOffset, fallbackLabel) {
  const normalizedDayOffset = maxSafeDayOffset(dayOffset);

  if (normalizedDayOffset === 1) {
    return 'Hari ini';
  }

  if (normalizedDayOffset === 2) {
    return 'Besok';
  }

  if (normalizedDayOffset === 3) {
    return 'Lusa';
  }

  return fallbackLabel || `H+${normalizedDayOffset}`;
}

function buildFreshnessBanner(meta, districts, sourceUrl) {
  const freshnessInfo = buildFreshnessInfo(meta, districts);
  const payloadMode = getPublicPayloadMode(meta);

  if (!freshnessInfo.available) {
    return null;
  }

  if (payloadMode === 'published_snapshot' && freshnessInfo.ageDays !== null && freshnessInfo.ageDays < freshnessInfo.staleThresholdDays) {
    return null;
  }

  const messageParts = [];
  if (freshnessInfo.observationValue) {
    messageParts.push(`Observasi terakhir ${formatDateOnly(freshnessInfo.observationValue)}.`);
  }
  if (freshnessInfo.forecastValue) {
    messageParts.push(`Prediksi ditujukan untuk ${formatDateOnly(freshnessInfo.forecastValue)}.`);
  }
  if (freshnessInfo.generatedValue) {
    messageParts.push(`Payload dibuat ${formatUpdatedAt(freshnessInfo.generatedValue)}.`);
  }

  let tone = 'fresh';
  if (payloadMode === 'live_fallback') {
    tone = 'warning';
    messageParts.unshift('Sumber data saat ini memakai file JSON cadangan karena backend live tidak tersedia.');
  } else if (payloadMode === 'published_snapshot') {
    messageParts.unshift('Homepage saat ini membaca snapshot publik terakhir yang sudah dipublish dari panel admin atau scheduler backend.');
  }

  if (freshnessInfo.ageDays !== null && freshnessInfo.ageDays >= freshnessInfo.staleThresholdDays) {
    tone = 'warning';
    messageParts.push(`Data observasi tertinggal ${freshnessInfo.ageDays} hari dari tanggal akses, jadi hasil perlu dibaca dengan lebih hati-hati.`);
  } else if (freshnessInfo.ageDays !== null) {
    messageParts.push(`Usia data observasi saat dibuka sekitar ${freshnessInfo.ageDays} hari.`);
  }

  return {
    tone,
    title: payloadMode === 'live_fallback'
      ? 'Sedang memakai JSON cadangan.'
      : tone === 'warning'
      ? 'Perlu cek freshness data.'
      : payloadMode === 'published_snapshot'
      ? 'Snapshot publik aktif.'
      : 'Status freshness data.',
    message: messageParts.join(' '),
    info: freshnessInfo
  };
}

function filterEastJakartaGeojson(geojson, districts) {
  const districtTokens = new Set(districts.map(district => normalizeDistrictToken(district.name)));

  return {
    ...geojson,
    features: (geojson.features || []).filter(feature => {
      const name = feature?.properties?.name || '';
      return districtTokens.has(normalizeDistrictToken(name));
    })
  };
}

function csvEscape(value) {
  const text = String(value ?? '');

  if (text.includes('"') || text.includes(',') || text.includes('\n')) {
    return `"${text.replaceAll('"', '""')}"`;
  }

  return text;
}

function downloadDistrictCsv(district) {
  const rows = [
    ['Kecamatan', district.label],
    ['Tanggal Prediksi', district.forecastLabel || '-'],
    ['Tingkat Risiko', getDetailRiskDisplay(district)],
    ['Curah Hujan', getDetailRainDisplay(district)],
    ['Kondisi Drainase', district.drainageCondition || '-'],
    ['Rata-Rata 3 Hari', formatRainMm(district.recentThreeDayAverageMm)],
    ['Potensi Hujan Lebat/Ekstrem', formatPercent(district.probabilityWaspadaPercent)],
    ['Confidence Kelas Dominan', formatPercent(getPredictedClassConfidencePercentValue(district))],
    ['Rekomendasi', district.recommendation || '-'],
    ['Catatan Drainase', district.drainageNote || '-']
  ];

  const csv = rows.map(row => row.map(csvEscape).join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `detail-${district.label.toLowerCase().replace(/\s+/g, '-')}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

function getRiskFilterMeta(filterKey) {
  return PUBLIC_RISK_FILTERS.find(item => item.key === filterKey) || PUBLIC_RISK_FILTERS[0];
}

function getDistrictRecommendationItems(district) {
  const level = Number(district?.webgisLevel || 0);

  if (level >= 4) {
    return [
      'Prioritaskan kewaspadaan pada lokasi yang sering tergenang.',
      'Batasi aktivitas di sekitar saluran atau ruas jalan rawan genangan.',
      'Siapkan rute alternatif dan pantau pembaruan cuaca berikutnya.'
    ];
  }

  if (level === 3) {
    return [
      'Tingkatkan kewaspadaan terutama saat hujan berlangsung lebih lama.',
      'Periksa jalur drainase sekitar rumah atau lingkungan terdekat.',
      'Siapkan langkah antisipasi genangan pada titik yang biasa bermasalah.'
    ];
  }

  if (level === 2) {
    return [
      'Tetap waspada terhadap genangan lokal saat hujan ringan hingga sedang.',
      'Bersihkan sedimen dan sampah di sekitar saluran terdekat.',
      'Pastikan aliran air di lingkungan sekitar tidak tersumbat.'
    ];
  }

  return [
    'Pertahankan pemantauan cuaca rutin pada wilayah ini.',
    'Jaga kebersihan saluran dan area sekitar agar aliran air tetap lancar.',
    'Gunakan informasi ini sebagai visualisasi awal, bukan peringatan operasional final.'
  ];
}

function getDistrictRecommendationTitle(district) {
  const level = Number(district?.webgisLevel || 0);

  if (level >= 4) {
    return 'Risiko tinggi. Waspadai potensi genangan dan prioritaskan langkah antisipasi lapangan.';
  }

  if (level === 3) {
    return 'Risiko sedang. Pemantauan perlu ditingkatkan terutama bila hujan berlangsung berulang.';
  }

  if (level === 2) {
    return 'Risiko ringan. Tetap waspada terhadap genangan lokal saat hujan ringan hingga sedang.';
  }

  return 'Risiko sangat rendah. Kondisi relatif aman, namun pemantauan rutin tetap diperlukan.';
}

function getRiskTrendSummary(trendSeries) {
  if (trendSeries.length < 2) {
    return {
      title: 'Tren belum terbaca',
      note: 'Histori risiko harian belum cukup untuk membaca arah perubahan.'
    };
  }

  const firstValue = Number(trendSeries[0]?.value || 0);
  const lastValue = Number(trendSeries[trendSeries.length - 1]?.value || 0);
  const delta = lastValue - firstValue;

  if (delta >= 3) {
    return {
      title: 'Tren naik',
      note: 'Skor risiko cenderung meningkat pada tiga hari terakhir yang tercatat.'
    };
  }

  if (delta <= -3) {
    return {
      title: 'Tren turun',
      note: 'Skor risiko cenderung menurun pada tiga hari terakhir yang tercatat.'
    };
  }

  return {
    title: 'Relatif stabil',
    note: 'Perubahan skor risiko antar hari terakhir masih dalam rentang kecil.'
  };
}

function RiskTrendCard({ trendSeries, isLoading }) {
  if (isLoading) {
    return (
      <div className="detail-trend-card">
        <div className="detail-trend-head">
          <div>
            <span>Tren Risiko 3 Hari Terakhir</span>
            <strong>Memuat histori</strong>
          </div>
          <small>Backend sedang mengambil riwayat skor risiko kecamatan terpilih.</small>
        </div>
      </div>
    );
  }

  if (trendSeries.length === 0) {
    return null;
  }

  const summary = getRiskTrendSummary(trendSeries);
  const chartWidth = 320;
  const chartHeight = 124;
  const leftPad = 18;
  const rightPad = 18;
  const topPad = 18;
  const bottomPad = 28;
  const usableWidth = chartWidth - leftPad - rightPad;
  const usableHeight = chartHeight - topPad - bottomPad;
  const maxValue = Math.max(...trendSeries.map(item => Number(item.value || 0)), 1);
  const minValue = Math.min(...trendSeries.map(item => Number(item.value || 0)), 0);
  const range = Math.max(maxValue - minValue, 6);

  const points = trendSeries.map((item, index) => {
    const x = leftPad + (trendSeries.length === 1 ? usableWidth / 2 : (usableWidth * index) / (trendSeries.length - 1));
    const y = topPad + usableHeight - (((Number(item.value || 0) - minValue) / range) * usableHeight);
    return {
      ...item,
      x,
      y
    };
  });

  const polylinePoints = points.map(point => `${point.x},${point.y}`).join(' ');

  return (
    <div className="detail-trend-card">
      <div className="detail-trend-head">
        <div>
          <span>Tren Risiko 3 Hari Terakhir</span>
          <strong>{summary.title}</strong>
        </div>
        <small>{summary.note}</small>
      </div>

      <div className="detail-trend-chart" aria-label="Grafik tren risiko 3 hari terakhir">
        <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} role="img">
          <defs>
            <linearGradient id="riskTrendLine" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#0b7285" />
              <stop offset="100%" stopColor="#1d4ed8" />
            </linearGradient>
          </defs>
          <line x1={leftPad} y1={chartHeight - bottomPad} x2={chartWidth - rightPad} y2={chartHeight - bottomPad} className="trend-axis-line" />
          <polyline points={polylinePoints} className="trend-line" />
          {points.map(point => (
            <g key={point.key}>
              <circle cx={point.x} cy={point.y} r="4.5" className="trend-dot" />
              <text x={point.x} y={point.y - 10} textAnchor="middle" className="trend-value-label">
                {`${Math.round(point.value)}%`}
              </text>
              <text x={point.x} y={chartHeight - 8} textAnchor="middle" className="trend-x-label">
                {point.label}
              </text>
            </g>
          ))}
        </svg>
      </div>

      <div className="detail-trend-footer">
        {trendSeries.map(item => (
          <div key={`legend-${item.key}`} className="detail-trend-step">
            <strong>{item.label}</strong>
            <span>{item.dateLabel}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function PublicRiskMap({ geojson, districts, selectedKey, onSelect }) {
  const mapContainerRef = useRef(null);
  const mapRef = useRef(null);
  const layerStateRef = useRef({
    geojsonLayer: null,
    heatOverlay: null,
    layersControl: null,
    legendControl: null,
    layerByKey: new Map()
  });

  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) {
      return undefined;
    }

    const map = L.map(mapContainerRef.current).setView([-6.225, 106.925], 11);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
      subdomains: 'abcd',
      maxZoom: 20
    }).addTo(map);

    L.control.scale({ imperial: false }).addTo(map);
    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!mapRef.current || !geojson?.features?.length || !districts.length) {
      return;
    }

    const map = mapRef.current;
    const state = layerStateRef.current;
    const districtLookup = new Map(districts.map(district => [normalizeDistrictToken(district.name), district]));

    state.geojsonLayer?.remove();
    state.heatOverlay?.remove();
    state.layersControl?.remove();
    state.legendControl?.remove();
    state.layerByKey = new Map();

    const getFeatureStyle = feature => {
      const featureKey = normalizeDistrictToken(feature?.properties?.name || '');
      const district = districtLookup.get(featureKey);

      return {
        fillColor: district ? getRiskColor(district) : '#94a3b8',
        weight: 1.4,
        color: '#ffffff',
        dashArray: '3',
        fillOpacity: 0.76
      };
    };

    const popupContent = district => {
      const forecastText = district.forecastLabel || 'Prediksi aktif';
      const semanticRiskLabel = getSemanticRiskLevelLabel(district);
      const riskInfo = semanticRiskLabel ? `<br>Tingkat risiko: ${semanticRiskLabel}` : '';
      const drainageInfo = district.drainageCondition ? `<br>Drainase: ${district.drainageCondition}` : '';

      return `
        <strong>${district.label}</strong><br>
        ${forecastText}: ${getRainfallDisplayValue(district)}
        ${drainageInfo}
        ${riskInfo}
      `;
    };

    state.geojsonLayer = L.geoJSON(geojson, {
      style: getFeatureStyle,
      onEachFeature: (feature, layer) => {
        const key = normalizeDistrictToken(feature?.properties?.name || '');
        const district = districtLookup.get(key);

        if (!district) {
          return;
        }

        state.layerByKey.set(key, layer);
        layer.bindPopup(popupContent(district));
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
          mouseout: () => {
            state.geojsonLayer?.eachLayer(eachLayer => {
              eachLayer.setStyle(getFeatureStyle(eachLayer.feature));
            });
          },
          click: () => {
            onSelect(key);
            layer.openPopup();
          }
        });
      }
    }).addTo(map);

    const heatPoints = districts.map(district => {
      const layer = state.layerByKey.get(normalizeDistrictToken(district.name));
      const center = layer?.getBounds?.().getCenter?.();
      return center ? [center.lat, center.lng, Number(district.riskScore) || 0] : null;
    }).filter(Boolean);

    const heatLayer = L.heatLayer(heatPoints, {
      radius: 42,
      blur: 30,
      minOpacity: 0.4,
      maxZoom: 13,
      gradient: {
        0.2: '#2f9e44',
        0.55: '#f0c419',
        1: '#e03131'
      }
    });

    const labelLayer = L.layerGroup(
      districts.map(district => {
        const layer = state.layerByKey.get(normalizeDistrictToken(district.name));
        const center = layer?.getBounds?.().getCenter?.();

        if (!center) {
          return null;
        }

        const marker = L.circleMarker(center, {
          radius: 7,
          weight: 1.5,
          color: '#ffffff',
          fillColor: getRiskColor(district),
          fillOpacity: 0.98
        });

        marker.bindTooltip(district.label, {
          permanent: true,
          direction: 'top',
          offset: [0, -12],
          className: 'heat-label'
        });
        marker.bindPopup(popupContent(district));
        marker.on('click', () => onSelect(normalizeDistrictToken(district.name)));
        return marker;
      }).filter(Boolean)
    );

    state.heatOverlay = L.layerGroup([heatLayer, labelLayer]).addTo(map);

    state.layersControl = L.control.layers(
      {},
      {
        'Peta Tematik Risiko': state.geojsonLayer,
        'Overlay Heatmap + Label': state.heatOverlay
      },
      { collapsed: true }
    ).addTo(map);

    state.legendControl = L.control({ position: 'bottomright' });
    state.legendControl.onAdd = () => {
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
    state.legendControl.addTo(map);

    const bounds = state.geojsonLayer.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [26, 26] });
    }
  }, [geojson, districts, onSelect]);

  useEffect(() => {
    if (!mapContainerRef.current || !mapRef.current || typeof ResizeObserver === 'undefined') {
      return undefined;
    }

    const observer = new ResizeObserver(() => {
      mapRef.current?.invalidateSize();
    });

    observer.observe(mapContainerRef.current);

    return () => {
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    if (!selectedKey || !mapRef.current || !layerStateRef.current.geojsonLayer) {
      return;
    }

    const layer = layerStateRef.current.layerByKey.get(selectedKey);
    if (!layer) {
      return;
    }

    layerStateRef.current.geojsonLayer.eachLayer(eachLayer => {
      const eachKey = normalizeDistrictToken(eachLayer.feature?.properties?.name || '');
      const district = districts.find(item => normalizeDistrictToken(item.name) === eachKey);
      eachLayer.setStyle({
        fillColor: district ? getRiskColor(district) : '#94a3b8',
        weight: eachKey === selectedKey ? 3 : 1.4,
        color: eachKey === selectedKey ? '#17324d' : '#ffffff',
        dashArray: eachKey === selectedKey ? '' : '3',
        fillOpacity: eachKey === selectedKey ? 0.88 : 0.76
      });
    });

    mapRef.current.flyToBounds(layer.getBounds(), {
      padding: [36, 36],
      duration: 0.8
    });
    layer.openPopup();
  }, [districts, selectedKey]);

  return <div id="map" ref={mapContainerRef} />;
}

function MetricInfoCard({ label, value }) {
  return (
    <div className="detail-metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function PublicFaqSection() {
  const [openKey, setOpenKey] = useState(PUBLIC_FAQ_ITEMS[0]?.key || '');

  return (
    <section className="panel public-faq-section" aria-labelledby="publicFaqTitle">
      <div className="public-faq-layout">
        <div className="public-faq-copy">
          <p className="public-faq-kicker">Panduan Singkat</p>
          <h2 id="publicFaqTitle">FAQs</h2>
          <p>
            Beberapa pertanyaan umum ini membantu pengguna memahami tujuan FloodGIS,
            sumber data, arti metrik, dan cara membaca hasil visualisasi.
          </p>
        </div>

        <div className="public-faq-list">
          {PUBLIC_FAQ_ITEMS.map(item => {
            const isOpen = item.key === openKey;

            return (
              <article key={item.key} className={`public-faq-item ${isOpen ? 'is-open' : ''}`.trim()}>
                <button
                  type="button"
                  className="public-faq-trigger"
                  aria-expanded={isOpen}
                  aria-controls={`faq-panel-${item.key}`}
                  onClick={() => setOpenKey(current => (current === item.key ? '' : item.key))}
                >
                  <span>{item.question}</span>
                  <span className="public-faq-icon" aria-hidden="true">
                    {isOpen ? '−' : '+'}
                  </span>
                </button>

                {isOpen ? (
                  <div id={`faq-panel-${item.key}`} className="public-faq-panel">
                    <p>{item.answer}</p>
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function DetailPanel({ district, trendSeries, isTrendLoading }) {
  if (!district) {
    return (
      <div className="detail-content">
        <div className="empty-state">
          Pilih kecamatan dari peta atau kartu ringkasan untuk melihat detail.
        </div>
      </div>
    );
  }

  const forecastValue = String(district.forecastLabel || '').replace(/^Prediksi\s+/i, '').trim();
  const recommendationItems = getDistrictRecommendationItems(district);
  const recommendationTitle = district.recommendation || getDistrictRecommendationTitle(district);

  return (
    <div className="detail-content">
      <div className="detail-sheet">
        <div className="detail-sheet-head">
          <h3 className="detail-sheet-title">{district.label}</h3>
          <div className="detail-sheet-meta-row">
            <p className="detail-sheet-date">{formatDateNumeric(forecastValue || district.latestObservationDate)}</p>
            <span className={`detail-risk-pill ${getRiskTone(district)}`.trim()}>{getDetailRiskDisplay(district)}</span>
          </div>
        </div>

        <div className="detail-metric-grid">
          <MetricInfoCard
            label="Tingkat Risiko"
            value={getDetailRiskDisplay(district)}
          />
          <MetricInfoCard
            label="Curah Hujan"
            value={getDetailRainDisplay(district)}
          />
          <MetricInfoCard
            label="Kondisi Drainase"
            value={district.drainageCondition || 'Tidak tersedia'}
          />
          <MetricInfoCard
            label="Rata-Rata 3 Hari"
            value={formatRainMm(district.recentThreeDayAverageMm)}
          />
          <MetricInfoCard
            label="Potensi Hujan Lebat/Ekstrem"
            value={formatPercent(district.probabilityWaspadaPercent)}
          />
        </div>

        <RiskTrendCard trendSeries={trendSeries} isLoading={isTrendLoading} />

        <div className="detail-recommendation-card">
          <span>Rekomendasi</span>
          <strong>{recommendationTitle}</strong>
          <ul>
            {recommendationItems.map(item => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>

        <button
          className="detail-download-button"
          type="button"
          onClick={() => downloadDistrictCsv(district)}
        >
          Download File CSV
        </button>
      </div>
    </div>
  );
}

export default function PublicApp() {
  const [payload, setPayload] = useState(null);
  const [geojson, setGeojson] = useState(null);
  const [sourceUrl, setSourceUrl] = useState('');
  const [selectedKey, setSelectedKey] = useState('');
  const [selectedForecastDay, setSelectedForecastDay] = useState(1);
  const [riskFilter, setRiskFilter] = useState('all');
  const [riskTrendHistory, setRiskTrendHistory] = useState([]);
  const [riskTrendLoading, setRiskTrendLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const cardsTrackRef = useRef(null);

  useEffect(() => {
    document.body.className = 'public-home';
  }, []);

  useEffect(() => {
    let cancelled = false;

    Promise.all([
      fetchFirstAvailable(buildGeojsonCandidates(), 'GeoJSON Jakarta Timur gagal dimuat.'),
      fetchFirstAvailable(buildPredictionCandidates(), 'Prediksi aktif gagal dimuat.')
    ])
      .then(([geojsonResult, predictionResult]) => {
        if (cancelled) {
          return;
        }

        const predictionPayload = predictionResult.payload;
        const filteredGeojson = filterEastJakartaGeojson(geojsonResult.payload, predictionPayload.districts || []);
        const requestedDistrict = new URLSearchParams(window.location.search).get('district');
        const requestedDay = new URLSearchParams(window.location.search).get('day');
        const requestedKey = normalizeDistrictToken(requestedDistrict || '');
        const availableForecastDays = [...(predictionPayload.forecastDays || [])]
          .map(item => maxSafeDayOffset(item?.dayOffset))
          .sort((left, right) => left - right);
        const initialForecastDay = availableForecastDays.includes(maxSafeDayOffset(requestedDay))
          ? maxSafeDayOffset(requestedDay)
          : (availableForecastDays[0] || 1);
        const displayDistricts = (predictionPayload.districts || []).map(district =>
          buildDisplayDistrict(district, initialForecastDay)
        );
        const sortedDistricts = [...displayDistricts].sort(
          (left, right) => Number(right.riskScore || 0) - Number(left.riskScore || 0)
        );
        const initialDistrict = displayDistricts.find(
          district => normalizeDistrictToken(district.name) === requestedKey
        ) || sortedDistricts[0];

        setGeojson(filteredGeojson);
        setPayload(predictionPayload);
        setSourceUrl(predictionResult.sourceUrl);
        setSelectedForecastDay(initialForecastDay);
        setSelectedKey(initialDistrict ? normalizeDistrictToken(initialDistrict.name) : '');
        setErrorMessage('');
      })
      .catch(error => {
        console.error('Gagal memuat frontend React publik:', error);
        if (!cancelled) {
          setErrorMessage('Gagal memuat data. Backend live dan file JSON cadangan sama-sama tidak bisa dibaca, jadi peta belum dapat ditampilkan.');
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (selectedKey) {
      url.searchParams.set('district', selectedKey);
    } else {
      url.searchParams.delete('district');
    }
    url.searchParams.set('day', String(selectedForecastDay));
    window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
  }, [selectedForecastDay, selectedKey]);

  const baseDistricts = payload?.districts || [];
  const forecastDays = [...(payload?.forecastDays || [])].sort(
    (left, right) => maxSafeDayOffset(left?.dayOffset) - maxSafeDayOffset(right?.dayOffset)
  );
  const effectiveForecastDay = forecastDays.some(day => maxSafeDayOffset(day?.dayOffset) === selectedForecastDay)
    ? selectedForecastDay
    : (forecastDays[0]?.dayOffset || 1);
  const districts = baseDistricts.map(district => buildDisplayDistrict(district, effectiveForecastDay));
  const activeRiskFilter = getRiskFilterMeta(riskFilter);
  const filteredDistricts = districts.filter(district => activeRiskFilter.match(district));
  const sortedDistricts = [...filteredDistricts].sort((left, right) => {
    const riskDifference = Number(right.riskScore || 0) - Number(left.riskScore || 0);
    if (riskDifference !== 0) {
      return riskDifference;
    }

    return String(left.label || '').localeCompare(String(right.label || ''), 'id');
  });
  const selectedDistrict = sortedDistricts.find(district => normalizeDistrictToken(district.name) === selectedKey) || sortedDistricts[0] || null;

  const activeForecastMeta = forecastDays.find(
    day => maxSafeDayOffset(day?.dayOffset) === effectiveForecastDay
  ) || null;
  const metaForSelectedDay = payload
    ? {
        ...(payload.meta || {}),
        forecastTargetDate: activeForecastMeta?.forecastTargetDate || payload?.meta?.forecastTargetDate || null
      }
    : null;

  const sourceStatus = getPublicPayloadStatus(payload?.meta || {}, sourceUrl);
  const freshnessInfo = payload ? buildFreshnessInfo(metaForSelectedDay || {}, filteredDistricts) : null;
  const averageRiskScore = filteredDistricts.length
    ? Math.round(filteredDistricts.reduce((sum, district) => sum + ((Number(district.riskScore) || 0) * 100), 0) / filteredDistricts.length)
    : 0;

  const mapSubtitle = selectedDistrict
    ? `${selectedDistrict.label}${selectedDistrict.forecastLabel ? ` (${selectedDistrict.forecastLabel})` : ''} sedang ditampilkan sebagai wilayah fokus.`
    : `Menampilkan ${filteredDistricts.length} kecamatan berdasarkan prediksi aktif dan kondisi wilayah terbaru.`;

  const statRefreshParts = [];
  if (freshnessInfo?.forecastValue) {
    statRefreshParts.push(`Prediksi: ${formatDateOnly(freshnessInfo.forecastValue)}`);
  }
  if (freshnessInfo?.generatedValue) {
    statRefreshParts.push(`Payload: ${formatUpdatedAt(freshnessInfo.generatedValue)}`);
  }
  if (payload?.meta?.publishedAt) {
    statRefreshParts.push(`Publish: ${formatUpdatedAt(payload.meta.publishedAt)}`);
  }
  if (freshnessInfo?.ageDays !== null && freshnessInfo?.ageDays !== undefined) {
    statRefreshParts.push(`Usia data: ${freshnessInfo.ageDays} hari`);
  }

  const handleSelectDistrict = useCallback(key => {
    setSelectedKey(key);

    const card = cardsTrackRef.current?.querySelector?.(`.showcase-card[data-key="${key}"]`);
    if (card && cardsTrackRef.current) {
      const cardCenter = card.offsetLeft + (card.offsetWidth / 2);
      const targetLeft = Math.max(0, cardCenter - (cardsTrackRef.current.clientWidth / 2));
      cardsTrackRef.current.scrollTo({ left: targetLeft, behavior: 'smooth' });
    }
  }, []);

  const scrollCards = direction => {
    if (!cardsTrackRef.current) {
      return;
    }

    cardsTrackRef.current.scrollBy({
      left: direction * Math.max(220, cardsTrackRef.current.clientWidth * 0.82),
      behavior: 'smooth'
    });
  };

  useEffect(() => {
    if (!sortedDistricts.length) {
      if (selectedKey) {
        setSelectedKey('');
      }
      return;
    }

    const isSelectedStillVisible = sortedDistricts.some(
      district => normalizeDistrictToken(district.name) === selectedKey
    );

    if (!isSelectedStillVisible) {
      setSelectedKey(normalizeDistrictToken(sortedDistricts[0].name));
    }
  }, [selectedKey, sortedDistricts]);

  useEffect(() => {
    let cancelled = false;

    if (!selectedDistrict?.name) {
      setRiskTrendHistory([]);
      setRiskTrendLoading(false);
      return undefined;
    }

    setRiskTrendLoading(true);

    fetchFirstAvailable(
      buildPublicDistrictTrendHistoryEndpoints(selectedDistrict.name, 3),
      'Histori risiko kecamatan gagal dimuat.'
    )
      .then(result => {
        if (cancelled) {
          return;
        }

        const historyEntries = Array.isArray(result?.payload?.history) ? result.payload.history : [];
        const trendEntries = historyEntries.map((item, index) => ({
          key: `${selectedDistrict.name}-${item.runId || item.targetPredictionDate || index}`,
          label: index === historyEntries.length - 1 ? 'Hari ini' : `H-${historyEntries.length - 1 - index}`,
          dateLabel: formatDateNumeric(item.targetPredictionDate || item.observationDate || item.generatedAt),
          value: Number((Number(item?.riskScore || 0) || 0) * 100)
        }));

        setRiskTrendHistory(trendEntries);
        setRiskTrendLoading(false);
      })
      .catch(error => {
        console.warn('Histori risiko publik gagal dimuat:', error);
        if (cancelled) {
          return;
        }
        setRiskTrendHistory([]);
        setRiskTrendLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedDistrict?.name]);

  return (
    <>
      <header className="site-header" id="top">
        <div className="nav-inner nav-simple home-nav">
          <a className="brand home-brand" href="#" aria-label="FloodGIS Jaktim Home">
            <img
              className="brand-logo"
              src={brandAssets.logoFloodgis}
              alt="FloodGIS Jaktim"
              width="1200"
              height="400"
            />
          </a>
        </div>
      </header>

      {payload?.meta?.isStaging ? (
        <div className="environment-banner staging">
          {(payload.meta.appName || 'FloodGIS Jakarta Timur')} - {(payload.meta.deploymentEnvironmentLabel || 'STAGING')}: versi uji coba, bukan web utama.
        </div>
      ) : null}

      <main className="app-shell home-shell">
        <section className="panel district-showcase" aria-labelledby="districtShowcaseTitle">
          <div className="district-showcase-head">
            <div>
              <h2 id="districtShowcaseTitle">Ringkasan Kecamatan</h2>
              <p>Geser kartu untuk melihat prediksi 3 hari ke depan tiap kecamatan dan klik kartu untuk fokus ke wilayah tersebut.</p>
            </div>
            {forecastDays.length > 0 ? (
              <div className="forecast-day-switcher" role="tablist" aria-label="Pilih horizon prediksi">
                {forecastDays.map(day => {
                  const dayOffset = maxSafeDayOffset(day?.dayOffset);
                  const isActive = dayOffset === effectiveForecastDay;
                  return (
                    <button
                      key={dayOffset}
                      className={`forecast-day-button ${isActive ? 'active' : ''}`.trim()}
                      type="button"
                      role="tab"
                      aria-selected={isActive}
                      onClick={() => setSelectedForecastDay(dayOffset)}
                    >
                      {getForecastTabLabel(dayOffset, day?.label)}
                    </button>
                  );
                })}
              </div>
            ) : null}
          </div>

          <div className="public-risk-filter-row" role="group" aria-label="Filter tingkat risiko">
            <span className="public-risk-filter-label">Filter Tingkat Risiko</span>
            <div className="public-risk-filter-chips">
              {PUBLIC_RISK_FILTERS.map(filterItem => {
                const isActive = filterItem.key === riskFilter;
                return (
                  <button
                    key={filterItem.key}
                    className={`public-risk-filter-chip ${isActive ? 'active' : ''}`.trim()}
                    type="button"
                    onClick={() => setRiskFilter(filterItem.key)}
                  >
                    {filterItem.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="district-showcase-viewport">
            <button className="showcase-scroll-button is-left" type="button" aria-label="Geser kartu ke kiri" onClick={() => scrollCards(-1)}>
              <img className="showcase-scroll-icon is-left" src={brandAssets.showcaseArrow} alt="" aria-hidden="true" />
            </button>

            <div ref={cardsTrackRef} className="district-cards-track" aria-live="polite">
              {sortedDistricts.length === 0 ? (
                <article className="showcase-empty-card">
                  {errorMessage || 'Tidak ada kecamatan yang cocok dengan filter risiko saat ini.'}
                </article>
              ) : sortedDistricts.map(district => {
                const tone = getRiskTone(district);
                const iconSpec = getShowcaseIconSpec(district);
                const isActive = normalizeDistrictToken(district.name) === selectedKey;

                return (
                  <article
                    key={district.name}
                    className={`showcase-card ${tone} icon-tone-${iconSpec.key} ${isActive ? 'active' : ''}`.trim()}
                    data-key={normalizeDistrictToken(district.name)}
                    tabIndex={0}
                    role="button"
                    aria-label={`Pilih ${district.label}`}
                    onClick={() => handleSelectDistrict(normalizeDistrictToken(district.name))}
                    onKeyDown={event => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        handleSelectDistrict(normalizeDistrictToken(district.name));
                      }
                    }}
                  >
                    <div className="showcase-card-top">
                      <h3 className="showcase-card-title">{district.label}</h3>
                      <p className="showcase-card-subtitle">{getShowcaseForecastDate(district)}</p>
                    </div>
                    <div className="showcase-card-icon">
                      <img className="showcase-weather-icon" src={iconSpec.path} alt="" aria-hidden="true" />
                    </div>
                    <p className="showcase-card-value">{getShowcasePrimaryValue(district)}</p>
                    <p className="showcase-card-label">{getShowcaseRainSummary(district)}</p>
                    <p className="showcase-card-risk">{getShowcaseFloodRiskLine(district)}</p>
                  </article>
                );
              })}
            </div>

            <button className="showcase-scroll-button is-right" type="button" aria-label="Geser kartu ke kanan" onClick={() => scrollCards(1)}>
              <img className="showcase-scroll-icon" src={brandAssets.showcaseArrow} alt="" aria-hidden="true" />
            </button>
          </div>
        </section>

        <section className="stats-grid public-summary-stats">
          <article className="stat-card">
            <span>Total Kecamatan</span>
            <strong>{formatNumber(filteredDistricts.length)}</strong>
            <small>Wilayah yang sedang tampil sesuai filter</small>
          </article>
          <article className="stat-card">
            <span>Perlu Waspada</span>
            <strong>{formatNumber(filteredDistricts.filter(district => Number(district.webgisLevel) >= 3).length)}</strong>
            <small>Kecamatan yang butuh perhatian lebih</small>
          </article>
          <article className="stat-card">
            <span>Rata-Rata Risiko</span>
            <strong>{`${formatNumber(averageRiskScore)} / 100`}</strong>
            <small>Gambaran umum kondisi Jakarta Timur</small>
          </article>
          <article className="stat-card">
            <span>Observasi Terakhir</span>
            <strong>{freshnessInfo?.observationValue ? formatDateOnly(freshnessInfo.observationValue) : formatUpdatedAt(payload?.meta?.updatedAt)}</strong>
            <small>{statRefreshParts.join(' | ') || 'Menunggu informasi pembaruan data'}</small>
          </article>
        </section>

        <section className="content-grid">
          <div className="map-panel">
            <div className="map-panel-head">
              <div>
                <h2>Peta Risiko Banjir</h2>
                <p>{errorMessage ? 'Terjadi kendala saat memuat peta atau data prediksi.' : mapSubtitle}</p>
              </div>
              <div className={`status-pill ${sourceStatus.tone}`.trim()}>{errorMessage ? 'Gagal memuat' : sourceStatus.text}</div>
            </div>

            {errorMessage || !geojson ? (
              <div className="detail-content">
                <div className="empty-state">{errorMessage || 'Memuat peta...'}</div>
              </div>
            ) : (
              <PublicRiskMap
                geojson={geojson}
                districts={filteredDistricts}
                selectedKey={selectedKey}
                onSelect={handleSelectDistrict}
              />
            )}
          </div>

          <aside className="side-panel">
            <section className="panel detail-panel">
              <div className="panel-heading">
                <h2>Detail Kecamatan</h2>
                <p>Informasi wilayah akan tampil setelah kecamatan dipilih.</p>
              </div>
              <DetailPanel district={selectedDistrict} trendSeries={riskTrendHistory} isTrendLoading={riskTrendLoading} />
            </section>
          </aside>
        </section>

        <PublicFaqSection />
      </main>

      <footer className="site-footer">
        <div className="footer-inner">
          <div className="footer-bottom">
            <p className="footer-copy">&copy; 2026 FloodGIS Jakarta Timur</p>
            <a className="back-to-top" href="#top" aria-label="Kembali ke atas" title="Kembali ke atas" />
          </div>
        </div>
      </footer>
    </>
  );
}
