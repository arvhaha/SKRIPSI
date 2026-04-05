// ==========================
// INIT MAP
// ==========================
var map = L.map('map').setView([-6.21, 106.9], 11);

// ==========================
// BASEMAP
// ==========================
const baseMap = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

// ==========================
// DATA RISIKO (dummy dulu)
// ==========================
const riskData = {
  "cakung": 85,
  "jatinegara": 40,
  "duren sawit": 60,
  "kramat jati": 30,
  "pasar rebo": 20,
  "ciracas": 50,
  "cipayung": 35,
  "makasar": 45,
  "matraman": 70,
  "pulo gadung": 80
};

function normalizeDistrictName(name) {
  return (name || '').toLowerCase().trim();
}

// ==========================
// FUNCTION WARNA
// ==========================
function getColor(value) {
  return value > 80 ? '#800026' :
         value > 60 ? '#BD0026' :
         value > 40 ? '#E31A1C' :
         value > 20 ? '#FC4E2A' :
         value > 10 ? '#FD8D3C' :
                      '#FED976';
}

// ==========================
// STYLE POLYGON
// ==========================
function style(feature) {
  let kec = normalizeDistrictName(feature.properties.WADMKC);
  let value = riskData[kec] || 0;

  return {
    fillColor: getColor(value),
    weight: 1,
    color: 'white',
    fillOpacity: 0.7
  };
}

// ==========================
// INTERAKSI (HOVER)
// ==========================
function highlightFeature(e) {
  var layer = e.target;

  layer.setStyle({
    weight: 3,
    color: '#666',
    fillOpacity: 0.9
  });

  if (!L.Browser.ie && !L.Browser.opera && !L.Browser.edge) {
    layer.bringToFront();
  }
}

function resetHighlight(e) {
  geojson.resetStyle(e.target);
}

// ==========================
// SETIAP FEATURE
// ==========================
function onEachFeature(feature, layer) {
  let kec = feature.properties.WADMKC;
  let value = riskData[normalizeDistrictName(kec)] || 0;

  layer.on({
    mouseover: highlightFeature,
    mouseout: resetHighlight
  });

  layer.bindPopup(
    `<b>${kec}</b><br>Risiko: ${value}`
  );
}

// ==========================
// LOAD GEOJSON
// ==========================
let geojson;
let heatLayer;

function buildHeatmapPoints(data) {
  const districtBounds = new Map();

  L.geoJSON(data, {
    onEachFeature: function(feature, layer) {
      const districtKey = normalizeDistrictName(feature.properties.WADMKC);
      const bounds = layer.getBounds();

      if (!districtKey || !bounds.isValid()) {
        return;
      }

      if (!districtBounds.has(districtKey)) {
        districtBounds.set(districtKey, L.latLngBounds(bounds.getSouthWest(), bounds.getNorthEast()));
        return;
      }

      districtBounds.get(districtKey).extend(bounds);
    }
  });

  return Array.from(districtBounds.entries())
    .map(([districtKey, bounds]) => {
      const center = bounds.getCenter();
      const riskValue = riskData[districtKey] || 0;

      return [center.lat, center.lng, riskValue / 100];
    })
    .filter(point => point[2] > 0);
}

fetch('data/jkt.geojson')
  .then(res => res.json())
  .then(data => {
    geojson = L.geoJSON(data, {
      style: style,
      onEachFeature: onEachFeature
    }).addTo(map);

    heatLayer = L.heatLayer(buildHeatmapPoints(data), {
      radius: 38,
      blur: 28,
      maxZoom: 13,
      minOpacity: 0.45,
      gradient: {
        0.2: '#fed976',
        0.4: '#fd8d3c',
        0.6: '#fc4e2a',
        0.8: '#bd0026',
        1.0: '#800026'
      }
    }).addTo(map);

    L.control.layers(
      {
        'OpenStreetMap': baseMap
      },
      {
        'Risiko per Kecamatan': geojson,
        'Heatmap Risiko': heatLayer
      },
      {
        collapsed: false
      }
    ).addTo(map);

    map.fitBounds(geojson.getBounds(), { padding: [20, 20] });
  })
  .catch(error => {
    console.error('Gagal memuat data GeoJSON:', error);
  });

// ==========================
// INFO HEATMAP
// ==========================
var mapInfo = L.control({position: 'topright'});

mapInfo.onAdd = function () {
  var div = L.DomUtil.create('div', 'map-info');
  div.innerHTML = `
    <strong>Heatmap Risiko</strong>
    Semakin pekat warna merah, semakin tinggi konsentrasi wilayah dengan nilai risiko banjir.
  `;

  L.DomEvent.disableClickPropagation(div);

  return div;
};

mapInfo.addTo(map);

// ==========================
// LEGEND
// ==========================
var legend = L.control({position: 'bottomright'});

legend.onAdd = function () {
  var div = L.DomUtil.create('div', 'legend'),
      grades = [0, 10, 20, 40, 60, 80];

  div.innerHTML = '<strong>Skala Risiko</strong>';

  for (var i = 0; i < grades.length; i++) {
    div.innerHTML +=
      '<i style="background:' + getColor(grades[i] + 1) + '"></i> ' +
      grades[i] + (grades[i + 1] ? '&ndash;' + grades[i + 1] + '<br>' : '+');
  }

  L.DomEvent.disableClickPropagation(div);

  return div;
};

legend.addTo(map);
