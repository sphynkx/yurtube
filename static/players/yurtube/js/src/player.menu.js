/**
 * Menu module - manages settings menu UI and navigation
 */

/**
 * Style a button to be transparent
 */
export function ensureTransparentMenuButton(btn) {
  try {
    btn.style.background = 'transparent';
    btn.style.backgroundColor = 'transparent';
    btn.style.border = 'none';
    btn.style.boxShadow = 'none';
    btn.style.color = 'inherit';
    btn.style.textAlign = 'left';
    btn.style.width = '100%';
    btn.style.display = 'block';
  } catch {}
}

/**
 * Style a back button with background
 */
export function styleBackButton(btn) {
  ensureTransparentMenuButton(btn);
  try {
    btn.style.background = 'rgba(255,255,255,0.12)';
    btn.style.backgroundColor = 'rgba(255,255,255,0.12)';
    btn.style.borderRadius = '4px';
    btn.style.fontWeight = '700';
    btn.style.marginBottom = '6px';
    btn.style.paddingLeft = '8px';
    btn.style.paddingRight = '8px';
  } catch {}
}

/**
 * Add submenu chevron indicator to button
 */
export function withSubmenuChevron(btn) {
  try { btn.classList.add('has-submenu'); } catch {}
}

/**
 * Build a scrollable container for menu lists
 * @param {HTMLElement} backBtn - The back button element (optional, used for height calculation)
 * @param {HTMLElement} menu - The menu element (optional, used to get player context)
 */
export function buildScrollableListContainer(backBtn, menu) {
  const wrap = document.createElement('div');
  wrap.className = 'yrp-menu-scroll';
  
  // Calculate max height: leave room for back button (40px) and menu padding
  let maxHeight = 'calc(100% - 40px)';
  
  // If we have menu context, try to limit to 2/3 of player height
  if (menu) {
    try {
      const playerContainer = menu.closest('.yrp-container');
      if (playerContainer) {
        const videoWrap = playerContainer.querySelector('.yrp-video-wrap');
        if (videoWrap) {
          const playerHeight = videoWrap.getBoundingClientRect().height;
          // 2/3 of player height minus controls (34px) minus back button (40px) minus padding (12px)
          const maxScrollHeight = Math.floor(playerHeight * 2 / 3) - 34 - 40 - 12;
          if (maxScrollHeight > 100) {
            maxHeight = maxScrollHeight + 'px';
          }
        }
      }
    } catch {}
  }
  
  Object.assign(wrap.style, {
    overflowY: 'auto',
    overflowX: 'hidden',
    maxHeight: maxHeight,
    paddingRight: '2px'
  });
  return wrap;
}

/**
 * Normalize quality section typography (remove old title, add placeholder)
 */
export function normalizeQualitySectionTypography(menu, ensureTransparentMenuButton) {
  if (!menu) return;
  try {
    const secQ = menu.querySelector('.yrp-menu-section[data-section="quality"]');
    if (!secQ) return;

    const oldTitle = secQ.querySelector('.yrp-menu-title');
    if (oldTitle) oldTitle.parentNode && oldTitle.parentNode.removeChild(oldTitle);

    if (secQ.querySelector('.yrp-menu-item.quality-future')) return;

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'yrp-menu-item quality-future';
    btn.textContent = 'Quality (future)';
    btn.disabled = true;
    ensureTransparentMenuButton(btn);
    btn.style.opacity = '0.75';
    secQ.appendChild(btn);
  } catch {}
}

/**
 * Remove future subtitles section from menu (cleanup legacy markup)
 */
export function removeFutureSubtitlesSection(menu) {
  if (!menu) return;
  try {
    const sec = menu.querySelector('.yrp-menu-section[data-section="subtitles"]');
    if (sec && sec.parentNode) sec.parentNode.removeChild(sec);
  } catch {}
}

/**
 * Insert a menu entry into the main menu view
 */
export function insertMainEntry(menu, label, action, extra, ensureTransparentMenuButton, withSubmenuChevron) {
  if (!menu) return null;

  const firstSection = menu.querySelector('.yrp-menu-section') || null;

  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'yrp-menu-item';
  btn.setAttribute('data-action', action);
  btn.textContent = label;

  ensureTransparentMenuButton(btn);

  if (extra && extra.disabled === true) {
    btn.disabled = true;
    btn.style.opacity = '0.6';
  }

  if (extra && extra.hasSubmenu === true) {
    withSubmenuChevron(btn);
  }

  if (firstSection && firstSection.parentNode === menu) menu.insertBefore(btn, firstSection);
  else menu.appendChild(btn);
  return btn;
}

/**
 * Get available playback speed options
 */
export function speedOptions() {
  return [0.5, 0.75, 1, 1.25, 1.5, 2];
}

/**
 * Build the speed submenu view
 */
export function buildSpeedMenuView(menu, video, styleBackButton, ensureTransparentMenuButton) {
  if (!menu) return;

  while (menu.firstChild) menu.removeChild(menu.firstChild);

  const back = document.createElement('button');
  back.type = 'button';
  back.className = 'yrp-menu-item';
  back.setAttribute('data-action', 'back');
  back.textContent = '← Back';
  styleBackButton(back);
  menu.appendChild(back);

  const cur = isFinite(video.playbackRate) ? video.playbackRate : 1;

  speedOptions().forEach(function (s) {
    const it = document.createElement('button');
    it.type = 'button';
    it.className = 'yrp-menu-item';
    it.setAttribute('data-action', 'set-speed');
    it.setAttribute('data-speed', String(s));
    it.textContent = (s === 1 ? '1.0x' : (String(s) + 'x')) + (Math.abs(s - cur) < 0.001 ? ' ✓' : '');
    ensureTransparentMenuButton(it);
    menu.appendChild(it);
  });
}

/**
 * Apply playback speed to video
 */
export function applySpeed(video, sp) {
  const s = parseFloat(String(sp));
  if (!isFinite(s) || s <= 0) return;
  video.playbackRate = s;
  try { localStorage.setItem('playback_speed', String(s)); } catch {}
}

/**
 * Menu state manager - encapsulates menu state and operations
 */
export class MenuManager {
  constructor(menu) {
    this.menu = menu;
    this.menuView = 'main';
    this.menuMainHTML = '';
    this.menuFixedMinHeight = 0;
  }

  ensureMainSnapshot() {
    if (!this.menu) return;
    if (!this.menuMainHTML) this.menuMainHTML = this.menu.innerHTML || '';
  }

  lockHeightFromCurrent() {
    if (!this.menu) return;
    if (this.menuFixedMinHeight > 0) return;
    try {
      const r = this.menu.getBoundingClientRect();
      this.menuFixedMinHeight = Math.ceil(r.height || 0);
      if (this.menuFixedMinHeight > 0) this.menu.style.minHeight = this.menuFixedMinHeight + 'px';
    } catch {}
  }

  resetHeightLock() {
    if (!this.menu) return;
    this.menuFixedMinHeight = 0;
    this.menu.style.minHeight = '';
  }

  setView(view) {
    this.menuView = view;
  }

  getView() {
    return this.menuView;
  }

  openMainView(callbacks) {
    if (!this.menu) return;
    this.ensureMainSnapshot();
    this.menu.innerHTML = this.menuMainHTML;
    this.menuView = 'main';
    
    // Reset any height constraints when opening main view
    this.menu.style.maxHeight = '';

    try {
      const secSpeed = this.menu.querySelector('.yrp-menu-section[data-section="speed"]');
      if (secSpeed && secSpeed.parentNode) secSpeed.parentNode.removeChild(secSpeed);
    } catch {}

    removeFutureSubtitlesSection(this.menu);
    normalizeQualitySectionTypography(this.menu, ensureTransparentMenuButton);

    if (callbacks) {
      callbacks.injectSpeed && callbacks.injectSpeed();
      callbacks.injectLanguages && callbacks.injectLanguages();
      callbacks.injectSubtitles && callbacks.injectSubtitles();
    }
  }

  /**
   * Constrain menu height to a fraction of player height
   * @param {number} fraction - Fraction of player height (default 2/3)
   */
  constrainToPlayerHeight(fraction = 2/3) {
    if (!this.menu) return;
    try {
      const playerContainer = this.menu.closest('.yrp-container');
      if (playerContainer) {
        const videoWrap = playerContainer.querySelector('.yrp-video-wrap');
        if (videoWrap) {
          const playerHeight = videoWrap.getBoundingClientRect().height;
          // Account for controls height (34px) and some padding
          const maxMenuHeight = Math.floor(playerHeight * fraction) - 34;
          if (maxMenuHeight > 100) {
            this.menu.style.maxHeight = maxMenuHeight + 'px';
            this.menu.style.overflowY = 'hidden'; // The scroll is in the container inside
          }
        }
      }
    } catch {}
  }
}
