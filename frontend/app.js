let client=null, mic=null, sessionId=null, lastDecisionKey=null, statusPollBusy=false;
const DEBUG_LOG_LIMIT=200;
const debugEntries=[];
const $=id=>document.getElementById(id);
function debugLog(event, details={}, level='INFO'){
 const entry={time:new Date().toISOString(),level,event,details};
 debugEntries.push(entry);
 if(debugEntries.length>DEBUG_LOG_LIMIT) debugEntries.shift();
 console[level==='ERROR'?'error':level==='WARN'?'warn':'log']('[VoiceOps]',entry);
 const panel=$('debugLog');
 if(panel){
  const line=document.createElement('div');
  line.className='debug-entry';
  line.textContent=`${entry.time} [${level}] ${event} ${JSON.stringify(details)}`;
  panel.appendChild(line);
  while(panel.children.length>DEBUG_LOG_LIMIT) panel.removeChild(panel.firstChild);
  panel.scrollTop=panel.scrollHeight;
 }
} 

function notify(msg){$('toast').textContent=msg;$('toast').classList.add('show');setTimeout(()=>$('toast').classList.remove('show'),3500)}
async function api(path,opts={}){
 const method=opts.method||'GET';
 let requestBody=opts.body;
 let parsedBody=null;
 try{parsedBody=requestBody?JSON.parse(requestBody):null}catch(_){parsedBody='[unparsed body]'}
 debugLog('API request',{method,path,body:parsedBody});
 try{
  const r=await fetch(path,{headers:{'Content-Type':'application/json'},...opts});
  const d=await r.json().catch(()=>({}));
  debugLog('API response',{method,path,status:r.status,ok:r.ok,body:d},r.ok?'INFO':'ERROR');
  if(!r.ok)throw new Error(d.detail||`Request failed ${r.status}`);
  return d;
 }catch(err){debugLog('API network/error',{method,path,error:err.message},'ERROR');throw err}
}
function showScreen(id){
 debugLog('Screen transition',{from:document.querySelector('.screen.active')?.id||null,to:id});
 document.querySelectorAll('.screen').forEach(s=>s.classList.remove('active'));
 $(id).classList.add('active');window.scrollTo({top:0,behavior:'smooth'});
}
function normalizeSpokenId(s){
 let t=s.toLowerCase().replace(/[.,!?;:]/g,' ').replace(/-/g,' ').replace(/\s+/g,' ').trim();
 const forms=['pay san twenty forty eight','pay san two thousand forty eight','pay san two zero four eight','pay san two oh four eight','pay san 2048'];
 for(const f of forms) if(t.includes(f)) return t.replace(f,'pay san 2048');
 return t;
}
function showDecisionFromState(d){
 const key=`${d.decision}:${d.decided_at}`;
 if(!d.decision||!d.decided_at||key===lastDecisionKey)return;
 lastDecisionKey=key;
 debugLog('Backend MCP decision observed',{decision:d.decision,status:d.status,decided_at:d.decided_at});
 if(d.decision==='MITIGATE'){
  renderMitigation({incident_id:d.incident_id,decided_at:d.decided_at,status:d.status,steps:d.steps||[]});
  showScreen('mitigationScreen');
  $('toolStatus').textContent='Agora successfully invoked authorize_mitigation. The simulated runbook is complete.';
  $('mcpTag').textContent='MCP decision received';$('mcpTag').className='tag good';
 }else if(d.decision==='IGNORE'){
  renderIgnored({incident_id:d.incident_id,decided_at:d.decided_at,comment:d.comment||''});
  showScreen('ignoredScreen');
  $('toolStatus').textContent='Agora successfully invoked ignore_incident. Your comment was recorded.';
  $('mcpTag').textContent='MCP decision received';$('mcpTag').className='tag good';
 }
}
async function pollIncidentState(){
 if(statusPollBusy)return;
 statusPollBusy=true;
 try{const r=await fetch('/api/incident');if(!r.ok)throw new Error(`Status ${r.status}`);const d=await r.json();showDecisionFromState(d)}
 catch(e){debugLog('Incident state poll failed',{error:e.message},'WARN')}
 finally{statusPollBusy=false}
}
function renderMitigation(d){
 $('mitigationTime').textContent=new Date(d.decided_at).toLocaleString();
 $('mitigationIncident').textContent=d.incident_id;
 $('mitigationSteps').innerHTML=d.steps.map((s,i)=>`<div class="result-step"><span>${i+1}</span><div><b>${escapeHtml(s.title)}</b><small>${escapeHtml(s.detail)}</small></div><em>SIMULATED</em></div>`).join('');
 $('resultBanner').textContent=d.status;
}
function renderIgnored(d){
 $('ignoredTime').textContent=new Date(d.decided_at).toLocaleString();
 $('ignoredComment').textContent=d.comment;
 $('ignoredIncident').textContent=d.incident_id;
}
function escapeHtml(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function start(){
 debugLog('Agora voice session start requested');$('startBtn').disabled=true;$('voiceStatus').textContent='Starting secure voice session…';$('micNote').textContent='Connecting to Agora and requesting microphone access.';
 try{
  const s=await api('/api/call/start',{method:'POST',body:'{}'});sessionId=s.session_id;client=AgoraRTC.createClient({mode:'rtc',codec:'vp8'});
  client.on('user-published',async(user,type)=>{await client.subscribe(user,type);if(type==='audio')user.audioTrack.play()});
  await client.join(s.app_id,s.channel,s.token,s.uid);mic=await AgoraRTC.createMicrophoneAudioTrack();await client.publish([mic]);
  debugLog('Agora voice session connected',{channel:s.channel,sessionId:s.session_id,uid:s.uid});$('orb').classList.add('active');$('voiceStatus').textContent='You are connected';$('voiceSub').textContent='Agora Conversational AI · Murf voice';$('callTag').textContent='Live session';$('callTag').className='tag warn';$('micNote').textContent='Agora microphone connected. Speak directly to Samar; Agora will call the MCP decision tool when it hears an exact command.';$('stopBtn').disabled=false;notify('Voice session connected.');
 }catch(e){debugLog('Agora voice session start failed',{error:e.message},'ERROR');console.error(e);if(sessionId){try{await api('/api/call/stop',{method:'POST',body:JSON.stringify({session_id:sessionId})})}catch(_){}}sessionId=null;if(client){try{await client.leave()}catch(_){}}client=null;$('startBtn').disabled=false;$('voiceStatus').textContent='Could not connect';$('micNote').textContent=e.message;notify(e.message)}
}
async function stop(){
 debugLog('Stop voice session requested');$('stopBtn').disabled=true;
 try{if(mic){mic.stop();mic.close();mic=null}if(client){await client.leave();client=null}if(sessionId)await api('/api/call/stop',{method:'POST',body:JSON.stringify({session_id:sessionId})});sessionId=null;
  $('orb').classList.remove('active');$('voiceStatus').textContent='Session ended';$('voiceSub').textContent='You can start another session';$('callTag').textContent='Not connected';$('callTag').className='tag';$('micNote').textContent='Microphone released.';$('startBtn').disabled=false;notify('Voice session ended.');
 }catch(e){$('stopBtn').disabled=false;notify(e.message)}
}
async function submitTextDecision(){
 const transcript=$('manualCommand').value.trim();if(!transcript){notify('Enter a complete decision phrase first.');return}
 try{
  const normalized=normalizeSpokenId(transcript);
  if(normalized==='i authorize mitigation for incident pay san 2048'){
    const d=await api('/api/incident/mitigate',{method:'POST',body:JSON.stringify({transcript})});showDecisionFromState({...d,steps:d.steps});return;
  }
  if(normalized.startsWith('ignore incident pay san 2048') && /(?:my\s+comment\s+is|comment\s+is)\s+.+/i.test(transcript)){
    const d=await api('/api/incident/ignore',{method:'POST',body:JSON.stringify({transcript})});showDecisionFromState(d);return;
  }
  notify('Command did not match. Check the exact phrases below.');
 }catch(e){notify(e.message)}
}
async function reset(){
 try{if(sessionId)await stop();await api('/api/incident/reset',{method:'POST',body:'{}'});$('statusValue').textContent='Investigating';$('approvalTag').textContent='Awaiting engineer';$('manualCommand').value='';lastDecisionKey=null;$('toolStatus').textContent='Agora listens to your command and calls the backend MCP tool after the exact phrase is recognized.';$('mcpTag').textContent='Awaiting decision';$('mcpTag').className='tag';showScreen('dashboardScreen');notify('Demo state reset.')}
 catch(e){notify(e.message)}
}
$('startBtn').onclick=start;$('stopBtn').onclick=stop;$('manualSubmit').onclick=submitTextDecision;
$('resetBtn').onclick=reset;$('mitigationResetBtn').onclick=reset;$('ignoredResetBtn').onclick=reset;
$('copyDebugBtn').onclick=()=>{const content=debugEntries.map(e=>JSON.stringify(e)).join('\\n');navigator.clipboard?.writeText(content).then(()=>notify('Debug log copied.')).catch(()=>notify('Could not copy log; select and copy it manually.'));};
$('clearDebugBtn').onclick=()=>{debugEntries.length=0;$('debugLog').innerHTML='';debugLog('Debug log cleared');};
document.querySelectorAll('.questions button').forEach(b=>b.onclick=()=>notify(`Ask aloud: “${b.dataset.q}”`));
(async()=>{debugLog('App initialized',{userAgent:navigator.userAgent,platform:navigator.platform});try{const h=await api('/api/health');if(!h.credentials_configured){$('micNote').textContent='Setup required: add Agora and Murf credentials to your local .env file.';$('startBtn').disabled=true}if(!h.mcp_configured){$('toolStatus').textContent='MCP is not configured. Set MCP_PUBLIC_URL and MCP_AUTH_TOKEN in .env, then restart the server.';$('mcpTag').textContent='MCP not configured';$('mcpTag').className='tag warn'}else{$('mcpTag').textContent='MCP configured';$('mcpTag').className='tag good'}}catch(e){debugLog('Initial health check failed',{error:e.message},'WARN')}setInterval(pollIncidentState,1000);await pollIncidentState()})();
