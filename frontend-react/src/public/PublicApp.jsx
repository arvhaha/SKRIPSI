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
  buildGeoJsonEndpoints,
  buildPredictionEndpoints,
  buildPublicPredictionSnapshotEndpoints,
  fetchFirstAvailable,
  fetchJson
} from '../shared/api';

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
      const modelInfo = !Number.isNaN(getPredictedClassConfidencePercentValue(district))
        ? `<br>Confidence kelas dominan: ${formatPercent(getPredictedClassConfidencePercentValue(district))}`
        : '';
      const semanticRiskLabel = getSemanticRiskLevelLabel(district);
      const riskInfo = semanticRiskLabel ? `<br>Tingkat risiko: ${semanticRiskLabel}` : '';
      const drainageInfo = district.drainageCondition ? `<br>Drainase: ${district.drainageCondition}` : '';

      return `
        <strong>${district.label}</strong><br>
        ${forecastText}: ${getRainfallDisplayValue(district)}
        ${drainageInfo}
        ${riskInfo}
        ${modelInfo}
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

function DetailPanel({ district }) {
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

  return (
    <div className="detail-content">
      <div className="detail-sheet">
        <div className="detail-sheet-head">
          <h3 className="detail-sheet-title">{district.label}</h3>
          <p className="detail-sheet-date">{formatDateNumeric(forecastValue || district.latestObservationDate)}</p>
        </div>

        <div className="detail-sheet-stack">
          <div className="detail-stack-card">
            <span>Tingkat Risiko</span>
            <strong>{getDetailRiskDisplay(district)}</strong>
          </div>
          <div className="detail-stack-card">
            <span>Curah Hujan</span>
            <strong>{getDetailRainDisplay(district)}</strong>
          </div>
          <div className="detail-stack-card">
            <span>Kondisi Drainase</span>
            <strong>{district.drainageCondition || 'Tidak tersedia'}</strong>
          </div>
          <div className="detail-stack-card">
            <span>Rata-Rata 3 Hari</span>
            <strong>{formatRainMm(district.recentThreeDayAverageMm)}</strong>
          </div>
          <div className="detail-stack-card">
            <span>Potensi Hujan Lebat/Ekstrem</span>
            <strong>{formatPercent(district.probabilityWaspadaPercent)}</strong>
          </div>
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
  const selectedDistrict = districts.find(district => normalizeDistrictToken(district.name) === selectedKey) || null;
  const sortedDistricts = [...districts].sort((left, right) => {
    const riskDifference = Number(right.riskScore || 0) - Number(left.riskScore || 0);
    if (riskDifference !== 0) {
      return riskDifference;
    }

    return String(left.label || '').localeCompare(String(right.label || ''), 'id');
  });

  const activeForecastMeta = forecastDays.find(
    day => maxSafeDayOffset(day?.dayOffset) === effectiveForecastDay
  ) || null;
  const metaForSelectedDay = payload
    ? {
        ...(payload.meta || {}),
        forecastTargetDate: activeForecastMeta?.forecastTargetDate || payload?.meta?.forecastTargetDate || null
      }
    : null;

  const freshnessBanner = payload ? buildFreshnessBanner(metaForSelectedDay || {}, districts, sourceUrl) : null;
  const sourceStatus = getPublicPayloadStatus(payload?.meta || {}, sourceUrl);
  const freshnessInfo = payload ? buildFreshnessInfo(metaForSelectedDay || {}, districts) : null;
  const averageRiskScore = districts.length
    ? Math.round(districts.reduce((sum, district) => sum + ((Number(district.riskScore) || 0) * 100), 0) / districts.length)
    : 0;

  const mapSubtitle = selectedDistrict
    ? `${selectedDistrict.label}${selectedDistrict.forecastLabel ? ` (${selectedDistrict.forecastLabel})` : ''} sedang ditampilkan sebagai wilayah fokus.`
    : `Menampilkan ${districts.length} kecamatan berdasarkan prediksi aktif dan kondisi wilayah terbaru.`;

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

          <div className="district-showcase-viewport">
            <button className="showcase-scroll-button is-left" type="button" aria-label="Geser kartu ke kiri" onClick={() => scrollCards(-1)}>
              <img className="showcase-scroll-icon is-left" src={brandAssets.showcaseArrow} alt="" aria-hidden="true" />
            </button>

            <div ref={cardsTrackRef} className="district-cards-track" aria-live="polite">
              {sortedDistricts.length === 0 ? (
                <article className="showcase-empty-card">
                  {errorMessage || 'Memuat ringkasan kecamatan...'}
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
            <strong>{formatNumber(districts.length)}</strong>
            <small>Wilayah yang ditampilkan di peta</small>
          </article>
          <article className="stat-card">
            <span>Perlu Waspada</span>
            <strong>{formatNumber(districts.filter(district => Number(district.webgisLevel) >= 3).length)}</strong>
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

            {freshnessBanner ? (
              <div className={`data-freshness-banner ${freshnessBanner.tone}`.trim()}>
                <strong>{freshnessBanner.title}</strong> {freshnessBanner.message}
              </div>
            ) : null}

            {errorMessage || !geojson ? (
              <div className="detail-content">
                <div className="empty-state">{errorMessage || 'Memuat peta...'}</div>
              </div>
            ) : (
              <PublicRiskMap
                geojson={geojson}
                districts={districts}
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
              <DetailPanel district={selectedDistrict} />
            </section>
          </aside>
        </section>
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
