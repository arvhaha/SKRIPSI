import { Fragment, useEffect, useState } from 'react';

import { brandAssets } from '../shared/assets';
import {
  buildFreshnessInfo,
  formatDateOnly,
  formatDrainageConfidence,
  formatHistoryDescription,
  formatMillimeter,
  formatPercent,
  formatScore,
  formatSignedPercent,
  formatUpdatedAt,
  getCompactRiskLevelLabel,
  getProbabilityPercentValue,
  getPublicPayloadStatus,
  getRainfallDisplayValue,
  getRiskTone,
  getSemanticRiskLevelLabel,
  normalizeDistrictToken,
  toTitleCaseWords
} from '../shared/formatters';
import {
  buildAdminPredictionRunHistoryUrl,
  buildAdminPreviewEndpoints,
  buildApiUrl,
  fetchJson,
  fetchFirstAvailable,
  getConfiguredApiBaseUrl,
  getConfiguredPublicBaseUrl,
  postJson
} from '../shared/api';

function normalizeAdminPreviewResponse(responsePayload) {
  return {
    payload: responsePayload?.payload || responsePayload,
    overrides: responsePayload?.overrides || {},
    publication: responsePayload?.publication || null,
    history: Array.isArray(responsePayload?.history) ? responsePayload.history : []
  };
}

function isLiveBackendSource(sourceUrl) {
  return Boolean(sourceUrl && sourceUrl.includes('api/admin/predictions/live'));
}

function getAdminDraftStatus(sourceUrl) {
  if (isLiveBackendSource(sourceUrl)) {
    return { text: 'Draft Live Backend', tone: 'success' };
  }

  return { text: 'JSON Cadangan', tone: 'warning' };
}

function buildPublicMapUrl(districtName) {
  const publicBaseUrl = getConfiguredPublicBaseUrl();
  const configuredApiBaseUrl = getConfiguredApiBaseUrl();
  const baseHref = publicBaseUrl || 'index.html';
  const url = new URL(baseHref, window.location.href);

  if (districtName) {
    url.searchParams.set('district', districtName);
  } else {
    url.searchParams.delete('district');
  }

  if (configuredApiBaseUrl) {
    url.searchParams.set('apiBaseUrl', configuredApiBaseUrl);
  }

  return `${url.origin}${url.pathname}${url.search}${url.hash}`;
}

function buildFreshnessBanner(payload, sourceUrl) {
  const predictions = payload?.districts || [];
  const freshnessInfo = buildFreshnessInfo(payload?.meta || {}, predictions);

  if (!freshnessInfo.available) {
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
  if (!isLiveBackendSource(sourceUrl)) {
    tone = 'warning';
    messageParts.unshift('Sumber data saat ini memakai file JSON cadangan karena backend live tidak tersedia.');
  }

  if (freshnessInfo.ageDays !== null && freshnessInfo.ageDays >= freshnessInfo.staleThresholdDays) {
    tone = 'warning';
    messageParts.push(`Data observasi tertinggal ${freshnessInfo.ageDays} hari dari tanggal akses, jadi admin perlu cek konteks sebelum membagikan hasil.`);
  } else if (freshnessInfo.ageDays !== null) {
    messageParts.push(`Usia data observasi saat dibuka sekitar ${freshnessInfo.ageDays} hari.`);
  }

  return {
    tone,
    title: !isLiveBackendSource(sourceUrl)
      ? 'Sedang memakai JSON cadangan.'
      : tone === 'warning'
      ? 'Perlu cek freshness data.'
      : 'Status freshness data.',
    message: messageParts.join(' '),
    info: freshnessInfo
  };
}

function getHistoryActionMeta(entry) {
  const actionType = String(entry?.type || '').trim().toLowerCase();

  switch (actionType) {
    case 'publish':
      return {
        label: 'Publish',
        title: 'Publish ke homepage',
        badgeClass: 'is-success'
      };
    case 'override_saved':
      return {
        label: 'Override',
        title: 'Override drainase disimpan',
        badgeClass: 'is-info'
      };
    case 'override_reset':
      return {
        label: 'Reset',
        title: 'Override drainase direset',
        badgeClass: 'is-neutral'
      };
    default:
      return {
        label: 'Aktivitas',
        title: 'Aktivitas admin',
        badgeClass: 'is-neutral'
      };
  }
}

function getPredictionRunTypeLabel(runType) {
  switch (String(runType || '').trim().toLowerCase()) {
    case 'admin_publish':
      return 'Publish Admin';
    case 'scheduled_export':
      return 'Scheduler Harian';
    default:
      return 'Run Backend';
  }
}

function formatHistoryDistrictName(value, districts) {
  const rawValue = String(value ?? '').trim();
  if (!rawValue) {
    return '';
  }

  const normalizedValue = normalizeDistrictToken(rawValue);
  const matchingDistrict = (districts || []).find(district =>
    normalizeDistrictToken(district?.name) === normalizedValue ||
    normalizeDistrictToken(district?.label) === normalizedValue
  );

  if (matchingDistrict?.label) {
    return matchingDistrict.label;
  }

  return toTitleCaseWords(rawValue);
}

function buildSelectedFromQuery(districts) {
  if (!districts.length) {
    return null;
  }

  const requestedDistrict = new URLSearchParams(window.location.search).get('district');
  if (!requestedDistrict) {
    return districts[0].name;
  }

  const requestedToken = normalizeDistrictToken(requestedDistrict);
  const matchedDistrict = districts.find(district =>
    normalizeDistrictToken(district.name) === requestedToken ||
    normalizeDistrictToken(district.label) === requestedToken
  );

  return matchedDistrict ? matchedDistrict.name : districts[0].name;
}

function sortDistrictsByRisk(districts) {
  return [...districts].sort((left, right) => {
    const riskDifference = Number(right.riskScore || 0) - Number(left.riskScore || 0);
    if (riskDifference !== 0) {
      return riskDifference;
    }

    return String(left.label || '').localeCompare(String(right.label || ''), 'id');
  });
}

export default function AdminApp() {
  const [payload, setPayload] = useState(null);
  const [overrides, setOverrides] = useState({});
  const [publication, setPublication] = useState(null);
  const [history, setHistory] = useState([]);
  const [predictionRuns, setPredictionRuns] = useState([]);
  const [sourceUrl, setSourceUrl] = useState('');
  const [selectedDistrictName, setSelectedDistrictName] = useState(null);
  const [expandedDistrictName, setExpandedDistrictName] = useState(null);
  const [draftOverrideValue, setDraftOverrideValue] = useState('');
  const [activeView, setActiveView] = useState(() => {
    const hashValue = String(window.location.hash || '').replace(/^#/, '').trim().toLowerCase();
    return ['dashboard', 'review', 'predictions', 'backend'].includes(hashValue) ? hashValue : 'dashboard';
  });
  const [message, setMessage] = useState({ text: '', tone: '' });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    document.body.className = 'admin-dashboard-page';
  }, []);

  useEffect(() => {
    const nextUrl = new URL(window.location.href);
    nextUrl.hash = activeView;
    window.history.replaceState({}, '', `${nextUrl.pathname}${nextUrl.search}${nextUrl.hash}`);
  }, [activeView]);

  useEffect(() => {
    if (!selectedDistrictName) {
      return;
    }

    const nextUrl = new URL(window.location.href);
    nextUrl.searchParams.set('district', selectedDistrictName);
    window.history.replaceState({}, '', `${nextUrl.pathname}${nextUrl.search}${nextUrl.hash}`);
  }, [selectedDistrictName]);

  async function loadPayload(nextMessage = 'Draft admin berhasil dimuat.') {
    setBusy(true);

    try {
      const { payload: rawResponse, sourceUrl: nextSourceUrl } = await fetchFirstAvailable(
        buildAdminPreviewEndpoints().map(url => ({ url })),
        'Tidak ada sumber data prediksi yang berhasil dimuat.'
      );
      const response = normalizeAdminPreviewResponse(rawResponse);
      const districts = response.payload?.districts || [];
      const runHistoryResponse = await fetchJson(buildAdminPredictionRunHistoryUrl(8)).catch(() => ({ runs: [] }));

      setPayload(response.payload);
      setOverrides(response.overrides || {});
      setPublication(response.publication || null);
      setHistory(response.history || []);
      setPredictionRuns(Array.isArray(runHistoryResponse?.runs) ? runHistoryResponse.runs : []);
      setSourceUrl(nextSourceUrl);
      setSelectedDistrictName(current => {
        if (current && districts.some(district => district.name === current)) {
          return current;
        }

        return buildSelectedFromQuery(districts);
      });
      setExpandedDistrictName(current => {
        if (current && districts.some(district => district.name === current)) {
          return current;
        }

        return null;
      });
      setMessage({ text: nextMessage, tone: 'success' });
    } catch (error) {
      console.error('Gagal memuat frontend React admin:', error);
      setPayload(null);
      setOverrides({});
      setPublication(null);
      setHistory([]);
      setPredictionRuns([]);
      setSourceUrl('');
      setSelectedDistrictName(null);
      setExpandedDistrictName(null);
      setMessage({ text: 'Data backend admin gagal dimuat.', tone: 'error' });
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    loadPayload();
  }, []);

  const districts = payload?.districts || [];
  const orderedDistricts = sortDistrictsByRisk(districts);
  const selectedDistrict = districts.find(district => district.name === selectedDistrictName) || null;
  const selectedOverride = selectedDistrictName ? overrides[selectedDistrictName] || null : null;
  const freshnessBanner = payload ? buildFreshnessBanner(payload, sourceUrl) : null;
  const freshnessInfo = payload ? buildFreshnessInfo(payload.meta || {}, districts) : null;
  const averageProbability = districts.length
    ? districts.reduce((total, district) => total + (getProbabilityPercentValue(district) || 0), 0) / districts.length
    : NaN;
  const topDistrict = orderedDistricts[0] || null;
  const priorityDistricts = orderedDistricts.slice(0, 3);
  const publicMapUrl = buildPublicMapUrl(selectedDistrictName);
  const publicationLastPublished = publication?.publishedAt || publication?.payloadUpdatedAt || null;
  const draftStatus = getAdminDraftStatus(sourceUrl);
  const publicStatus = getPublicPayloadStatus(
    {
      publicPayloadSource: publication?.hasPublishedSnapshot ? 'published_snapshot' : '',
      publicPayloadSourceLabel: publication?.sourceLabel || payload?.meta?.publicPayloadSourceLabel || ''
    },
    sourceUrl
  );

  useEffect(() => {
    setDraftOverrideValue(selectedOverride?.drainageCondition || '');
  }, [selectedOverride, selectedDistrictName]);

  const handleSaveOverride = async () => {
    if (!selectedDistrictName) {
      setMessage({ text: 'Pilih kecamatan dulu sebelum menyimpan draft admin.', tone: 'error' });
      return;
    }

    setBusy(true);
    setMessage({ text: 'Menyimpan draft admin...', tone: '' });

    try {
      const response = await postJson(buildApiUrl('api/admin/overrides'), {
        districtName: selectedDistrictName,
        drainageCondition: draftOverrideValue
      });
      await loadPayload(response.message || 'Draft admin berhasil disimpan.');
    } catch (error) {
      console.error('Gagal menyimpan override admin:', error);
      setMessage({ text: error.message || 'Draft admin gagal disimpan.', tone: 'error' });
      setBusy(false);
    }
  };

  const handleResetOverride = async () => {
    if (!selectedDistrictName) {
      setMessage({ text: 'Pilih kecamatan dulu sebelum mereset draft admin.', tone: 'error' });
      return;
    }

    setBusy(true);
    setMessage({ text: 'Mereset draft admin kecamatan ini...', tone: '' });
    setDraftOverrideValue('');

    try {
      const response = await postJson(buildApiUrl('api/admin/overrides'), {
        districtName: selectedDistrictName,
        drainageCondition: ''
      });
      await loadPayload(response.message || 'Draft admin untuk kecamatan ini berhasil direset.');
    } catch (error) {
      console.error('Gagal mereset draft admin:', error);
      setMessage({ text: error.message || 'Draft admin gagal direset.', tone: 'error' });
      setBusy(false);
    }
  };

  const handlePublish = async () => {
    setBusy(true);
    setMessage({ text: 'Mempublish snapshot ke halaman publik...', tone: '' });

    try {
      const response = await postJson(buildApiUrl('api/admin/publish'), {});
      await loadPayload(response.message || 'Snapshot publik berhasil diperbarui dari panel admin.');
    } catch (error) {
      console.error('Gagal publish snapshot publik:', error);
      setMessage({ text: error.message || 'Snapshot publik gagal dipublish.', tone: 'error' });
      setBusy(false);
    }
  };

  const handleExportJson = () => {
    if (!payload) {
      setMessage({ text: 'Belum ada data yang bisa diexport.', tone: 'error' });
      return;
    }

    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: 'application/json'
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'east-jakarta-predictions.json';
    link.click();
    URL.revokeObjectURL(url);
    setMessage({ text: 'JSON berhasil diexport.', tone: 'success' });
  };

  return (
    <div className="admin-dashboard-layout">
      <aside className="admin-sidepane">
        <a className="admin-sidebrand" href="admin.html">
          <img className="brand-logo" src={brandAssets.logoFloodgis} alt="FloodGIS Jaktim" />
          <div className="admin-sidebrand-copy">
            <strong>Admin FloodGIS</strong>
            <small>Validasi internal prediksi banjir kecamatan Jakarta Timur.</small>
          </div>
        </a>

        <nav className="admin-side-nav" aria-label="Menu admin">
          <div className="admin-side-group">
            <p className="admin-side-label">Menu Utama</p>
            {[
              ['dashboard', 'Dashboard'],
              ['review', 'Review Kecamatan'],
              ['predictions', 'Data Prediksi'],
              ['backend', 'Backend Info']
            ].map(([key, label]) => (
              <button
                key={key}
                className={`admin-side-button ${activeView === key ? 'is-active' : ''}`.trim()}
                type="button"
                onClick={() => setActiveView(key)}
              >
                <span>{label}</span>
              </button>
            ))}
          </div>
        </nav>
      </aside>

      <div className="admin-main-shell">
        <main className="app-shell admin-shell admin-shell-sidebar">
          <header className="panel admin-topbar">
            <div className="admin-topbar-copy">
              <p className="eyebrow">Panel Admin</p>
              <h1>FloodGIS Jakarta Timur</h1>
              <p className="hero-text">Frontend React untuk review internal, override drainase publik, dan publish snapshot hasil ke homepage.</p>
            </div>

            <div className="admin-toolbar-actions admin-topbar-actions">
              <a className="admin-link-button button-secondary" href={publicMapUrl}>Buka Peta Publik</a>
              <button id="refreshDataButton" type="button" onClick={() => loadPayload('Draft admin berhasil diperbarui dari backend.')} disabled={busy}>Refresh Data Model</button>
              <button id="exportJsonButton" className="button-secondary" type="button" onClick={handleExportJson} disabled={busy}>Export JSON</button>
            </div>
          </header>

          {payload?.meta?.isStaging ? (
            <div className="environment-banner staging">
              {(payload.meta.appName || 'FloodGIS Jakarta Timur')} - {(payload.meta.deploymentEnvironmentLabel || 'STAGING')}: versi uji coba admin, bukan panel utama.
            </div>
          ) : null}

          <div className={`save-message admin-global-message ${message.tone || ''}`.trim()}>{message.text}</div>

          <section className={`admin-view ${activeView === 'dashboard' ? 'is-active' : ''}`.trim()} data-admin-view="dashboard">
            <article className="panel admin-view-hero">
              <div>
                <span className="admin-section-kicker">Dashboard</span>
                <h2>Ringkasan monitoring admin</h2>
                <p>Baca ringkasan model aktif, wilayah prioritas, dan catatan umum backend sebelum masuk ke proses review kecamatan.</p>
              </div>
            </article>

            <section className="admin-status-strip">
              <article className="admin-runtime-card">
                <span className="admin-runtime-label">Status Data Model</span>
                <strong>{payload ? draftStatus.text : 'Gagal Memuat'}</strong>
                <small>
                  {payload && freshnessInfo
                    ? [
                        freshnessInfo.observationValue ? `Observasi: ${formatDateOnly(freshnessInfo.observationValue)}` : '',
                        freshnessInfo.generatedValue ? `Payload: ${formatUpdatedAt(freshnessInfo.generatedValue)}` : '',
                        freshnessInfo.ageDays !== null ? `Usia: ${freshnessInfo.ageDays} hari` : ''
                      ].filter(Boolean).join(' | ')
                    : 'Pastikan backend lokal sedang berjalan.'}
                </small>
              </article>

              {freshnessBanner ? (
                <div className={`data-freshness-banner admin-inline-banner ${freshnessBanner.tone}`.trim()}>
                  <strong>{freshnessBanner.title}</strong> {freshnessBanner.message}
                </div>
              ) : null}
            </section>

            <section className="admin-kpi-grid" aria-label="Ringkasan cepat admin">
              <article className="kpi-card">
                <span>Total Kecamatan</span>
                <strong>{payload ? String(districts.length) : '-'}</strong>
                <small>Wilayah yang sedang dipantau di WebGIS.</small>
              </article>
              <article className="kpi-card">
                <span>Risiko Tertinggi</span>
                <strong>{topDistrict ? topDistrict.label : '-'}</strong>
                <small>{topDistrict ? `${formatPercent(getProbabilityPercentValue(topDistrict))} | ${getSemanticRiskLevelLabel(topDistrict)}` : 'Menunggu data backend.'}</small>
              </article>
              <article className="kpi-card">
                <span>Kecamatan Siaga</span>
                <strong>{payload ? String(districts.filter(district => Number(district.webgisLevel || 0) >= 2).length) : '-'}</strong>
                <small>Wilayah dengan level WebGIS kuning sampai merah.</small>
              </article>
              <article className="kpi-card">
                <span>Rata-Rata Confidence</span>
                <strong>{Number.isNaN(averageProbability) ? '-' : formatPercent(averageProbability)}</strong>
                <small>Gambaran umum keyakinan model terhadap kelas dominan tiap kecamatan.</small>
              </article>
            </section>

            <section className="admin-dashboard-grid">
              <article className="panel admin-priority-panel">
                <div className="panel-heading">
                  <h2>Kecamatan Prioritas</h2>
                  <p>Tiga kecamatan dengan skor risiko tertinggi untuk ditinjau lebih dahulu.</p>
                </div>
                <div className="priority-list">
                  {priorityDistricts.length === 0 ? (
                    <div className="empty-state">Belum ada data prioritas.</div>
                  ) : priorityDistricts.map(district => {
                    const tone = getRiskTone(district.riskCategory, district.webgisLevel);
                    return (
                      <article key={district.name} className="priority-card">
                        <div className="priority-card-head">
                          <div>
                            <strong>{district.label}</strong>
                            <p>{district.forecastLabel || 'Prediksi aktif'}</p>
                          </div>
                          <span className={`risk-badge ${tone}`.trim()}>{getSemanticRiskLevelLabel(district)}</span>
                        </div>
                        <div className="priority-card-body">
                          <span>{formatPercent(getProbabilityPercentValue(district))} confidence kelas</span>
                          <span>{formatDrainageConfidence(district)} confidence</span>
                        </div>
                        <button
                          className="table-action priority-action"
                          type="button"
                          onClick={() => {
                            setActiveView('predictions');
                            setSelectedDistrictName(district.name);
                            setExpandedDistrictName(district.name);
                          }}
                        >
                          Buka di Tabel
                        </button>
                      </article>
                    );
                  })}
                </div>
              </article>

              <article className="panel admin-insight-panel">
                <div className="panel-heading">
                  <h2>Catatan Model</h2>
                  <p>Panel ini membantu review internal hasil model dan tidak menggantikan keputusan operasional final.</p>
                </div>
                <div className="admin-inline-note admin-inline-note-strong">
                  <p>
                    {payload?.meta?.modelAccuracyNote || payload?.meta?.conversionNote || 'Catatan model sedang dimuat dari payload aktif.'}
                    {!isLiveBackendSource(sourceUrl) ? ' Saat ini admin sedang membaca file JSON cadangan, jadi hasil yang tampil bukan hitungan backend live pada saat ini.' : ''}
                  </p>
                </div>
              </article>
            </section>
          </section>

          <section className={`admin-view ${activeView === 'review' ? 'is-active' : ''}`.trim()} data-admin-view="review">
            <article className="panel admin-view-hero">
              <div>
                <span className="admin-section-kicker">Review Kecamatan</span>
                <h2>Editor override dan publish</h2>
                <p>Fokus utama admin ada di sini: pilih kecamatan, cek ringkasannya, koreksi jika perlu, lalu publish hasil final.</p>
              </div>
            </article>

            <section className="admin-review-layout">
              <article className="admin-editor-card">
                <div className="admin-card-head">
                  <div>
                    <span className="admin-section-kicker">Editor Kecamatan</span>
                    <h2>Intervensi ringan admin</h2>
                    <p>Gunakan panel ini untuk menyesuaikan konteks lapangan tanpa mengubah model inti.</p>
                  </div>
                </div>

                <div className="admin-district-summary">
                  {selectedDistrict
                    ? `${selectedDistrict.label} diprediksi ${selectedDistrict.forecastLabel || 'pada horizon aktif'} dengan level ${getCompactRiskLevelLabel(selectedDistrict).toLowerCase()} dan kondisi drainase ${String(selectedDistrict.drainageCondition || 'tidak tersedia').toLowerCase()}.`
                    : 'Pilih kecamatan untuk melihat ringkasan singkat sebelum menyimpan draft admin.'}
                </div>

                <div className="admin-microgrid">
                  <div className="admin-field-stack">
                    <label className="admin-field-label" htmlFor="adminDistrict">Kecamatan</label>
                    <select
                      id="adminDistrict"
                      className="admin-field-input"
                      value={selectedDistrictName || ''}
                      onChange={event => setSelectedDistrictName(event.target.value)}
                      disabled={busy || districts.length === 0}
                    >
                      {districts.map(district => (
                        <option key={district.name} value={district.name}>{district.label}</option>
                      ))}
                    </select>
                  </div>

                  <div className="admin-field-stack">
                    <label className="admin-field-label" htmlFor="adminDrainageOverride">Override drainase publik</label>
                    <select
                      id="adminDrainageOverride"
                      className="admin-field-input"
                      value={draftOverrideValue}
                      onChange={event => setDraftOverrideValue(event.target.value)}
                      disabled={busy || !selectedDistrictName}
                    >
                      <option value="">Gunakan hasil backend</option>
                      <option value="Baik">Baik</option>
                      <option value="Sedang">Sedang</option>
                      <option value="Buruk">Buruk</option>
                    </select>
                  </div>
                </div>

                <section className="admin-editor-publish">
                  <div className="admin-publish-summary">
                    <div className="admin-publish-box">
                      <span>Snapshot Publik Aktif</span>
                      <strong>{publicationLastPublished ? formatUpdatedAt(publicationLastPublished) : 'Belum pernah'}</strong>
                      <small>{publicStatus.text}</small>
                    </div>
                    <div className="admin-publish-box">
                      <span>Draft Live Admin</span>
                      <strong>{payload?.meta?.updatedAt ? formatUpdatedAt(payload.meta.updatedAt) : 'Belum dimuat'}</strong>
                      <small>{`${Number(payload?.meta?.adminOverrideCount || 0)} override aktif di draft`}</small>
                    </div>
                  </div>

                  <div className="admin-inline-note admin-inline-note-strong">
                    Publish dilakukan setelah admin selesai cek ringkasan kecamatan ini dan memastikan data yang akan tayang di homepage sudah siap dibagikan.
                  </div>

                  <section className="admin-history-block">
                    <div className="admin-history-head">
                      <strong>Riwayat Aktivitas Admin</strong>
                      <p>Aktivitas terbaru saat save, reset, dan publish akan tercatat di sini.</p>
                    </div>
                    <div className="admin-history-list">
                      {history.length === 0 ? (
                        <div className="empty-state">Belum ada riwayat aktivitas admin.</div>
                      ) : history.slice(0, 8).map((entry, index) => {
                        const actionMeta = getHistoryActionMeta(entry);
                        const districtName = formatHistoryDistrictName(entry?.districtName, districts);
                        const description = formatHistoryDescription(entry, districtName);

                        return (
                          <article key={`${entry.timestamp}-${index}`} className="admin-history-item">
                            <div className="admin-history-item-top">
                              <span className={`admin-history-badge ${actionMeta.badgeClass}`.trim()}>{actionMeta.label}</span>
                              <span className="admin-history-item-time">{formatUpdatedAt(entry.timestamp)}</span>
                            </div>
                            <div className="admin-history-item-head">
                              <strong>{actionMeta.title}</strong>
                            </div>
                            {districtName ? <p className="admin-history-item-district">{districtName}</p> : null}
                            <p>{description || 'Detail aktivitas belum tersedia.'}</p>
                          </article>
                        );
                      })}
                    </div>
                  </section>

                  <section className="admin-history-block admin-run-history-block">
                    <div className="admin-history-head">
                      <strong>Riwayat Run Prediksi</strong>
                      <p>Histori snapshot yang sudah masuk ke SQLite dari scheduler atau publish admin.</p>
                    </div>
                    <div className="admin-history-list">
                      {predictionRuns.length === 0 ? (
                        <div className="empty-state">Belum ada histori run prediksi.</div>
                      ) : predictionRuns.map(run => (
                        <article key={`${run.id}-${run.generatedAt}`} className="admin-history-item admin-run-history-item">
                          <div className="admin-history-item-top">
                            <span className="admin-history-badge is-info">{getPredictionRunTypeLabel(run.runType)}</span>
                            <span className="admin-history-item-time">{formatUpdatedAt(run.publishedAt || run.generatedAt)}</span>
                          </div>
                          <div className="admin-history-item-head">
                            <strong>{run.targetPredictionDate ? `Target ${formatDateOnly(run.targetPredictionDate)}` : 'Run prediksi'}</strong>
                          </div>
                          <p>
                            {[
                              run.observationDate ? `Observasi ${formatDateOnly(run.observationDate)}` : '',
                              run.districtCount ? `${run.districtCount} kecamatan` : '',
                              run.sourceLabel || ''
                            ].filter(Boolean).join(' | ')}
                          </p>
                          {Array.isArray(run.topDistricts) && run.topDistricts.length > 0 ? (
                            <div className="admin-run-history-tags">
                              {run.topDistricts.map(district => (
                                <span key={`${run.id}-${district.districtName}`} className="admin-run-history-tag">
                                  {district.districtLabel}: {district.riskLevel || '-'}
                                </span>
                              ))}
                            </div>
                          ) : null}
                        </article>
                      ))}
                    </div>
                  </section>
                </section>

                <div className="admin-editor-actions">
                  <button className="admin-action-button" type="button" onClick={handleSaveOverride} disabled={busy || !selectedDistrictName}>
                    Simpan Draft Admin
                  </button>
                  <button className="admin-action-button admin-action-button-secondary" type="button" onClick={handleResetOverride} disabled={busy || !selectedDistrictName}>
                    Reset Kecamatan Ini
                  </button>
                  <a className="admin-link-button button-secondary" href={publicMapUrl}>Buka Peta Kecamatan</a>
                  <button className="admin-action-button admin-action-button-publish" type="button" onClick={handlePublish} disabled={busy || !payload}>
                    Publish ke Halaman Publik
                  </button>
                </div>
              </article>

              <div className="admin-review-side">
                <article className="panel admin-preview-panel">
                  <div className="panel-heading">
                    <h2>Preview kecamatan terpilih</h2>
                    <p className="admin-preview-active-name">{selectedDistrict ? selectedDistrict.label : 'Pilih kecamatan dari editor di sebelah kiri.'}</p>
                    <p>Semua kartu ini membaca kecamatan yang sedang aktif pada editor di sebelah kiri.</p>
                  </div>

                  <div className="admin-preview-grid">
                    <div className="meta-item">
                      <span>Tanggal Prediksi</span>
                      <strong>{selectedDistrict?.forecastLabel || '-'}</strong>
                    </div>
                    <div className="meta-item">
                      <span>Tingkat Risiko</span>
                      <strong>{selectedDistrict ? getSemanticRiskLevelLabel(selectedDistrict) : '-'}</strong>
                    </div>
                    <div className="meta-item">
                      <span>Curah Hujan</span>
                      <strong>{selectedDistrict ? getRainfallDisplayValue(selectedDistrict) : '-'}</strong>
                    </div>
                    <div className="meta-item">
                      <span>Kelas Hujan</span>
                      <strong>{selectedDistrict?.riskCategory || '-'}</strong>
                    </div>
                    <div className="meta-item">
                      <span>Skor Risiko</span>
                      <strong>{selectedDistrict ? formatScore(selectedDistrict.riskScore) : '-'}</strong>
                    </div>
                    <div className="meta-item">
                      <span>Confidence Kelas</span>
                      <strong>{selectedDistrict ? formatPercent(getProbabilityPercentValue(selectedDistrict)) : '-'}</strong>
                    </div>
                    <div className="meta-item">
                      <span>Kondisi Drainase</span>
                      <strong>{selectedDistrict?.drainageCondition || '-'}</strong>
                    </div>
                    <div className="meta-item">
                      <span>Confidence Drainase</span>
                      <strong>{selectedDistrict ? formatDrainageConfidence(selectedDistrict) : '-'}</strong>
                    </div>
                    <div className="meta-item">
                      <span>Penyesuaian Drainase</span>
                      <strong>{selectedDistrict ? formatSignedPercent(selectedDistrict.drainageAdjustmentPercent) : '-'}</strong>
                    </div>
                    <div className="meta-item">
                      <span>Observasi Terakhir</span>
                      <strong>{selectedDistrict ? formatDateOnly(selectedDistrict.latestObservationDate) : '-'}</strong>
                    </div>
                    <div className="meta-item">
                      <span>Hujan Aktual</span>
                      <strong>{selectedDistrict ? formatMillimeter(selectedDistrict.latestObservedRainfallMm) : '-'}</strong>
                    </div>
                    <div className="meta-item">
                      <span>Rata-Rata 3 Hari</span>
                      <strong>{selectedDistrict ? formatMillimeter(selectedDistrict.recentThreeDayAverageMm) : '-'}</strong>
                    </div>
                  </div>

                  <div className="admin-preview-copy-grid">
                    <div className="admin-preview-copy-card">
                      <span>Ringkasan</span>
                      <p>{selectedDistrict?.summary || '-'}</p>
                    </div>
                    <div className="admin-preview-copy-card">
                      <span>Catatan Drainase</span>
                      <p>{selectedDistrict?.drainageNote || selectedDistrict?.drainageDataSourceName || '-'}</p>
                    </div>
                    <div className="admin-preview-copy-card admin-preview-copy-card-wide">
                      <span>Rekomendasi</span>
                      <p>{selectedDistrict?.recommendation || '-'}</p>
                    </div>
                  </div>
                </article>
              </div>
            </section>
          </section>

          <section className={`admin-view ${activeView === 'predictions' ? 'is-active' : ''}`.trim()} data-admin-view="predictions">
            <article className="panel admin-view-hero">
              <div>
                <span className="admin-section-kicker">Data Prediksi</span>
                <h2>Tabel seluruh kecamatan</h2>
                <p>Buka detail inline untuk melihat ringkasan, rekomendasi, dan catatan drainase tanpa pindah halaman.</p>
              </div>
            </article>

            <section className="panel admin-table-panel" id="predictionTableSection">
              <div className="panel-heading table-heading">
                <div>
                  <h2>Data Prediksi Saat Ini</h2>
                  <p>Klik tombol lihat untuk membuka detail kecamatan langsung di baris tabel ini.</p>
                </div>
              </div>

              <div className="table-wrap">
                <table className="prediction-table">
                  <thead>
                    <tr>
                      <th>Kecamatan</th>
                      <th>Kelas Hujan</th>
                      <th>Drainase</th>
                      <th>Risiko</th>
                      <th>Skor</th>
                      <th>Confidence</th>
                      <th>Aksi</th>
                    </tr>
                  </thead>
                  <tbody>
                    {orderedDistricts.map(district => {
                      const tone = getRiskTone(district.riskCategory, district.webgisLevel);
                      const isExpanded = expandedDistrictName === district.name;

                      return (
                        <Fragment key={district.name}>
                          <tr key={district.name}>
                            <td>
                              <strong>{district.label}</strong>
                              {district.hasAdminDrainageOverride ? <small>Override drainase aktif</small> : null}
                            </td>
                            <td>{getRainfallDisplayValue(district)}</td>
                            <td>{district.drainageCondition || '-'}</td>
                            <td><span className={`risk-badge ${tone}`.trim()}>{getCompactRiskLevelLabel(district)}</span></td>
                            <td>{formatScore(district.riskScore).replace(' / 100', '')}</td>
                            <td>{formatPercent(getProbabilityPercentValue(district))}</td>
                            <td>
                              <button
                                className="table-action"
                                type="button"
                                onClick={() => {
                                  setSelectedDistrictName(district.name);
                                  setExpandedDistrictName(current => current === district.name ? null : district.name);
                                }}
                              >
                                {isExpanded ? 'Tutup' : 'Lihat'}
                              </button>
                            </td>
                          </tr>
                          {isExpanded ? (
                            <tr className="table-detail-row">
                              <td colSpan="7">
                                <div className="table-detail-card">
                                  <div className="table-detail-grid">
                                    <div className="table-detail-item">
                                      <span>Level WebGIS</span>
                                      <strong>{getSemanticRiskLevelLabel(district)}</strong>
                                    </div>
                                    <div className="table-detail-item">
                                      <span>Skor Risiko</span>
                                      <strong>{formatScore(district.riskScore)}</strong>
                                    </div>
                                    <div className="table-detail-item">
                                      <span>Observasi Terakhir</span>
                                      <strong>{formatDateOnly(district.latestObservationDate)}</strong>
                                    </div>
                                    <div className="table-detail-item">
                                      <span>Hujan Aktual</span>
                                      <strong>{formatMillimeter(district.latestObservedRainfallMm)}</strong>
                                    </div>
                                    <div className="table-detail-item">
                                      <span>Rata-Rata 3 Hari</span>
                                      <strong>{formatMillimeter(district.recentThreeDayAverageMm)}</strong>
                                    </div>
                                    <div className="table-detail-item">
                                      <span>Penyesuaian Drainase</span>
                                      <strong>{formatSignedPercent(district.drainageAdjustmentPercent)}</strong>
                                    </div>
                                  </div>
                                  <div className="table-detail-copy">
                                    <div className="table-detail-copy-block">
                                      <span>Ringkasan</span>
                                      <p>{district.summary || '-'}</p>
                                    </div>
                                    <div className="table-detail-copy-block">
                                      <span>Rekomendasi</span>
                                      <p>{district.recommendation || '-'}</p>
                                    </div>
                                    <div className="table-detail-copy-block">
                                      <span>Catatan Drainase</span>
                                      <p>{district.drainageNote || district.drainageDataSourceName || '-'}</p>
                                    </div>
                                  </div>
                                  <div className="table-detail-actions">
                                    <a className="admin-link-button button-secondary" href={buildPublicMapUrl(district.name)}>Buka Peta Kecamatan</a>
                                  </div>
                                </div>
                              </td>
                            </tr>
                          ) : null}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          </section>

          <section className={`admin-view ${activeView === 'backend' ? 'is-active' : ''}`.trim()} data-admin-view="backend">
            <article className="panel admin-view-hero">
              <div>
                <span className="admin-section-kicker">Backend Info</span>
                <h2>Sumber data dan metadata model</h2>
                <p>Admin cukup cek sumber data, model aktif, dan waktu update dari panel ini.</p>
              </div>
            </article>

            <section className="panel admin-help admin-help-footer" id="backendSection">
              <div className="panel-heading">
                <h2>Info Backend</h2>
                <p>Admin cukup cek sumber data, model aktif, dan waktu update dari panel ini.</p>
              </div>

              <div className="backend-meta">
                <div className="meta-item meta-item-hero">
                  <span>Status Sumber</span>
                  <strong>{payload ? draftStatus.text : 'Menunggu data'}</strong>
                </div>
                <div className="meta-item">
                  <span>Status Snapshot Publik</span>
                  <p>{publicationLastPublished ? `${publicStatus.text} - ${formatUpdatedAt(publicationLastPublished)}` : 'Belum pernah dipublish'}</p>
                </div>
                <div className="meta-item">
                  <span>Observasi Terakhir</span>
                  <p>{freshnessInfo?.observationValue ? formatDateOnly(freshnessInfo.observationValue) : '-'}</p>
                </div>
                <div className="meta-item">
                  <span>Target Prediksi</span>
                  <p>{freshnessInfo?.forecastValue ? formatDateOnly(freshnessInfo.forecastValue) : '-'}</p>
                </div>
                <div className="meta-item">
                  <span>Payload Dibuat</span>
                  <p>{freshnessInfo?.generatedValue ? formatUpdatedAt(freshnessInfo.generatedValue) : '-'}</p>
                </div>
                <div className="meta-item">
                  <span>Model Aktif</span>
                  <p>{payload?.meta?.model || '-'}</p>
                </div>
                <div className="meta-item">
                  <span>Sumber Curah Hujan</span>
                  <p>{payload?.meta?.rainfallSource || '-'}</p>
                </div>
                <div className="meta-item">
                  <span>Sumber Drainase</span>
                  <p>{payload?.meta?.drainageSource || '-'}</p>
                </div>
                <div className="meta-item">
                  <span>Horizon Prediksi</span>
                  <p>{payload?.meta?.forecastHorizonDays ? `${payload.meta.forecastHorizonDays} hari` : '-'}</p>
                </div>
                <div className="meta-item">
                  <span>Catatan Akurasi</span>
                  <p>{payload?.meta?.modelAccuracyNote || payload?.meta?.conversionNote || '-'}</p>
                </div>
              </div>
            </section>
          </section>
        </main>
      </div>
    </div>
  );
}
