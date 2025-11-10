/* Unified player UI script (ru) */

document.addEventListener('DOMContentLoaded', function () {
  const appCfg = (window.AppConfig || {});
  // Elements
  const mainPanel = document.getElementById('main-panel');
  const dropLayer = document.getElementById('drop-layer');
  const videoLayer = document.getElementById('video-layer');
  const closeButton = document.getElementById('close-video');

  const videoElement = document.getElementById('video-player');
  try {
    // Improve autoplay behavior on mobile browsers
    if (videoElement) {
      videoElement.setAttribute('playsinline', '');
      videoElement.playsInline = true;
      videoElement.autoplay = true;
    }
  } catch {}
  const playPauseButton = document.getElementById('play-pause');
  const progressBar = document.getElementById('progress');
  const volumeSlider = document.getElementById('volume');
  const speedSelect = document.getElementById('speed');
  const timeDisplay = document.getElementById('time-display');
  const controls = document.getElementById('controls');
  const videoList = document.getElementById('video-list');
  const instructions = document.getElementById('upload-instructions');
  const videoFilter = document.getElementById('video-filter');
  const fileInput = document.getElementById('file-input');
  const fileSelectTrigger = document.getElementById('file-select-trigger');
  const subtitlePanel = document.getElementById('subtitle-panel');
  const subtitleList = document.getElementById('subtitle-list');
  const processingOverlay = document.getElementById('processing-overlay');

  const tabs = document.querySelectorAll('.tab-btn');
  // Collect available panels; in single-video mode, the log panel is absent
  const panels = {
    chat: document.getElementById('panel-chat'),
    about: document.getElementById('panel-about'),
    log: document.getElementById('panel-log')
  };
  const chatMessages = document.getElementById('chat-messages');
  const chatInput = document.getElementById('chat-input');
  const chatSend = document.getElementById('chat-send');
  let chatSuggestions = document.getElementById('chat-suggestions');
  // Ensure suggestions container exists just below the input row
  (function ensureSuggestionsContainer(){
    try {
      if (!chatSuggestions) {
        const inputRow = document.querySelector('.chat-input-row');
        const cont = document.createElement('div');
        cont.id = 'chat-suggestions';
        cont.className = 'chat-suggestions';
        if (inputRow && inputRow.parentNode) {
          inputRow.parentNode.insertBefore(cont, inputRow.nextSibling);
          chatSuggestions = cont;
        }
      }
    } catch {}
  })();
  const btnClearLog = document.getElementById('log-clear');

  const explainTooltip = document.getElementById('explain-tooltip');
  const explainBtn = document.getElementById('explain-btn');
  // Inline unmute control (appears only if autoplay had to be muted)
  const unmuteBtn = (function(){
    try {
      const btn = document.createElement('button');
      btn.id = 'unmute-btn';
      btn.type = 'button';
      btn.textContent = 'Включить звук';
      btn.style.position = 'absolute';
      btn.style.right = '12px';
      btn.style.top = '12px';
      btn.style.zIndex = '20';
      btn.style.padding = '8px 10px';
      btn.style.borderRadius = '8px';
      btn.style.border = '1px solid rgba(0,0,0,0.2)';
      btn.style.background = 'rgba(255,255,255,0.92)';
      btn.style.color = '#111';
      btn.style.fontSize = '13px';
      btn.style.cursor = 'pointer';
      btn.style.boxShadow = '0 2px 6px rgba(0,0,0,0.12)';
      btn.style.display = 'none';
      if (videoLayer) videoLayer.appendChild(btn);
      return btn;
    } catch { return null; }
  })();

  // State
  let currentSubtitles = [];
  let currentVideoName = null;
  let dialog = [];
  let lastClickRel = { x: 0.5, y: 0.5 };
  let lastPopoverEl = null;
  let isBusy = false;
  let pendingUnmute = false;
  // Start overlay for single-link open (manual start with sound)
  let startOverlay = null;
  function ensureStartOverlay(){
    try {
      if (startOverlay || !videoLayer) return null;
      const ov = document.createElement('button');
      ov.id = 'start-overlay';
      ov.type = 'button';
      ov.textContent = 'начать просмотр';
      ov.style.position = 'absolute';
      ov.style.left = '50%';
      ov.style.top = '50%';
      ov.style.transform = 'translate(-50%, -50%)';
      ov.style.padding = '12px 18px';
      ov.style.borderRadius = '12px';
      ov.style.border = '1px solid rgba(255,255,255,0.35)';
      ov.style.background = 'rgba(1,1,1,0.1)';
      ov.style.color = '#fff';
      ov.style.fontSize = '16px';
      ov.style.fontWeight = '600';
      ov.style.letterSpacing = '0.3px';
      ov.style.backdropFilter = 'blur(6px)';
      ov.style.cursor = 'pointer';
      ov.style.zIndex = '25';
      ov.style.userSelect = 'none';
      ov.style.display = 'none';
      videoLayer.appendChild(ov);
      startOverlay = ov;
      ov.addEventListener('click', (e)=>{
        e.stopPropagation();
        try { if (startOverlay) startOverlay.style.display='none'; } catch{}
        // explicit start with sound
        try { videoElement.muted = false; } catch{}
        try {
          const v = parseFloat((volumeSlider && volumeSlider.value) || '1');
          if (!Number.isNaN(v)) videoElement.volume = Math.max(0, Math.min(1, v));
        } catch{}
        videoElement.play().catch(()=>{});
      });
      return ov;
    } catch { return null; }
  }

  const defaultInstructions = 'Перетащите видео сюда или выберите из списка ниже';

  // Fetch/Render videos
  async function fetchVideos() {
    try {
      const r = await fetch('/videos');
      if (!r.ok) throw new Error('Не удалось получить список видео');
      renderVideoList(await r.json());
    } catch (e) { console.error(e); }
  }

  function renderVideoList(videos) {
    while (videoList.firstChild) videoList.removeChild(videoList.firstChild);
    if (!videos.length) {
      const li = document.createElement('li');
      li.style.fontStyle = 'italic'; li.style.color = '#999';
      li.textContent = 'Еще нет загруженных видео';
      videoList.appendChild(li); return;
    }
    videos.forEach(vid => {
      const li = document.createElement('li');
      li.className = 'video-item';
      li.dataset.url = vid.url;
      const name = document.createElement('span'); name.className = 'name'; name.textContent = vid.name;
      const del = document.createElement('button'); del.className = 'delete-video'; del.title = 'Удалить'; del.textContent = '×';
      del.addEventListener('click', async (e)=>{
        e.stopPropagation();
        try { const resp = await fetch(`/video/${encodeURIComponent(vid.name)}`, { method: 'DELETE' }); if (!resp.ok) throw new Error('Не удалось удалить файл'); if (currentVideoName === vid.name) closeVideo(); fetchVideos(); } catch (err) { alert(err.message || 'Ошибка удаления'); }
      });
      li.appendChild(name); li.appendChild(del);
      li.addEventListener('click', ()=> loadVideo(vid.url, vid.name));
      videoList.appendChild(li);
    });
  }

  // Player helpers
  function formatTime(secs) { const s = Math.floor(secs % 60).toString().padStart(2,'0'); const m = Math.floor((secs/60)%60).toString().padStart(2,'0'); const h = Math.floor(secs/3600); return h>0?`${h}:${m}:${s}`:`${m}:${s}`; }
  function updateProgress(){ if(!videoElement.duration) return; progressBar.max = videoElement.duration; progressBar.value = videoElement.currentTime; timeDisplay.textContent = `${formatTime(videoElement.currentTime)} / ${formatTime(videoElement.duration)}`; }

  // Suggestions state
  let allSuggestions = [];
  let lastRenderedKeys = new Set();
  function parseHHMMSS(s){ if(!s) return NaN; const m = String(s).trim().match(/^(\d{1,2}):(\d{2}):(\d{2})$/); if(!m) return NaN; return (+m[1])*3600 + (+m[2])*60 + (+m[3]); }
  async function loadSuggestions(){ allSuggestions = []; lastRenderedKeys.clear(); if(!currentVideoName) { renderSuggestions([]); return; } try { const r = await fetch(`/suggestions/${encodeURIComponent(currentVideoName)}`); if(!r.ok) { renderSuggestions([]); return; } const d = await r.json(); const items = Array.isArray(d?.items) ? d.items : []; allSuggestions = items.map((it,idx)=>({ key: `${idx}-${it.start}-${it.end}`, text: String(it.text||'').trim(), start: String(it.start||'').trim(), end: String(it.end||'').trim(), startSec: parseHHMMSS(it.start), endSec: parseHHMMSS(it.end) })).filter(it=> it.text && Number.isFinite(it.startSec) && Number.isFinite(it.endSec) && it.endSec>it.startSec); updateSuggestionsForTime(); } catch { renderSuggestions([]); } }
  function renderSuggestions(list){ if(!chatSuggestions) return; // fade out old
    try { Array.from(chatSuggestions.children).forEach(ch=>{ ch.classList.add('hiding'); setTimeout(()=>{ if(ch&&ch.parentNode) ch.parentNode.removeChild(ch); }, 180); }); } catch{}
    // add new
    list.forEach(item=>{ const btn=document.createElement('button'); btn.type='button'; btn.className='suggestion-btn'; btn.textContent=item.text; btn.addEventListener('click', ()=>{ sendChat(item.text); }); chatSuggestions.appendChild(btn); requestAnimationFrame(()=>{ btn.classList.add('visible'); }); });
  }
  function updateSuggestionsForTime(){ if(!chatSuggestions) return; const t = videoElement?.currentTime||0; const active = allSuggestions.filter(it => t >= it.startSec && t <= it.endSec).slice(0, 6); const keys = new Set(active.map(a=>a.key)); // avoid unnecessary re-render
    let changed=false; if (keys.size !== lastRenderedKeys.size) { changed=true; } else { for(const k of keys){ if(!lastRenderedKeys.has(k)) { changed=true; break; } } }
    if(!changed) return; lastRenderedKeys = keys; renderSuggestions(active); }

  async function ensureProcessed(name){
    try {
      await fetch('/api/ensure_processed', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ name }) });
    } catch {}
  }
  function pollSubtitlesUntil(name, maxAttempts=12, delayMs=5000){
    let attempts=0;
    const tick = async ()=>{
      attempts++;
      try {
        const subs = await fetchSubtitlesFor(name);
        if (Array.isArray(subs) && subs.length){
          currentSubtitles = subs;
          renderSubtitles(currentSubtitles);
          if (subtitlePanel) subtitlePanel.style.display = 'block';
          return;
        }
      } catch {}
      if (attempts < maxAttempts) setTimeout(tick, delayMs);
    };
    setTimeout(tick, delayMs);
  }
  function loadVideo(url, name, auto=false){
    videoElement.pause(); videoElement.removeAttribute('src'); videoElement.load();
    dropLayer.style.display = 'none'; videoLayer.style.display = 'block'; controls.style.display = 'flex';
    instructions.textContent = name || defaultInstructions; currentVideoName = name || null;
    videoElement.src = url; videoElement.load();
    try {
      const v = parseFloat((volumeSlider && volumeSlider.value) || '1'); if (!Number.isNaN(v)) videoElement.volume = Math.max(0, Math.min(1, v));
      const r = parseFloat((speedSelect && speedSelect.value) || '1'); if (!Number.isNaN(r)) videoElement.playbackRate = r;
    } catch {}
    // Try to autoplay; if blocked by policy, retry muted when auto=true
    if (auto) {
      (async ()=>{
        try {
          videoElement.muted = false;
          await videoElement.play();
          // success with sound, ensure UI reflects unmuted
          pendingUnmute = false;
          if (unmuteBtn) unmuteBtn.style.display = 'none';
        } catch (e) {
          try {
            // Fallback to muted autoplay, then wait for first user interaction to unmute
            videoElement.muted = true;
            await videoElement.play();
            pendingUnmute = true;
            if (unmuteBtn) unmuteBtn.style.display = 'inline-block';
            attachOneShotUnmuteHandlers();
          } catch {}
        }
      })();
    }
    if (subtitlePanel) {
      fetchSubtitlesFor(name)
        .then(async (subs)=>{
          currentSubtitles = subs||[];
          renderSubtitles(currentSubtitles);
          subtitlePanel.style.display = currentSubtitles.length?'block':'none';
          if (!currentSubtitles.length){ await ensureProcessed(name); pollSubtitlesUntil(name); }
        })
        .catch(async ()=>{
          currentSubtitles=[]; renderSubtitles(currentSubtitles); subtitlePanel.style.display='none';
          await ensureProcessed(name); pollSubtitlesUntil(name);
        });
    }
    // reset chat
    dialog = []; if (chatMessages) chatMessages.textContent = '';
    // reset suggestions and load
    renderSuggestions([]);
    loadSuggestions();
  }

  async function closeVideo(){
    const nameToClear = currentVideoName;
    videoElement.pause(); videoElement.removeAttribute('src'); videoElement.load();
    controls.style.display = 'none'; videoLayer.style.display = 'none'; dropLayer.style.display = 'flex';
    if (playPauseButton) playPauseButton.textContent = '\u25B6'; // ▶
    instructions.textContent = defaultInstructions; progressBar.value = 0; timeDisplay.textContent = '0:00 / 0:00';
    currentSubtitles = []; if (subtitlePanel) { renderSubtitles(currentSubtitles); subtitlePanel.style.display='none'; }
    try { if (chatMessages) chatMessages.innerHTML=''; dialog=[]; } catch{}
    try { const logEl=document.getElementById('log-content'); if (logEl) logEl.textContent=''; } catch{}
    try { const aboutEl=document.getElementById('about-content'); if (aboutEl) aboutEl.textContent=''; } catch{}
    currentVideoName = null;
    try { if (nameToClear) await fetch(`/logs/${encodeURIComponent(nameToClear)}`, { method: 'DELETE' }); } catch{}
  }

  // Upload via DnD
  async function uploadFile(file){ showProcessing(true); setProcessingStep('extract'); const fd=new FormData(); fd.append('file', file); try { setTimeout(()=>setProcessingStep('transcribe'), 800); const r=await fetch('/upload',{method:'POST', body:fd}); const d=await r.json(); if(!r.ok) throw new Error(d.error||'Ошибка загрузки'); setProcessingStep('summarize'); loadVideo(d.url, d.name); fetchVideos(); } catch(e){ alert(e.message||'Произошла ошибка при загрузке'); } finally { setTimeout(()=>showProcessing(false), 600); } }
  ['dragenter','dragover'].forEach(ev=> mainPanel.addEventListener(ev, e=>{ e.preventDefault(); e.stopPropagation(); if (dropLayer.style.display!=='none') dropLayer.classList.add('active'); }));
  ['dragleave','dragend','drop'].forEach(ev=> mainPanel.addEventListener(ev, e=>{ e.preventDefault(); e.stopPropagation(); dropLayer.classList.remove('active'); }));
  mainPanel.addEventListener('drop', e=>{ e.preventDefault(); e.stopPropagation(); const f=e.dataTransfer?.files; if(f && f.length>0) uploadFile(f[0]); });

  // Controls
  playPauseButton.addEventListener('click', ()=>{ if (videoElement.paused) videoElement.play(); else videoElement.pause(); });
  videoElement.addEventListener('play', ()=>{ if (playPauseButton) playPauseButton.textContent='\u23F8'; /* ⏸ */ });
  videoElement.addEventListener('pause', ()=>{ if (playPauseButton) playPauseButton.textContent='\u25B6'; /* ▶ */ });
  videoElement.addEventListener('timeupdate', ()=>{ updateProgress(); updateSuggestionsForTime(); });
  videoElement.addEventListener('durationchange', updateProgress);

  // Volume and speed controls
  try {
    if (volumeSlider) {
      const v0 = parseFloat(volumeSlider.value || '1');
      if (!Number.isNaN(v0)) videoElement.volume = Math.max(0, Math.min(1, v0));
      volumeSlider.addEventListener('input', ()=>{
        const v = parseFloat(volumeSlider.value || '1');
        if (!Number.isNaN(v)) videoElement.volume = Math.max(0, Math.min(1, v));
      });
      volumeSlider.addEventListener('change', ()=>{
        const v = parseFloat(volumeSlider.value || '1');
        if (!Number.isNaN(v)) videoElement.volume = Math.max(0, Math.min(1, v));
      });
    }
    if (speedSelect) {
      const r0 = parseFloat(speedSelect.value || '1');
      if (!Number.isNaN(r0)) videoElement.playbackRate = r0;
      speedSelect.addEventListener('change', ()=>{
        const r = parseFloat(speedSelect.value || '1');
        if (!Number.isNaN(r)) videoElement.playbackRate = r;
      });
    }
  } catch {}

  // Seeking stability (avoid jump-back)
  let wasPlaying=false; progressBar.addEventListener('mousedown', ()=>{ wasPlaying=!videoElement.paused; if(wasPlaying) videoElement.pause(); }); progressBar.addEventListener('touchstart', ()=>{ wasPlaying=!videoElement.paused; if(wasPlaying) videoElement.pause(); }, {passive:true}); progressBar.addEventListener('input', ()=>{ videoElement.currentTime = parseFloat(progressBar.value||'0'); }); const finishScrub=()=>{ videoElement.currentTime = parseFloat(progressBar.value||'0'); if(wasPlaying) videoElement.play(); }; progressBar.addEventListener('mouseup', finishScrub); progressBar.addEventListener('touchend', finishScrub); progressBar.addEventListener('change', finishScrub);

  // Close button
  if (closeButton) closeButton.addEventListener('click', (e)=>{ e.stopPropagation(); closeVideo(); });

  function performUnmute(){
    try {
      if (!videoElement) return;
      if (!pendingUnmute) return;
      videoElement.muted = false;
      const v = parseFloat((volumeSlider && volumeSlider.value) || '1');
      if (!Number.isNaN(v)) videoElement.volume = Math.max(0, Math.min(1, v));
      videoElement.play().catch(()=>{});
      pendingUnmute = false;
      if (unmuteBtn) unmuteBtn.style.display = 'none';
    } catch {}
  }
  function attachOneShotUnmuteHandlers(){
    const opts = { once: true, capture: true };
    const handler = ()=> performUnmute();
    try { document.addEventListener('pointerdown', handler, opts); } catch {}
    try { document.addEventListener('mousedown', handler, opts); } catch {}
    try { document.addEventListener('touchstart', handler, opts); } catch {}
    try { document.addEventListener('keydown', handler, opts); } catch {}
    if (unmuteBtn) unmuteBtn.onclick = (e)=>{ e.stopPropagation(); performUnmute(); };
  }

  // Subtitles
  videoElement.addEventListener('timeupdate', ()=>{ if(!subtitlePanel||!currentSubtitles.length) return; const t=videoElement.currentTime; const idx=currentSubtitles.findIndex(s=> t>=s.start && t<s.end); highlightSubtitle(idx); });
  function renderSubtitles(subs){ if(!subtitleList) return; while(subtitleList.firstChild) subtitleList.removeChild(subtitleList.firstChild); subs.forEach((s,i)=>{ const li=document.createElement('li'); li.textContent = s.text; li.dataset.index=i; li.addEventListener('click', ()=>{ videoElement.currentTime = s.start+0.01; }); subtitleList.appendChild(li); }); }
  function highlightSubtitle(idx){ if(!subtitleList) return; const items=subtitleList.querySelectorAll('li'); items.forEach((li,i)=> li.classList.toggle('active', i===idx)); if(idx>=0){ const active=items[idx]; if(active&&subtitlePanel){ const pr=subtitlePanel.getBoundingClientRect(); const ir=active.getBoundingClientRect(); const above=ir.top<pr.top+8; const below=ir.bottom>pr.bottom-8; if(above) subtitlePanel.scrollTop += (ir.top-pr.top-8); else if(below) subtitlePanel.scrollTop += (ir.bottom-pr.bottom+8); } } }
  async function fetchSubtitlesFor(name){ if(!name) return []; try { const r=await fetch(`/subtitles/${encodeURIComponent(name)}.json`); if(!r.ok) return []; const d=await r.json(); return Array.isArray(d?.segments)? d.segments : []; } catch { return []; } }

  // Overlay
  function showProcessing(v){ if(processingOverlay) processingOverlay.style.display=v?'flex':'none'; }
  function setProcessingStep(step){ const m={ extract:document.querySelector('.step-extract'), transcribe:document.querySelector('.step-transcribe'), summarize:document.querySelector('.step-summarize') }; Object.values(m).forEach(el=>{ if(el){ el.classList.remove('active'); el.classList.remove('done'); } }); if(step==='extract'){ m.extract?.classList.add('active'); } if(step==='transcribe'){ m.extract?.classList.add('done'); m.transcribe?.classList.add('active'); } if(step==='summarize'){ m.extract?.classList.add('done'); m.transcribe?.classList.add('done'); m.summarize?.classList.add('active'); } }

  // Tabs (be tolerant to missing panels like 'log' in single-video mode)
  tabs.forEach(btn => btn.addEventListener('click', () => {
    tabs.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    // Hide all existing panels safely
    Object.values(panels).forEach(p => { if (p) p.style.display = 'none'; });
    // Show selected panel if it exists
    const id = btn.dataset.tab;
    if (panels[id]) panels[id].style.display = 'block';
    if (id === 'about') loadSummary();
    if (id === 'log') loadLog();
  }));

  // Chat
  chatSend?.addEventListener('click', sendChat);
  chatInput?.addEventListener('keydown', (e)=>{ if(e.key==='Enter') sendChat(); });
  function appendMsg(role, text){ dialog.push({ role, text }); const wrap=document.createElement('div'); wrap.className='msg '+(role==='student'?'msg-student':'msg-lecturer'); const content=document.createElement('div'); content.style.whiteSpace='pre-wrap'; if(role==='lecturer') content.innerHTML = mdToHtml(text||''); else content.textContent = text||''; wrap.appendChild(content); chatMessages.appendChild(wrap); chatMessages.scrollTop = chatMessages.scrollHeight; if(role==='lecturer' && window.MathJax && window.MathJax.typesetPromise){ window.MathJax.typesetPromise([wrap]).catch(()=>{}); } return wrap; }
  function appendLoader(role){ const wrap=document.createElement("div"); wrap.className='msg '+(role==='student'?'msg-student':'msg-lecturer'); const content=document.createElement("div"); content.innerHTML = '<span class="typing-loader" aria-label="loading"><span></span><span></span><span></span></span>'; wrap.appendChild(content); chatMessages.appendChild(wrap); chatMessages.scrollTop = chatMessages.scrollHeight; return {wrap, content}; }
  async function sendChat(textOverride){ const text=((typeof textOverride==='string' && textOverride.length)? textOverride : (chatInput.value||'')).trim(); if(!text||!currentVideoName) return; if(isBusy) return; appendMsg("student", text); if (!textOverride) chatInput.value=""; const {wrap, content}=appendLoader("lecturer"); isBusy = true; try{ chatInput.disabled = true; chatSend.disabled = true; if (explainBtn) explainBtn.disabled = true; }catch{} try { const body={ name: currentVideoName, currentTime: videoElement.currentTime||0, dialog, question: text }; const r=await fetch('/api/chat',{method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)}); if(!r.ok) throw new Error('Сервер вернул ошибку'); const d=await r.json(); const ans=(d&&d.answer)? d.answer : 'Нет ответа'; content.innerHTML = mdToHtml(ans); if (/ошибка/i.test(ans)) content.style.color='crimson'; if(window.MathJax&&window.MathJax.typesetPromise) window.MathJax.typesetPromise([wrap]).catch(()=>{}); } catch(e){ content.textContent = (e&&e.message)? e.message : 'Ошибка обращения к LLM'; content.style.color='crimson'; } finally { isBusy = false; try{ chatInput.disabled = false; chatSend.disabled = false; if (explainBtn) explainBtn.disabled = false; }catch{} } }
  // Summary & Log
  async function loadSummary(){ if(!currentVideoName) return; const el=document.getElementById('about-content'); let attempts=0; const pull = async ()=>{ try{ const r=await fetch(`/summary/${encodeURIComponent(currentVideoName)}`); if(!r.ok) return; const d=await r.json(); const txt=(d&&d.text)? d.text : ''; if (el) { el.innerHTML = txt ? mdToHtml(txt) : 'Описание пока не готово'; if(window.MathJax&&window.MathJax.typesetPromise) window.MathJax.typesetPromise([el]).catch(()=>{}); } if(!txt && attempts<6){ attempts++; setTimeout(pull, 5000); } } catch{} }; pull(); }
  async function loadLog(){ if(!currentVideoName) return; try{ const r=await fetch(`/logs/${encodeURIComponent(currentVideoName)}`); if(!r.ok) return; const d=await r.json(); const el=document.getElementById('log-content'); if(!el) return; const entries=d?.entries||[]; el.innerHTML=''; entries.forEach(e=>{ const block=document.createElement('div'); block.style.margin='8px 0'; const head=document.createElement('div'); head.style.fontWeight='600'; head.textContent=`${e.time} | ${e.type}`; const body=document.createElement('div'); body.style.whiteSpace='pre-wrap'; body.textContent=e.content||''; block.appendChild(head); block.appendChild(body); if(e.image_url){ const img=document.createElement('img'); img.src=e.image_url; img.alt='кадр'; img.style.maxWidth='100%'; img.style.borderRadius='6px'; img.style.marginTop='6px'; block.appendChild(img);} el.appendChild(block); }); if(!entries.length) el.textContent='Пусто'; } catch{} }
  btnClearLog?.addEventListener('click', async ()=>{ if(!currentVideoName) return; try { const r=await fetch(`/logs/${encodeURIComponent(currentVideoName)}`, { method:'DELETE' }); if (r.ok) loadLog(); } catch{} });

  // Frame analysis tooltip (fixed at click position)
  videoLayer.addEventListener('click', (e)=>{
    if (e.target.closest('#close-video') || e.target.closest('#explain-tooltip')) return;
    const rect=videoLayer.getBoundingClientRect();
    lastClickRel = { x:(e.clientX-rect.left)/rect.width, y:(e.clientY-rect.top)/rect.height };
    if (explainTooltip && !isBusy){
      // show and clamp inside the video
      explainTooltip.style.display='flex';
      // place offscreen to measure
      explainTooltip.style.left='-9999px';
      explainTooltip.style.top='-9999px';
      const tw = explainTooltip.offsetWidth || 160; // fallback
      const th = explainTooltip.offsetHeight || 44;
      let x = (lastClickRel.x*rect.width)+12;
      let y = (lastClickRel.y*rect.height)+12;
      if (x + tw > rect.width - 4) x = Math.max(4, rect.width - tw - 4);
      if (y + th > rect.height - 4) y = Math.max(4, rect.height - th - 4);
      if (x < 4) x = 4; if (y < 4) y = 4;
      explainTooltip.style.left = `${x}px`;
      explainTooltip.style.top = `${y}px`;
      setTimeout(()=>{ if (explainTooltip) explainTooltip.style.display='none'; }, 5000);
    }
  });
  // Ensure single handler
  if (explainBtn) {
    const newBtn = explainBtn.cloneNode(true); explainBtn.parentNode.replaceChild(newBtn, explainBtn);
    newBtn.addEventListener('click', async (e)=>{
      e.stopPropagation(); if(!currentVideoName) return; if (isBusy) return;
      const wasPlayingLocal = !videoElement.paused; if (wasPlayingLocal) videoElement.pause();
      const shot = await captureFrameWithMarker(lastClickRel);
      // mark dialog, show loader + student message in correct order
      try { dialog.push({ role:'student', text:'Поясни фрагмент', kind:'frame' }); } catch{}
      appendMsg('student','Поясни фрагмент');
      const studentWrap = document.querySelector('#chat-messages .msg:last-child'); if (studentWrap){ studentWrap.dataset.kind='frame'; studentWrap.dataset.normx=String(lastClickRel.x); studentWrap.dataset.normy=String(lastClickRel.y); }
      const {wrap, content} = appendLoader('lecturer');
      if (wrap){ wrap.dataset.kind='frame'; wrap.dataset.normx=String(lastClickRel.x); wrap.dataset.normy=String(lastClickRel.y); }
      // lock UI while waiting
      isBusy = true; try{ chatInput.disabled = true; chatSend.disabled = true; if (newBtn) newBtn.disabled = true; }catch{}
      try { const r=await fetch('/api/explain_frame',{method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ name: currentVideoName, currentTime: videoElement.currentTime||0, image: shot.dataUrl })}); if(!r.ok) throw new Error('Сервер вернул ошибку при анализе кадра'); const d=await r.json(); const ans=(d&&d.answer)? d.answer : 'Нет ответа'; content.innerHTML = mdToHtml(ans); if (/ошибка/i.test(ans)) content.style.color='crimson'; if(window.MathJax&&window.MathJax.typesetPromise) window.MathJax.typesetPromise([wrap]).catch(()=>{}); showAnnotationPopover(ans, lastClickRel); } catch(e){ content.textContent = (e&&e.message)? e.message : 'Ошибка обращения к LLM (кадр)'; content.style.color='crimson'; }
      finally { isBusy = false; try{ chatInput.disabled = false; chatSend.disabled = false; if (newBtn) newBtn.disabled = false; }catch{} }
    });
  }

  async function captureFrameWithMarker(norm){
    const vw=videoElement.videoWidth||1280; const vh=videoElement.videoHeight||720;
    const canvas=document.createElement("canvas"); canvas.width=vw; canvas.height=vh;
    const ctx=canvas.getContext("2d"); ctx.drawImage(videoElement,0,0,vw,vh);
    const cx=Math.max(0,Math.min(1,norm.x))*vw; const cy=Math.max(0,Math.min(1,norm.y))*vh;
    const r=vh*0.15;
    ctx.fillStyle="rgba(255,0,0,0.5)"; ctx.beginPath(); ctx.arc(cx,cy,r,0,Math.PI*2); ctx.fill();
    return { dataUrl: canvas.toDataURL("image/png") };
  }
  function showAnnotationPopover(_text, norm){ if(!videoLayer) return; const rect=videoLayer.getBoundingClientRect(); const marker=document.createElement('div'); marker.className='pulse-marker'; marker.style.left = `${norm.x*rect.width}px`; marker.style.top = `${norm.y*rect.height}px`; videoLayer.appendChild(marker); setTimeout(()=>{ if(marker&&marker.parentNode) marker.parentNode.removeChild(marker); }, 8400); }

  // Very basic Markdown rendering
  function mdToHtml(src){
    let s=(src||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    // links, code, bold/italic
    s=s.replace(/\[([^\]]+)\]\((https?:[^\s)]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1<\/a>');
    s=s.replace(/`([^`]+)`/g,'<code>$1<\/code>');
    s=s.replace(/\*\*([^*]+)\*\*/g,'<strong>$1<\/strong>').replace(/__([^_]+)__/g,'<strong>$1<\/strong>');
    s=s.replace(/(^|\s)\*([^*]+)\*(?=\s|$)/g,'$1<em>$2<\/em>').replace(/(^|\s)_([^_]+)_(?=\s|$)/g,'$1<em>$2<\/em>');
    // headings (###, ##, #) – same compact style
    s=s.replace(/(^|\n)###\s+([^\n]+)/g,'$1<div class="md-h3">$2<\/div>');
    s=s.replace(/(^|\n)##\s+([^\n]+)/g,'$1<div class="md-h2">$2<\/div>');
    s=s.replace(/(^|\n)#\s+([^\n]+)/g,'$1<div class="md-h1">$2<\/div>');
    // Simple list handling before line breaks
    if (/^-\s/m.test(s)){
      const lines=s.split(/\n/); let out=''; let inList=false;
      for(const line of lines){
        if(line.startsWith('- ')){
          if(!inList){ out+='<ul>'; inList=true; }
          out+='<li>'+line.slice(2)+'</li>';
        } else {
          if(inList){ out+='</ul>'; inList=false; }
          out+=line+'\n';
        }
      }
      if(inList) out+='</ul>';
      s=out;
    }
    // line breaks
    s=s.replace(/\n/g,'<br/>' );
    return s;
  }
  // Replay marker on clicking frame-related chat messages
  if (chatMessages) {
    chatMessages.addEventListener('click', (e)=>{
      const node = e.target.closest('.msg');
      if(!node) return;
      if(node.dataset && node.dataset.kind==='frame'){
        const nx = parseFloat(node.dataset.normx||'');
        const ny = parseFloat(node.dataset.normy||'');
        const norm = (!isNaN(nx) && !isNaN(ny)) ? { x:nx, y:ny } : lastClickRel;
        showAnnotationPopover('', norm);
      }
    });
  }  // Init
  try { const tipSpan=document.querySelector('#explain-tooltip span'); if(tipSpan) tipSpan.textContent='Что здесь?' ; const tipBtn=document.getElementById('explain-btn'); if(tipBtn) tipBtn.textContent='Пояснить' ; } catch{}
  if (playPauseButton) playPauseButton.textContent='\u25B6';
  if ((appCfg.singleMode===true || appCfg.singleMode==='true') && (appCfg.singleName||'').trim()){
    const name = (appCfg.singleName||'').trim();
    // For direct links: do not autoplay; show centered start overlay
    loadVideo(`/video/${encodeURIComponent(name)}`, name, false);
    try { if (videoElement) { videoElement.autoplay = false; videoElement.muted = false; } } catch{}
    const ov = ensureStartOverlay(); if (ov) ov.style.display = 'inline-block';
  } else {
    fetchVideos();
  }

  // File select trigger
  if (fileSelectTrigger && fileInput) {
    fileSelectTrigger.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      fileInput.click();
    });

    fileInput.addEventListener('change', (e) => {
      const files = e.target.files;
      if (files && files.length > 0) {
        uploadFile(files[0]);
        fileInput.value = ''; // Reset input
      }
    });
  }

  // Video filter
  if (videoFilter) {
    videoFilter.addEventListener('input', (e) => {
      const filterText = e.target.value.toLowerCase().trim();
      const items = videoList.querySelectorAll('.video-item');
      
      items.forEach(item => {
        const name = item.querySelector('.name');
        if (name) {
          const videoName = name.textContent.toLowerCase();
          if (videoName.includes(filterText)) {
            item.style.display = 'flex';
          } else {
            item.style.display = 'none';
          }
        }
      });
    });
  }
});
