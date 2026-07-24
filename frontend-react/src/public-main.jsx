import React from 'react';
import { createRoot } from 'react-dom/client';
import 'leaflet/dist/leaflet.css';
import '../../style.css';

import PublicApp from './public/PublicApp';

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <PublicApp />
  </React.StrictMode>
);
