'use strict';
const $ = id => document.getElementById(id);
let state, busy = false;
const session = sessionStorage.getItem('risk-demo-session') || crypto.randomUUID();
sessionStorage.setItem('risk-demo-session', session);
const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = (value, places = 2) => value === null || value === undefined ? 'Unknown' : Number(value).toLocaleString('en-US', {maximumFractionDigits: places});
const time = value => new Date(value).toISOString().slice(11, 16);
const stamp = value => `${new Date(value).toISOString().slice(0,10)} ${time(value)}`;
const utcInput = value => new Date(value).toISOString().slice(0,19);
const features = {
 latest_temperature_c:['Latest temperature','°C'], measurement_age_minutes:['Measurement age','min'],
 arrival_delay_minutes:['Arrival delay','min'], temperature_missing:['Temperature missing',''],
 temperature_count:['Readings in window',''], temperature_mean_c:['Mean temperature','°C'],
 temperature_max_c:['Maximum temperature','°C'], temperature_trend_c_per_hour:['Temperature trend','°C/h'],
 temperature_span_hours:['Observation span','h']
};
const reasons = {
 shipment_not_retained:'Shipment is not retained. The score uses the learned overall incident rate.',
 retention_coverage_unverified:'Earlier history may be missing after eviction.',
 history_truncated:'Some history was removed to meet the record cap.',
 no_usable_temperature:'No usable temperature is available at this time.',
 stale_temperature:'The latest reading is more than three hours old.',
 future_device_clock_excluded:'A measurement ahead of its receipt time was excluded.'
};
async function request(path, body) {
 const response = await fetch(path, body ? {method:'POST', headers:{'Content-Type':'application/json','X-Demo-Session':session},body:JSON.stringify(body)} : {headers:{'X-Demo-Session':session}});
 const result = await response.json();
 if (!response.ok) throw new Error(result.error || 'The request failed.');
 return result;
}
function notice(message, error=false) {
 $('notice').textContent=message; $('notice').classList.toggle('error',error);
}
async function action(name, extra={}) {
 if(busy)return;
 busy=true;document.body.classList.add('busy');
 try {
  const value=$('as-of').value;
  if(name!=='reset' && !value)throw new Error('Choose a UTC prediction time.');
  state=await request('/api/action',{action:name,shipment:$('shipment').value,as_of:value ? value+'Z' : undefined,...extra});
  if(name==='reset') $('follow').checked=false;
  render(); notice(state.message);
 } catch(error){notice(error.message,true);}
 finally{busy=false;document.body.classList.remove('busy');}
}
function render() {
 $('scenario').value=state.scenario;$('capacity').value=state.capacity;
 $('scenario-note').textContent=state.scenario==='lesson' ? 'Seven invented deliveries. A small example you can check by hand.' : 'Synthetic source data, processed in its original file order.';
 $('position').textContent=`${state.position.toLocaleString()} / ${state.total.toLocaleString()}`;
 $('progress').max=state.total;$('progress').value=state.position;
 $('shipment').innerHTML=state.shipments.map(s=>`<option value="${escapeHTML(s)}">${escapeHTML(s)}</option>`).join('');
 $('shipment').value=state.shipment;$('as-of').value=utcInput(state.as_of);
 const next=state.next_event;
 $('next-event').innerHTML=next ? `<span>NEXT DELIVERY</span><b>${escapeHTML(next.event_id)} · revision ${next.revision}</b><span>${escapeHTML(next.shipment_id)} · received ${stamp(next.received_at)}</span>` : '<b>End of the stream.</b><span>Reset to replay from the beginning.</span>';
 $('step').disabled=!next;$('batch').disabled=!next || state.scenario==='lesson';$('batch').textContent='Next 1,000';
 $('noon').hidden=state.scenario!=='lesson';$('restore').disabled=!state.has_snapshot;
 $('probability').innerHTML=`${(state.prediction.probability*100).toFixed(1)}<span>%</span>`;
 $('horizon').textContent=`${stamp(state.as_of)} → ${stamp(state.horizon_end)} UTC`;
 $('model-version').textContent=state.prediction.model_version;$('feature-digest').textContent=state.prediction.feature_digest;
 $('quality').innerHTML=state.prediction.degraded ? `<div class="quality warn"><b>Limited evidence</b><ul>${state.prediction.reasons.map(r=>`<li>${escapeHTML(reasons[r] || r)}</li>`).join('')}</ul></div>` : '<div class="quality">No engine degradation flags at this checkpoint.</div>';
 const f=state.features;
 $('key-features').innerHTML=['latest_temperature_c','measurement_age_minutes','temperature_trend_c_per_hour'].map(k=>`<div><label>${features[k][0]}</label><strong>${num(f[k])} <small>${f[k]===null?'':features[k][1]}</small></strong></div>`).join('');
 $('all-features').innerHTML=Object.entries(features).map(([k,[label,unit]])=>`<div class="feature-item"><span>${label}</span><b>${num(f[k])}${f[k]===null || !unit?'':' '+unit}</b></div>`).join('');
 $('table-count').textContent=`${state.displayed_deliveries} of ${state.shipment_deliveries} deliveries`;
 $('readings-body').innerHTML=state.deliveries.length ? state.deliveries.map(e=>`<tr><td>${escapeHTML(e.event_id)}<small>File row ${e.file_row} · ${escapeHTML(e.kind)}</small></td><td>r${e.revision}</td><td>${stamp(e.device_time)}</td><td>${stamp(e.received_at)}</td><td>${escapeHTML(e.value ?? 'Missing')}${e.kind==='temperature_c'?' °C':''}</td><td><span class="badge ${e.status==='In temperature window'?'eligible':/Not |excluded/.test(e.status)?'warning':''}">${escapeHTML(e.status)}</span></td></tr>`).join('') : '<tr><td colspan="6">No deliveries for this shipment have been processed yet.</td></tr>';
 const st=state.stats;
 $('stats').innerHTML=[[`${st.shipments} / ${st.max_shipments}`,'Shipments'],[st.retained_records,'Records'],[st.evictions,'Evictions'],[st.trimmed,'Trimmed records']].map(([v,l])=>`<div class="stat"><b>${v}</b><span>${l}</span></div>`).join('');
 $('retained').textContent=`Retained, oldest update first: ${state.retained_shipments.slice(0,8).join(', ') || 'none'}${state.retained_shipments.length>8?'…':''}. Up to ${st.max_records_per_shipment} records per shipment; ${st.event_id_index} event IDs indexed.`;
 $('window-label').textContent=`${stamp(state.lookback_start)} → ${time(state.as_of)} UTC`;
 $('outcome-content').hidden=true;$('outcome-content').replaceChildren();$('reveal').textContent='Reveal audit reports';
 drawChart();
}
function drawChart() {
 const rows=state.deliveries.filter(e=>typeof e.value==='number' && Number.isFinite(e.value) && e.kind==='temperature_c');
 const width=560,height=265,left=42,right=16,top=25,bottom=40;
 const start=Date.parse(state.lookback_start), end=Date.parse(state.as_of);
 const minX=Math.min(start,...rows.map(e=>Date.parse(e.device_time))),maxX=Math.max(end,...rows.map(e=>Date.parse(e.device_time)))+10*60000;
 const low=Math.min(0,...rows.map(e=>e.value)),high=Math.max(10,...rows.map(e=>e.value))+2;
 const x=v=>left+(v-minX)/(maxX-minX)*(width-left-right),y=v=>height-bottom-(v-low)/(high-low)*(height-top-bottom);
 let svg=`<svg viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><rect x="${x(start)}" y="${top}" width="${x(end)-x(start)}" height="${height-top-bottom}" fill="#eff4e7"/>`;
 for(let i=0;i<=4;i++){
  const v=low+(high-low)*i/4;
  svg+=`<line x1="${left}" x2="${width-right}" y1="${y(v)}" y2="${y(v)}" stroke="#e3e8de"/><text x="${left-9}" y="${y(v)+4}" text-anchor="end" fill="#788679" font-size="10">${num(v,1)}°</text>`;
 }
 for(let i=0;i<=4;i++){
  const v=minX+(maxX-minX)*i/4;
  svg+=`<text x="${x(v)}" y="${height-15}" text-anchor="middle" fill="#788679" font-size="10">${time(v)}</text>`;
 }
 svg+=`<line x1="${x(end)}" x2="${x(end)}" y1="${top}" y2="${height-bottom}" stroke="#65876b" stroke-dasharray="4 4"/><text x="${x(end)-4}" y="15" text-anchor="end" fill="#4e6e50" font-size="10">PREDICTION TIME</text>`;
 const eligible=rows.filter(e=>e.status==='In temperature window').sort((a,b)=>Date.parse(a.device_time)-Date.parse(b.device_time));
 if(eligible.length>1)svg+=`<polyline points="${eligible.map(e=>`${x(Date.parse(e.device_time))},${y(e.value)}`).join(' ')}" stroke="#2e674c" fill="none" stroke-width="2"/>`;
 for(const e of rows){
  const good=e.status==='In temperature window';
  svg+=`<circle cx="${x(Date.parse(e.device_time))}" cy="${y(e.value)}" r="${good?5:3.5}" fill="${good?'#2e674c':'#c3cbc2'}" stroke="white" stroke-width="1.5"><title>${escapeHTML(`${e.event_id} r${e.revision}: ${e.value}°C; ${stamp(e.device_time)} UTC; ${e.status}`)}</title></circle>`;
 }
 if(!rows.length)svg+=`<text x="${width/2}" y="${height/2}" text-anchor="middle" fill="#72816e" font-size="12">No numeric temperature deliveries to display</text>`;
 $('chart').innerHTML=svg+'</svg>';
 $('chart').setAttribute('aria-label',`${rows.length} temperature deliveries shown; ${eligible.length} in the temperature window. Prediction at ${stamp(state.as_of)} UTC. Other deliveries may be excluded or not retained.`);
}
async function showEvaluation(){
 try{
  const r=await request('/api/evaluation');
  const metric=(v,d=4)=>v===null || v===undefined?'Not available':Number(v).toFixed(d);
  $('evaluation-content').innerHTML=`<span class="eyebrow">${escapeHTML(r.model_kind.replaceAll('_',' '))} · FIXED BEFORE TEST EVALUATION</span><div class="eval-metrics"><div><b>${r.test.rows}</b><span>Held-out checkpoints</span></div><div><b>${r.test.positives}</b><span>Incident outcomes</span></div><div><b>${r.development_rows}</b><span>Development rows used for final fit</span></div></div><h2>Selected model vs. constant baseline</h2><div class="table-scroll"><table><thead><tr><th>Model</th><th>Average precision ↑</th><th>Brier score ↓</th><th>Log loss ↓</th><th>Recall at 20%</th><th>Precision at 20%</th></tr></thead><tbody>${[['Selected model',r.test],['Constant baseline',r.constant_test]].map(([label,m])=>`<tr><td>${label}</td><td>${metric(m.average_precision)}</td><td>${metric(m.brier)}</td><td>${metric(m.log_loss)}</td><td>${metric(m.recall_at_0_2,2)}</td><td>${metric(m.precision_at_0_2,2)}</td></tr>`).join('')}</tbody></table></div><p class="help">Average precision measures ranking. Brier and log loss measure probability error. The 20% threshold is an illustration, not an operating recommendation.</p><h2>Performance by source, freshness and trend availability</h2><div class="table-scroll"><table><thead><tr><th>Slice</th><th>Group</th><th>Rows</th><th>Incidents</th><th>Average precision</th><th>Brier</th></tr></thead><tbody>${r.slices.map(s=>`<tr><td>${escapeHTML(s.dimension)}</td><td>${escapeHTML(s.value.replaceAll('_',' '))}</td><td>${s.rows}</td><td>${s.positives}</td><td>${metric(s.average_precision)}</td><td>${metric(s.brier)}</td></tr>`).join('')}</tbody></table></div><h2>What these results can tell us</h2><p class="help">${escapeHTML(r.split.rule)}. Validation begins ${stamp(r.split.validation_start)} UTC; test begins ${stamp(r.split.test_start)} UTC. The assumed observation cutoff is ${stamp(r.split.observation_cutoff)} UTC.</p><ul class="help">${r.limitations.map(l=>`<li>${escapeHTML(l)}</li>`).join('')}</ul><p class="help">Read from the saved evaluation report. The UI does not retrain, tune a threshold or use outcomes to create features.</p>`;
 }catch(e){$('evaluation-content').textContent=`Evaluation unavailable: ${e.message}`;}
}
for(const button of document.querySelectorAll('[data-tab]'))button.addEventListener('click',()=>{
 for(const pane of document.querySelectorAll('.tab'))pane.hidden=pane.id!==button.dataset.tab;
 for(const nav of document.querySelectorAll('[data-tab]'))nav.classList.toggle('active',nav===button);
 if(button.dataset.tab==='evaluation')showEvaluation();
});
$('reset').onclick=()=>action('reset',{scenario:$('scenario').value,capacity:Number($('capacity').value)});
$('scenario').onchange=()=>action('reset',{scenario:$('scenario').value,capacity:$('scenario').value==='lesson'?2:32});
$('step').onclick=()=>action('step',{count:1,follow_time:$('follow').checked});
$('batch').onclick=()=>action('step',{count:1000,follow_time:$('follow').checked});
$('score').onclick=()=>action('view');$('shipment').onchange=()=>action('view');
$('noon').onclick=()=>{$('as-of').value='2026-01-01T12:00:00';action('view');};
$('save').onclick=()=>action('save');$('restore').onclick=()=>action('restore');
$('valid-reload').onclick=()=>action('reload_valid');$('invalid-reload').onclick=()=>action('reload_invalid');
$('reveal').onclick=async()=>{
 if(busy)return;
 try{
  const viewedShipment=state.shipment, viewedScenario=state.scenario;
  const result=await request('/api/outcomes');
  if(viewedShipment!==state.shipment || viewedScenario!==state.scenario)return;
  $('outcome-content').hidden=false;
  $('outcome-content').innerHTML=`<p>${escapeHTML(result.note)}</p>${result.reports.length ? result.reports.map(r=>`<p><b>Incident:</b> ${stamp(r.incident_at)} UTC · <b>Report available:</b> ${stamp(r.label_available_at)} UTC</p>`).join('') : '<p>No incident report is listed for this shipment. Its outcome is not certified negative.</p>'}`;
 }catch(e){notice(e.message,true);}
};
request('/api/state').then(s=>{state=s;render();notice(s.message);}).catch(e=>notice(`Could not load the engine: ${e.message}`,true));
