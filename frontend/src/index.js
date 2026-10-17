import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import { PlayerCardProvider } from './components/PlayerCard';
import { applyTheme, getTheme } from './theme';

applyTheme(getTheme());

const root = ReactDOM.createRoot(document.getElementById('root'));
// The provider sits outside App: opening a player card never re-renders the app or its boards.
root.render(
  <PlayerCardProvider>
    <App />
  </PlayerCardProvider>
);
