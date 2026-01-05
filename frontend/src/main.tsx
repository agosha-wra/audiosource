import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles.css'

// Load saved accent color on startup
const savedAccentColor = localStorage.getItem('accentColor');
const savedHoverColor = localStorage.getItem('accentHoverColor');

if (savedAccentColor) {
  document.documentElement.style.setProperty('--accent', savedAccentColor);
  document.documentElement.style.setProperty('--accent-glow', `${savedAccentColor}26`);
}
if (savedHoverColor) {
  document.documentElement.style.setProperty('--accent-hover', savedHoverColor);
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)

