import React from 'react';
import { createRoot } from 'react-dom/client';
import '../../style.css';

import AdminApp from './admin/AdminApp';

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <AdminApp />
  </React.StrictMode>
);
