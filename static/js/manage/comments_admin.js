(function(){
  if (window.__comments_admin_once) return;
  window.__comments_admin_once = true;

  const root = document.getElementById('manage-comments-root');
  if (!root) return;

  const videoId = root.dataset.videoId || '';
  const ui = { status:null, settingsWrap:null, usersWrap:null, dangerWrap:null };

  function el(tag, cls, text){
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function showStatus(msg, type){
    if (!ui.status) return;
    ui.status.textContent = msg || '';
    ui.status.className = 'mc-status ' + (type||'');
    if (msg) setTimeout(()=>{ ui.status.textContent=''; ui.status.className='mc-status'; }, 1800);
  }
  async function apiGet(url){
    const r = await fetch(url, { credentials:'same-origin' });
    if (!r.ok) throw new Error('GET '+url+' failed');
    return r.json();
  }
  async function apiPost(url, body){
    const r = await fetch(url, {
      method:'POST',
      credentials:'same-origin',
      headers:{ 'Content-Type':'application/json' },
      body: JSON.stringify(body||{})
    });
    if (!r.ok) throw new Error('POST '+url+' failed');
    return r.json();
  }

  function renderSettings(settings){
    ui.settingsWrap.innerHTML = '';

    const cardOnOff = el('div', 'mc-card');
    cardOnOff.appendChild(el('div', 'mc-h', 'Comments status'));
    const row = el('div', 'mc-row');
    const lbl = el('label', 'mc-switch');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = !!settings?.comments_enabled;
    const spanT = el('span', 'mc-switch-lbl', 'Enable comments for this video');
    lbl.appendChild(cb); lbl.appendChild(spanT);
    row.appendChild(lbl);
    cardOnOff.appendChild(row);
    ui.settingsWrap.appendChild(cardOnOff);

    const cardTmb = el('div', 'mc-card');
    cardTmb.appendChild(el('div', 'mc-h', 'Tombstone visibility ("Removed")'));
    cardTmb.appendChild(el(
      'div',
      'mc-desc',
      'Controls who can see the "Removed" placeholder. If hidden, replies are re-attached to the nearest visible parent.'
    ));
    const group = el('div', 'mc-radio-group');

    const cur = settings?.hide_deleted || 'all';

    // Backend values (keep as-is):
    // - all   => hide tombstone for everyone (reparent replies)
    // - owner => show tombstone only to video owner
    // - none  => show tombstone to everyone
    const opts = [
      { val:'all',   label:'Hide for everyone (re-attach replies silently)' },
      { val:'owner', label:'Show only to video owner' },
      { val:'none',  label:'Show to everyone (display "Removed")' }
    ];

    opts.forEach(o=>{
      const label = el('label', 'mc-radio');
      const r = document.createElement('input');
      r.type='radio'; r.name='mc-hide-deleted'; r.value=o.val; r.checked=(o.val===cur);
      const sp = el('span', null, o.label);
      label.appendChild(r); label.appendChild(sp);
      group.appendChild(label);
    });
    cardTmb.appendChild(group);
    ui.settingsWrap.appendChild(cardTmb);

    async function saveSettings(){
      try{
        const hide = (ui.settingsWrap.querySelector('input[name="mc-hide-deleted"]:checked')||{}).value || 'all';
        const enabled = !!cb.checked;
        await apiPost('/api/manage/comments/settings', { video_id: videoId, comments_enabled: enabled, hide_deleted: hide });
        showStatus('Saved', 'ok');
      }catch(e){ console.warn(e); showStatus('Failed', 'err'); }
    }
    cb.addEventListener('change', saveSettings);
    ui.settingsWrap.querySelectorAll('input[name="mc-hide-deleted"]').forEach(radio=>{
      radio.addEventListener('change', saveSettings);
    });
  }

  function renderUsers(users){
    ui.usersWrap.innerHTML = '';
    const card = el('div', 'mc-card');
    card.appendChild(el('div', 'mc-h', 'Commenters'));
    const table = el('table', 'mc-table');
    const thead = el('thead'); const trh = el('tr');
    ['User','Comments','Soft ban','Hard ban','Note','Actions'].forEach(t=> trh.appendChild(el('th', null, t)));
    thead.appendChild(trh); table.appendChild(thead);
    const tbody = el('tbody');

    users.forEach(u=>{
      const tr = el('tr');

      const tdUser = el('td', 'mc-user');
      const av = el('img', 'mc-av'); av.src = u.avatar || '/static/img/avatar_default.svg'; av.alt='';
      const nm = el('span', 'mc-name', u.name || u.uid || 'User');
      tdUser.appendChild(av); tdUser.appendChild(nm);

      const tdCnt = el('td', 'mc-count', String(u.comments_count || 0));

      const tdSoft = el('td', 'mc-check'); const cbSoft = document.createElement('input'); cbSoft.type='checkbox'; cbSoft.checked=!!u.soft_ban; tdSoft.appendChild(cbSoft);
      const tdHard = el('td', 'mc-check'); const cbHard = document.createElement('input'); cbHard.type='checkbox'; cbHard.checked=!!u.hard_ban; tdHard.appendChild(cbHard);

      const tdNote = el('td', 'mc-note');
      const note = document.createElement('input');
      note.type = 'text';
      note.className = 'mc-note-input';
      note.placeholder = 'Optional note';
      note.value = u.note || '';
      tdNote.appendChild(note);

      const tdAct = el('td', 'mc-save');
      const btnSave = el('button', 'mc-btn', 'Save');

      btnSave.addEventListener('click', async ()=>{
        btnSave.disabled = true;
        try{
          await apiPost('/api/manage/comments/ban', {
            video_id: videoId,
            user_uid: u.uid,
            soft_ban: !!cbSoft.checked,
            hard_ban: !!cbHard.checked,
            note: String(note.value || '')
          });
          showStatus('Saved', 'ok');
        }catch(e){ console.warn(e); showStatus('Failed', 'err'); }
        finally{ btnSave.disabled = false; }
      });

      tr.appendChild(tdUser);
      tr.appendChild(tdCnt);
      tr.appendChild(tdSoft);
      tr.appendChild(tdHard);
      tr.appendChild(tdNote);
      tr.appendChild(tdAct);
      tdAct.appendChild(btnSave);

      tbody.appendChild(tr);
    });

    table.appendChild(tbody); card.appendChild(table);
    ui.usersWrap.appendChild(card);
  }

  function renderDanger(){
    ui.dangerWrap.innerHTML = '';

    const card = el('div', 'mc-card');
    card.appendChild(el('div', 'mc-h', 'Danger zone'));
    const desc = el('div', 'mc-desc', 'Delete all comments for this video (irreversible).');
    const btn = el('button', 'mc-btn mc-btn-danger', 'Delete all comments');
    btn.addEventListener('click', async ()=>{
      const ok = window.confirm('This will permanently delete all comments for this video. Continue?');
      if (!ok) return;
      btn.disabled = true;
      try{
        const res = await apiPost('/api/manage/comments/delete-all', { video_id: videoId });
        const d = res?.deleted || {};
        showStatus(`Deleted: root=${d.root_deleted||0}, chunks=${d.chunks_deleted||0}`, 'ok');
      }catch(e){ console.warn(e); showStatus('Delete failed', 'err'); }
      finally{ btn.disabled = false; }
    });
    card.appendChild(desc);
    card.appendChild(btn);
    ui.dangerWrap.appendChild(card);
  }

  async function loadAll(){
    try{
      showStatus('Loading...', 'info');
      const [settingsRes, usersRes] = await Promise.all([
        apiGet(`/api/manage/comments/settings?v=${encodeURIComponent(videoId)}`),
        apiGet(`/api/manage/comments/users?v=${encodeURIComponent(videoId)}`)
      ]);
      renderSettings(settingsRes?.settings || { comments_enabled:true, hide_deleted:'all' });
      renderUsers(usersRes?.users || []);
      renderDanger();
      showStatus('');
    }catch(e){ console.warn(e); showStatus('Load failed', 'err'); }
  }

  root.innerHTML = '';
  const wrap = el('div', 'mc-wrap');
  const title = el('div', 'mc-title', 'Comments admin');
  ui.status = el('div', 'mc-status');
  ui.settingsWrap = el('div', 'mc-section');
  ui.usersWrap = el('div', 'mc-section');
  ui.dangerWrap = el('div', 'mc-section');
  wrap.appendChild(title);
  wrap.appendChild(ui.status);
  wrap.appendChild(ui.settingsWrap);
  wrap.appendChild(ui.usersWrap);
  wrap.appendChild(ui.dangerWrap);
  root.appendChild(wrap);

  loadAll();
})();