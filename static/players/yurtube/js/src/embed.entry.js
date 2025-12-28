import { initEmbed } from './embed.core.js';

// Entry point for embed player, built into static/players/yurtube/js/embed.js
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initEmbed);
} else {
  initEmbed();
}