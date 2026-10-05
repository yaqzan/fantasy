import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import { applyTheme, getTheme } from './theme';

applyTheme(getTheme());

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <App />
);
