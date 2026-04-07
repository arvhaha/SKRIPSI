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
// DATA RISIKO
// ==========================
const riskData = {};

function normalizeDistrictName(name) {
  return (name || '').toLowerCase().trim();
}

function getDistrictName(feature) {
  return feature.properties.name || 'Tanpa Nama';
}

function getRiskValueByName(name) {
  return riskData[normalizeDistrictName(name)] || 0;
}

function generateRandomRisk() {
  return Math.floor(Math.random() * 91) + 10;
}

function generateRandomRiskData(data) {
  data.features.forEach(feature => {
    const districtKey = normalizeDistrictName(getDistrictName(feature));

    if (!districtKey || riskData[districtKey]) {
      return;
    }

    riskData[districtKey] = generateRandomRisk();
  });
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
  let kec = getDistrictName(feature);
  let value = getRiskValueByName(kec);

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
  let kec = getDistrictName(feature);
  let value = getRiskValueByName(kec);

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
let heatPointLayer;

function buildHeatmapData(data) {
  const districts = [];

  L.geoJSON(data, {
    onEachFeature: function(feature, layer) {
      const districtName = getDistrictName(feature);
      const districtKey = normalizeDistrictName(districtName);
      const center = typeof layer.getCenter === 'function'
        ? layer.getCenter()
        : layer.getBounds().getCenter();

      if (!districtKey || !center) {
        return;
      }

      districts.push({
        name: districtName,
        key: districtKey,
        center: center,
        risk: getRiskValueByName(districtName)
      });
    }
  });

  return districts;
}

function createHeatPointLayer(districts) {
  return L.layerGroup(
    districts.map(district => L.circleMarker(district.center, {
      radius: 6,
      weight: 1.5,
      color: '#ffffff',
      fillColor: getColor(district.risk),
      fillOpacity: 0.95
    })
      .bindTooltip(district.name, {
        direction: 'top',
        offset: [0, -8],
        opacity: 1,
        className: 'heat-tooltip'
      })
      .bindPopup(`<b>${district.name}</b><br>Risiko acak: ${district.risk}`))
  );
}

fetch('data/jkt.geojson')
  .then(res => res.json())
  .then(data => {
    generateRandomRiskData(data);

    geojson = L.geoJSON(data, {
      style: style,
      onEachFeature: onEachFeature
    }).addTo(map);

    const districts = buildHeatmapData(data);

    heatLayer = L.heatLayer(districts.map(district => [
      district.center.lat,
      district.center.lng,
      district.risk / 100
    ]), {
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
    });

    heatPointLayer = createHeatPointLayer(districts);

    const heatmapOverlay = L.layerGroup([heatLayer, heatPointLayer]).addTo(map);

    L.control.layers(
      {
        'OpenStreetMap': baseMap
      },
      {
        'Risiko per Kecamatan': geojson,
        'Heatmap Risiko + Nama Daerah': heatmapOverlay
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
    Titik heatmap menampilkan nama daerah asli dari GeoJSON. Nilai risiko dibuat acak ulang setiap refresh halaman.
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
