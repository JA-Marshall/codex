let csrf = '', selected = null, current = null, timerRunning = false;
let soundOn = false, lastPending = -1, audio = null;
try { soundOn = localStorage.getItem('review-sound') === 'on'; } catch (e) {}
const tab = crypto.randomUUID();
const $ = id => document.getElementById(id);
const states = {created:'Preparing review', pausing:'Pausing work', pending:'Waiting for you', answered:'Answer saved', consumed:'Answer saved', interrupted:'Interrupted', expired:'Expired', withdrawn:'Withdrawn', pause_failed:'Could not pause'};
function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
async function api(path, body, keepalive = false, retry = true) {
  const response = await fetch(path, {method:body?'POST':'GET', keepalive,
    headers:body?{'Content-Type':'application/json','X-Review-CSRF':csrf}:{}, body:body?JSON.stringify(body):undefined});
  const value = await response.json();
  if(response.status===403 && body && path!=='/api/session' && retry) {
    const session=await fetch('/api/session');
    if(session.ok) {csrf=(await session.json()).csrf;return api(path,body,keepalive,false);}
  }
  if (!response.ok) throw new Error(value.error || 'Connection unavailable');
  return value;
}
function status(row) { return row.continued ? 'Continuing' : states[row.state] || row.state; }
async function connect() {
  const token = location.hash.slice(1);
  if (token) { history.replaceState(null,'',location.pathname); sessionStorage.setItem('review-entry',token); }
  try { csrf = (await api('/api/session')).csrf; }
  catch (error) {
    const saved = sessionStorage.getItem('review-entry');
    if (!saved) throw error;
    csrf = (await api('/api/session',{token:saved})).csrf;
  }
}
async function timer(action, extra = {}) {
  if (!selected) return;
  try {
    const value = await api('/api/timer',{request:selected,tab,action,...extra},action==='pause');
    timerRunning = value.this_tab;
    if ($('timer-status')) $('timer-status').textContent = `${Math.floor(value.seconds/60)}m ${Math.floor(value.seconds%60)}s active review · ` + (value.this_tab?'Timer running':value.running?'Running in another tab':'Paused');
    if ($('timer-toggle')) $('timer-toggle').textContent = value.this_tab?'Pause timer':'Resume timer';
  } catch (error) {
    timerRunning = false;
    if ($('timer-status')) $('timer-status').textContent = error.message+' Timer paused; resume explicitly.';
    if ($('timer-toggle')) $('timer-toggle').textContent = 'Resume timer';
  }
}
document.addEventListener('visibilitychange',()=>{if(document.hidden) timer('pause');});
window.addEventListener('pagehide',()=>timer('pause'));
async function poll() {
  try {
    const rows = await api('/api/reviews');
    const pending = rows.filter(row=>row.state==='pending').length;
    if (lastPending >= 0 && pending > lastPending && soundOn) beep();
    lastPending = pending;
    document.title = `(${pending}) Review inbox`;
    $('count').textContent = pending;
    $('connection').textContent = 'Connected · updates every 2 seconds';
    const activeIds = new Set(rows.map(row=>row.id));
    for (const button of $('cases').children) if (!activeIds.has(button.dataset.id)) button.remove();
    if (!selected && rows.length) $('detail').replaceChildren(el('h2','Select a case'),el('p','Choose a ready request from the inbox to review it.'));
    for (const row of rows) {
      let button = [...$('cases').children].find(node=>node.dataset.id===row.id);
      if (!button) {
        button=el('button');button.dataset.id=row.id;
        button.append(el('span','','code'),el('strong',''),el('span','','state'));
        button.onclick=()=>open(row.id,true);$('cases').append(button);
      }
      button.className='case'+(selected===row.id?' selected':'');
      const wait=row.ready?` · ${Math.max(0,Math.floor(((row.answered_at||Date.now()/1000)-row.ready)/60))}m waiting`:'';
      button.children[0].textContent=row.code+(row.unread?' · NEW':'');
      button.children[1].textContent=row.title;
      button.children[2].textContent=`${row.kind} · ${status(row)}${wait}`;
    }
    const row = rows.find(r=>r.id===selected);
    if (row && current && (row.state!==current.state || row.continued!==current.continued)) await open(selected,false);
    if (selected && current?.state==='pending' && !document.hidden) await timer(timerRunning?'heartbeat':'status');
  } catch (error) {
    timerRunning = false;
    if ($('timer-status')) $('timer-status').textContent = 'Connection lost. Timer paused; resume explicitly after reconnecting.';
    if ($('timer-toggle')) $('timer-toggle').textContent = 'Resume timer';
    $('connection').textContent = error.message+' Reconnecting; drafts remain unsent.';
    try { await connect(); } catch {}
  }
}
async function open(id,userSelected=false) {
  if (selected && selected!==id) await timer('pause');
  selected = id;
  current = await api('/api/reviews/'+id);
  const root = $('detail'), p = current.presented;
  root.replaceChildren(el('div',current.code,'code'),el('h2',current.title),el('p',status(current),'notice'));
  root.append(el('h3','Original request'),el('pre',p.request||''));
  if(p.decisions?.length) root.append(el('h3','Earlier owner decisions'),el('pre',p.decisions.join('\n\n')));
  if(current.state!=='pending') { await timer('pause'); root.append(el('p','This review is retained in its current state.','muted')); return; }
  const timerText=el('p','Review timer paused','muted'); timerText.id='timer-status';
  const toggle=el('button','Resume timer'); toggle.id='timer-toggle'; toggle.onclick=()=>timer(timerRunning?'pause':'start');
  const adjust=el('button','Adjust time');
  adjust.onclick=async()=>{const minutes=prompt('Minutes to add or subtract for offline review:'); if(minutes===null||!Number.isFinite(Number(minutes)))return; const reason=prompt('Why are you adjusting the timer?'); if(reason?.trim())await timer('adjust',{seconds:Number(minutes)*60,reason});};
  root.append(timerText,toggle,adjust);
  const secondary=el('details'),summary=el('summary','More actions');
  const withdraw=el('button','Withdraw this case');
  withdraw.onclick=async()=>{const reason=prompt('Withdraw this case without continuing its work. Optional reason:');if(reason===null)return;try{await api('/api/reviews/'+id+'/withdraw',{reason});await open(id);await poll();}catch(error){$('connection').textContent=error.message;}};
  secondary.append(summary,withdraw);root.append(secondary);
  const form=el('form'),draftKey='review-draft-'+id;
  let draft={}; try{draft=JSON.parse(localStorage.getItem(draftKey)||'{}');}catch{}
  const fields={};
  for(const q of p.questions||[]) {
    const group=el('fieldset'); group.append(el('legend',q.header),el('p',q.question));
    const input=el('textarea'); input.value=draft[q.id]||''; input.placeholder='Your answer — free text is always available'; input.setAttribute('aria-label',q.question);
    for(const option of q.options||[]) { const button=el('button',option.label+' — '+option.description);button.type='button';button.onclick=()=>{input.value=option.label;input.dispatchEvent(new Event('input'));};group.append(button); }
    input.oninput=()=>{draft[q.id]=input.value;localStorage.setItem(draftKey,JSON.stringify(draft));};
    group.append(input);fields[q.id]=input;form.append(group);
  }
  const result=el('p','','notice'),actions=el('div',undefined,'actions');
  const send=el('button','Send answer','primary');send.type='submit';
  const unable=el('button','I cannot decide');unable.type='button';actions.append(send,unable);
  form.append(el('p','Drafts stay in this browser and are not sent until you submit.','muted'),actions,result);
  async function submit(action) {
    send.disabled=unable.disabled=true;
    const key=draft._key||(draft._key=crypto.randomUUID());localStorage.setItem(draftKey,JSON.stringify(draft));
    try {
      const answers=Object.fromEntries(Object.entries(fields).map(([id,input])=>[id,[input.value]]));
      await api('/api/reviews/'+id+'/response',{key,revision:current.revision,presented_hash:current.presented_hash,action,answers:action==='answer'?answers:null,text:'',new_scope:false});
      localStorage.removeItem(draftKey);await timer('pause');await open(id);await poll();
    }catch(error){result.textContent=error.message;send.disabled=unable.disabled=false;}
  }
  form.onsubmit=event=>{event.preventDefault();submit('answer');};unable.onclick=()=>submit('cannot_decide');root.append(form);
  await timer(userSelected&&!document.hidden?'start':'status');
}
function beep() {
  try {
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    if (audio.state === 'suspended') audio.resume();
    const osc = audio.createOscillator(), gain = audio.createGain();
    osc.connect(gain); gain.connect(audio.destination);
    gain.gain.value = 0.05; osc.frequency.value = 660;
    osc.start(); osc.stop(audio.currentTime + 0.15);
  } catch (e) {}
}
const soundBox = $('sound');
if (soundBox) {
  soundBox.checked = soundOn;
  soundBox.onchange = () => {
    soundOn = soundBox.checked;
    try { localStorage.setItem('review-sound', soundOn ? 'on' : 'off'); } catch (e) {}
    if (soundOn) beep();
  };
}
connect().then(()=>{poll();setInterval(poll,2000);}).catch(error=>$('connection').textContent=error.message);
