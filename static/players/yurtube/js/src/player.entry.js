import { initAll } from './core.js';

// Entry point: build into static/players/yurtube/js/player.js
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initAll);
} else {
  initAll();
}