import { initEmbed } from './embed.core.js';

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initEmbed);
} else {
  initEmbed();
}