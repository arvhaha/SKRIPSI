export function normalizeBaseUrl(value) {
  return String(value ?? '').trim().replace(/\/+$/, '');
}

export function getMetaContent(name) {
  return document.querySelector(`meta[name="${name}"]`)?.getAttribute('content') || '';
}

export function getConfiguredApiBaseUrl() {
  const queryValue = new URLSearchParams(window.location.search).get('apiBaseUrl');
  const globalValue = typeof window.HYDROGIS_API_BASE_URL === 'string'
    ? window.HYDROGIS_API_BASE_URL
    : '';
  const metaValue = getMetaContent('hydrogis-api-base-url');
  const storedValue = window.localStorage?.getItem('hydrogisApiBaseUrl') || '';

  return [queryValue, globalValue, metaValue, storedValue]
    .map(normalizeBaseUrl)
    .find(Boolean) || '';
}

export function getConfiguredPublicBaseUrl() {
  const queryValue = new URLSearchParams(window.location.search).get('publicBaseUrl');
  const globalValue = typeof window.HYDROGIS_PUBLIC_BASE_URL === 'string'
    ? window.HYDROGIS_PUBLIC_BASE_URL
    : '';
  const metaValue = getMetaContent('hydrogis-public-base-url');
  const storedValue = window.localStorage?.getItem('hydrogisPublicBaseUrl') || '';

  return [queryValue, globalValue, metaValue, storedValue]
    .map(normalizeBaseUrl)
    .find(Boolean) || '';
}

export function buildPredictionEndpoints() {
  const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
  const hostName = window.location.hostname || '127.0.0.1';
  const configuredApiBaseUrl = getConfiguredApiBaseUrl();
  const liveCandidates = [];

  if (configuredApiBaseUrl) {
    liveCandidates.push(`${configuredApiBaseUrl}/api/predictions`);
  } else {
    liveCandidates.push('/api/predictions');
  }

  if (hostName === 'localhost' || hostName === '127.0.0.1') {
    liveCandidates.push(`${protocol}//${hostName}:8011/api/predictions`);
    
    if (hostName !== 'localhost') {
      liveCandidates.push(`${protocol}//localhost:8011/api/predictions`);
    }

    if (hostName !== '127.0.0.1') {
      liveCandidates.push(`${protocol}//127.0.0.1:8011/api/predictions`);
    }

    liveCandidates.push(`${protocol}//${hostName}:8000/api/predictions`);

    if (hostName !== 'localhost') {
      liveCandidates.push(`${protocol}//localhost:8000/api/predictions`);
    }

    if (hostName !== '127.0.0.1') {
      liveCandidates.push(`${protocol}//127.0.0.1:8000/api/predictions`);
    }
  }

  return [...new Set(liveCandidates)];
}

export function buildGeoJsonEndpoints() {
  const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
  const hostName = window.location.hostname || '127.0.0.1';
  const configuredApiBaseUrl = getConfiguredApiBaseUrl();
  const candidates = [];

  if (configuredApiBaseUrl) {
    candidates.push(`${configuredApiBaseUrl}/api/geojson`);
  } else {
    candidates.push('/api/geojson');
  }

  if (hostName === 'localhost' || hostName === '127.0.0.1') {
    candidates.push(`${protocol}//${hostName}:8011/api/geojson`);

    if (hostName !== 'localhost') {
      candidates.push(`${protocol}//localhost:8011/api/geojson`);
    }

    if (hostName !== '127.0.0.1') {
      candidates.push(`${protocol}//127.0.0.1:8011/api/geojson`);
    }

    candidates.push(`${protocol}//${hostName}:8000/api/geojson`);

    if (hostName !== 'localhost') {
      candidates.push(`${protocol}//localhost:8000/api/geojson`);
    }

    if (hostName !== '127.0.0.1') {
      candidates.push(`${protocol}//127.0.0.1:8000/api/geojson`);
    }
  }

  candidates.push('data/jkt.geojson');
  return [...new Set(candidates)];
}

export function buildAdminPreviewEndpoints() {
  const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
  const hostName = window.location.hostname || '127.0.0.1';
  const configuredApiBaseUrl = getConfiguredApiBaseUrl();
  const candidates = [];

  if (configuredApiBaseUrl) {
    candidates.push(`${configuredApiBaseUrl}/api/admin/predictions/live`);
  } else {
    candidates.push('/api/admin/predictions/live');
  }

  if (hostName === 'localhost' || hostName === '127.0.0.1') {
    candidates.push(`${protocol}//${hostName}:8011/api/admin/predictions/live`);

    if (hostName !== 'localhost') {
      candidates.push(`${protocol}//localhost:8011/api/admin/predictions/live`);
    }

    if (hostName !== '127.0.0.1') {
      candidates.push(`${protocol}//127.0.0.1:8011/api/admin/predictions/live`);
    }

    candidates.push(`${protocol}//${hostName}:8000/api/admin/predictions/live`);

    if (hostName !== 'localhost') {
      candidates.push(`${protocol}//localhost:8000/api/admin/predictions/live`);
    }

    if (hostName !== '127.0.0.1') {
      candidates.push(`${protocol}//127.0.0.1:8000/api/admin/predictions/live`);
    }
  }

  return [...new Set(candidates)];
}

export function buildAdminPredictionRunHistoryUrl(limit = 8) {
  const normalizedLimit = Math.max(1, Math.min(Number(limit) || 8, 50));
  return buildApiUrl(`api/admin/prediction-runs?limit=${normalizedLimit}`);
}

export function buildApiUrl(path) {
  const configuredApiBaseUrl = getConfiguredApiBaseUrl();
  const normalizedPath = String(path || '').replace(/^\/+/, '');
  return configuredApiBaseUrl
    ? `${configuredApiBaseUrl}/${normalizedPath}`
    : normalizedPath;
}

export function fetchJson(url, options = {}) {
  return fetch(url, options).then(async response => {
    if (!response.ok) {
      const responseText = await response.text().catch(() => '');
      throw new Error(responseText || `Gagal memuat ${url} (${response.status})`);
    }

    return response.json();
  });
}

export async function fetchFirstAvailable(candidates, fallbackErrorMessage) {
  let lastError = null;

  for (const candidate of candidates) {
    try {
      if (typeof candidate.load === 'function') {
        const payload = await candidate.load();
        return {
          payload,
          sourceUrl: candidate.sourceUrl || candidate.label || 'inline-fallback'
        };
      }

      const payload = await fetchJson(candidate.url, candidate.options);
      return {
        payload,
        sourceUrl: candidate.url
      };
    } catch (error) {
      lastError = error;
      console.warn(`Sumber data ${candidate.url || candidate.label || 'fallback'} gagal dimuat.`, error);
    }
  }

  throw lastError || new Error(fallbackErrorMessage || 'Tidak ada sumber data yang berhasil dimuat.');
}

export function postJson(url, payload) {
  return fetchJson(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });
}
