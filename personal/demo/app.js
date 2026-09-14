'use strict';
const $ = id => document.getElementById(id);

const session = sessionStorage.getItem('risk-demo-session') || crypto.randomUUID();
sessionStorage.setItem('risk-demo-session', session);
const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = (value, places = 2) => value === null || value === undefined ? 'Unknown' : Number(value).toLocaleString('en-US', {maximumFractionDigits: places});
const time = value => new Date(value).toISOString().slice(11, 16);
const stamp = value => `${new Date(value).toISOString().slice(0,10)} ${time(value)}`;
const utcInput = value => new Date(value).toISOString().slice(0,19);
async function request(path, body, token=session) {
 const response = await fetch(path, body ? {method:'POST', headers:{'Content-Type':'application/json','X-Demo-Session':token},body:JSON.stringify(body)} : {headers:{'X-Demo-Session':token}});
 const result = await response.json();
 if (!response.ok) throw new Error(typeof result.detail==='string' ? result.detail : result.error || JSON.stringify(result.detail) || 'The request failed.');
 return result;
}
async function showEvaluation(){
 try{
  const r=await request('/api/evaluation');
  const metric=(v,d=4)=>v===null || v===undefined?'Not available':Number(v).toFixed(d);
  $('evaluation-content').innerHTML=`<span class="eyebrow">${escapeHTML(r.model_kind.replaceAll('_',' '))} · FIXED BEFORE TEST EVALUATION</span><div class="eval-metrics"><div><b>${r.test.rows}</b><span>Held-out checkpoints</span></div><div><b>${r.test.positives}</b><span>Incident outcomes</span></div><div><b>${r.development_rows}</b><span>Development rows used for final fit</span></div></div><h2>Selected model vs. constant baseline</h2><div class="table-scroll"><table><thead><tr><th>Model</th><th>Average precision ↑</th><th>Brier score ↓</th><th>Log loss ↓</th><th>Recall at 20%</th><th>Precision at 20%</th></tr></thead><tbody>${[['Selected model',r.test],['Constant baseline',r.constant_test]].map(([label,m])=>`<tr><td>${label}</td><td>${metric(m.average_precision)}</td><td>${metric(m.brier)}</td><td>${metric(m.log_loss)}</td><td>${metric(m.recall_at_0_2,2)}</td><td>${metric(m.precision_at_0_2,2)}</td></tr>`).join('')}</tbody></table></div><p class="help">Average precision measures ranking. Brier and log loss measure probability error. The 20% threshold is an illustration, not an operating recommendation.</p><h2>Performance by source, freshness and trend availability</h2><div class="table-scroll"><table><thead><tr><th>Slice</th><th>Group</th><th>Rows</th><th>Incidents</th><th>Average precision</th><th>Brier</th></tr></thead><tbody>${r.slices.map(s=>`<tr><td>${escapeHTML(s.dimension)}</td><td>${escapeHTML(s.value.replaceAll('_',' '))}</td><td>${s.rows}</td><td>${s.positives}</td><td>${metric(s.average_precision)}</td><td>${metric(s.brier)}</td></tr>`).join('')}</tbody></table></div><h2>What these results can tell us</h2><p class="help">${escapeHTML(r.split.rule)}. Validation begins ${stamp(r.split.validation_start)} UTC; test begins ${stamp(r.split.test_start)} UTC. The assumed observation cutoff is ${stamp(r.split.observation_cutoff)} UTC.</p><ul class="help">${r.limitations.map(l=>`<li>${escapeHTML(l)}</li>`).join('')}</ul><p class="help">Read from the saved evaluation report. The UI does not retrain, tune a threshold or use outcomes to create features.</p>`;
  const detail=$('evaluation-content').innerHTML;
  const m=r.test;
  const countsKnown=[m.true_positive,m.false_negative,m.false_positive].every(v=>Number.isFinite(v));
  $('evaluation-content').innerHTML=`<div class="button-row"><button id="show-model" class="primary" aria-pressed="true">Our model</button><button id="show-baseline" class="secondary" aria-pressed="false">Constant baseline</button></div><div id="model-visual" aria-live="polite"></div><p class="help">Synthetic test data · 20% alert cutoff</p><details><summary>Why is this a fair test?</summary><p>Fit on older shipments → choose on validation → test on later shipments. No shared shipments. Labels wait six hours plus 48 hours for reports.</p><p>That reporting completeness is assumed. These results do not establish real-world performance.</p></details><details class="technical-section"><summary>Full test report</summary>${detail}</details>`;
  const paint=(baseline)=>{
   const chosen=baseline?r.constant_test:r.test;
   const valid=[chosen.true_positive,chosen.false_negative,chosen.false_positive,chosen.positives].every(Number.isFinite);
   $('model-visual').innerHTML=valid ? `<p class="simple-caption">${baseline?'Same risk for every shipment':'Logistic regression'} · ${chosen.positives} incidents</p><div class="incident-dots" aria-label="${chosen.true_positive} caught, ${chosen.false_negative} missed">${Array.from({length:Math.min(chosen.positives,100)},(_,i)=>`<span class="${i<chosen.true_positive?'caught':'missed'}" aria-hidden="true"></span>`).join('')}</div><div class="result-counts">${[['Caught',chosen.true_positive],['Missed',chosen.false_negative],['False alarms',chosen.false_positive]].map(([label,value])=>`<div><strong>${value}</strong><span>${label}</span></div>`).join('')}</div>` : '<p>Insufficient test data.</p>';
   $('show-model').setAttribute('aria-pressed',String(!baseline));$('show-baseline').setAttribute('aria-pressed',String(baseline));
  };
  $('show-model').onclick=()=>paint(false);$('show-baseline').onclick=()=>paint(true);paint(false);


 }catch(e){$('evaluation-content').textContent=`Evaluation unavailable: ${e.message}`;}
}
for(const button of document.querySelectorAll('[data-tab]'))button.addEventListener('click',()=>{
 for(const pane of document.querySelectorAll('.tab'))pane.hidden=pane.id!==button.dataset.tab;
 for(const nav of document.querySelectorAll('.nav[data-tab]'))nav.classList.toggle('active',nav.dataset.tab===button.dataset.tab);

 window.scrollTo({top:0,behavior:'smooth'});
 if(button.dataset.tab==='evaluation')showEvaluation();
});
// Keep guided playback separate so it cannot reset the user's manual exploration.
const storySession = sessionStorage.getItem('risk-story-session') || crypto.randomUUID();
sessionStorage.setItem('risk-story-session', storySession);
let storyIndex = -1, storyBusy = false;
const storyCopy = [
 ['A reading arrives: 8°C.', 'The sensor measured 8°C at 9 AM. The message reached us at 9:05 AM. At 11 AM, we can use it.', 'At 11 AM, this is the temperature information we have.', 'The measurement time tells us how old the reading is. The arrival time tells us when we could first use it.'],
 ['The same message arrives again.', 'This is a retry of the original message. It does not give us another measurement.', 'The message arrived twice, but the engine counts it once. The prediction stays the same.', 'The engine recognizes the same event ID and revision. Repeating that delivery must not add another reading or change the prediction.'],
 ['A correction arrives at noon: 5°C.', 'We are still asking about the 11 AM prediction. At 11 AM, this correction had not arrived, so the engine still uses 8°C.', 'The corrected reading is 5°C, but we did not know that at 11 AM. We cannot use future information to rewrite the earlier prediction.', 'We have now delivered the noon correction to the engine, but the requested prediction time remains 11 AM. Only revisions received by that time are eligible.'],
 ['Now ask for a prediction at noon.', 'The correction has arrived by this time. The engine can now use the corrected 5°C reading.', 'At noon, we know about the correction, so we use it. What the engine knows depends on when we ask.', 'Moving to noon also moves the lookback and forecast windows. The corrected 9 AM reading supplies the latest temperature, but sits exactly outside the open left edge of the three-hour summary window. A score change cannot be attributed only to the temperature correction.']
];

/** Rebuild one guided checkpoint through the real API; Back never fakes engine state. */
async function showStory(index) {
 if(storyBusy)return;
 storyBusy=true;
 for(const id of ['story-next','story-back','story-restart']) $(id).disabled=true;
 $('story-error').hidden=true;
 try {
  const baseline=await request('/api/action',{action:'reset',scenario:'lesson',capacity:2},storySession);
  let result=baseline;
  if(index>0) result=await request('/api/action',{action:'step',count:Math.min(index,2),as_of:'2026-01-01T11:00:00Z',follow_time:false},storySession);
  if(index===3) result=await request('/api/action',{action:'view',as_of:'2026-01-01T12:00:00Z'},storySession);
  storyIndex=index;
  const [title,explanation,script,why]=storyCopy[index];
  $('story-step').textContent=`STEP ${index+1} OF 4`;
  $('story-title').textContent=title;
  $('story-explanation').textContent=['Measured at 9 AM. Arrived at 9:05.','Same message. Counted once.','Noon correction cannot change 11 AM.','At noon, the correction is available.'][index];
  $('timing-visual').hidden=false;
  $('timing-visual').innerHTML=`<div class="${index<3?'available':'superseded'}"><strong>8°C</strong><span>Arrived 9:05 AM</span><b>${index<3?'Used':'Replaced'}</b></div><span>→</span><div class="${index===3?'available':'superseded'}"><strong>5°C</strong><span>Arrives at noon</span><b>${index===3?'Used':index===2?'Too late for 11 AM':'Not yet available'}</b></div>`;
  $('story-facts').hidden=false;
  $('story-facts').innerHTML=[['Prediction time',`${time(result.as_of)} UTC`],['6-hour risk',`${result.prediction.probability > 0 && result.prediction.probability < 0.001 ? 'Less than 0.1' : num(result.prediction.probability*100,1)}%`]].map(([label,value])=>`<div><dt>${label}</dt><dd>${value}</dd></div>`).join('');
  const same=result.prediction.feature_digest===baseline.prediction.feature_digest && result.prediction.probability===baseline.prediction.probability;
  $('story-check').hidden=false;
  $('story-check').textContent=index===0 ? 'Prediction covers 11 AM to 5 PM.' : index<3 ? (same ? '✓ Same inputs · Same prediction' : 'Unexpected result: the prediction changed. Investigate before presenting this step.') : 'Prediction now covers noon to 6 PM. The latest temperature is 5°C.';
  $('story-script').hidden=false;
  $('story-script').textContent=`What you can say: “${script}”`;
  $('story-detail').hidden=false; $('story-detail').open=false;
  $('story-why').textContent=why;
  document.querySelectorAll('.story-steps li').forEach((item,i)=>{
   if(i===index)item.setAttribute('aria-current','step'); else item.removeAttribute('aria-current');
  });
  $('story-restart').hidden=false;
  $('story-next').textContent=['Next: repeat the message →','Next: deliver the correction →','Next: move to noon →','Walkthrough complete'][index];
  $('story-finish').hidden=index!==3;
 } catch(error) {
  $('story-error').textContent=`Could not load this step: ${error.message}. Try again.`;
  $('story-error').hidden=false;
 } finally {
  storyBusy=false;
  $('story-next').disabled=storyIndex===3;
  $('story-back').disabled=storyIndex<=0;
  $('story-restart').disabled=false;
 }
}
$('story-next').onclick=()=>showStory(Math.min(storyIndex+1,3));
$('story-back').onclick=()=>showStory(Math.max(storyIndex-1,0));
$('story-restart').onclick=()=>showStory(0);


/** Persist the navigation preference while keeping the menu button accessible. */
function setSidebar(collapsed) {
 document.body.classList.toggle('sidebar-collapsed',collapsed);
 $('sidebar-toggle').setAttribute('aria-expanded',String(!collapsed));
 $('sidebar-toggle').setAttribute('aria-label',collapsed?'Expand navigation':'Collapse navigation');
 sessionStorage.setItem('risk-sidebar-collapsed',String(collapsed));
}
$('sidebar-toggle').onclick=()=>setSidebar(false);
$('sidebar-close').onclick=()=>setSidebar(true);
setSidebar(sessionStorage.getItem('risk-sidebar-collapsed')==='true' || window.innerWidth < 800);


const checkSession = crypto.randomUUID();
let checkIndex = 0;

/** Run each reliability check from a known state using the existing engine API. */
async function runCheck() {
 $('check-run').disabled=true;
 $('check-reset').disabled=true;
 $('check-error').hidden=true;
 try {
  const call=(body)=>request('/api/action',body,checkSession);
  const initial=await call({action:'reset',scenario:'lesson',capacity:2});
  let result, title, description, evidence, meaning;
  if(checkIndex===0) {
   result=await call({action:'step',count:4});
   if(result.stats.shipments!==2 || result.stats.evictions!==1)throw new Error('Memory check did not match the expected limit.');
   title='Memory stays within the limit.';
   description='Three shipments arrived. There is room for two.';
   evidence=`${result.stats.shipments} kept · ${result.stats.evictions} removed`;
   meaning='The oldest shipment is removed. Its lost history is flagged in predictions.';
  } else if(checkIndex===1) {
   await call({action:'save'});
   await call({action:'step',count:4});
   result=await call({action:'restore'});
   if(JSON.stringify(result.prediction)!==JSON.stringify(initial.prediction))throw new Error('Restored prediction differs.');
   title='Saved state comes back correctly.';
   description='Save the state, process more messages, then restore it.';
   evidence='Original prediction restored';
   meaning='The server also checks that the saved and restored prediction bytes match.';
  } else {
   result=await call({action:'reload_invalid'});
   if(JSON.stringify(result.prediction)!==JSON.stringify(initial.prediction))throw new Error('Prediction changed after failed reload.');
   title='A failed update does not stop scoring.';
   description='Try loading a model file that does not exist.';
   evidence='Previous model still serving';
   meaning='The update is rejected. The prediction stays unchanged.';
  }
  $('check-number').textContent=`CHECK ${checkIndex+1} OF 3 · PASSED`;
  $('check-title').textContent=title;
  $('check-description').textContent=['3 shipments → 2 spaces','Save → advance → restore','Broken update → previous model'][checkIndex];
  $('check-visual').innerHTML=checkIndex===0 ? '<span class="removed">A removed</span><span>B kept</span><span>C kept</span>' : checkIndex===1 ? '<span>Saved</span><b> = </b><span>Restored</span>' : '<span class="removed">Update rejected</span><span>Original running</span>';
  $('check-result').textContent=evidence; $('check-result').hidden=false;
  $('check-meaning').textContent=meaning; $('check-meaning').hidden=false;
  checkIndex++;
  $('check-run').textContent=['','Next: check restore →','Next: try a failed update →','All three checks passed'][checkIndex];
  $('check-reset').hidden=false;
 } catch(error) {
  $('check-error').textContent=`Check failed: ${error.message}`;
  $('check-error').hidden=false;
 } finally {
  $('check-run').disabled=checkIndex===3;
  $('check-reset').disabled=false;
 }
}
$('check-run').onclick=runCheck;
$('check-reset').onclick=()=>{
 checkIndex=0;
 $('check-number').textContent='THREE SMALL CHECKS';
 $('check-title').textContent='What happens when memory fills up?';
 $('check-description').textContent='3 shipments → 2 spaces';
 $('check-visual').innerHTML='<span>A</span><span>B</span><span>C</span>';
 $('check-result').hidden=true; $('check-meaning').hidden=true;
 $('check-error').hidden=true; $('check-reset').hidden=true;
 $('check-run').textContent='Run memory check →'; $('check-run').disabled=false;
};

/** Generate and verify a fresh stream using the FastAPI backend. */
$('run-stream').onclick=async()=>{
 const button=$('run-stream'); button.disabled=true;
 $('run-result').textContent='Generating and checking…';
 try {
  const result=await request('/api/interview/stream',{seed:Number($('run-seed').value),shipments:Number($('run-size').value),max_shipments:Number($('run-limit').value)});
  $('run-result').innerHTML=`<div class="result-counts"><div><strong>${num(result.events,0)}</strong><span>Messages</span></div><div><strong>${result.first_replay.peak_shipments}</strong><span>Peak shipments retained</span></div></div><ul class="run-checks">${Object.entries(result.checks).map(([key,passed])=>`<li>${passed?'✓':'✗'} ${escapeHTML(key.replaceAll('_',' '))}</li>`).join('')}</ul><p class="help">Saved: ${escapeHTML(result.output_directory)}</p><details><summary>Request &amp; evidence</summary><pre>${escapeHTML(JSON.stringify(result,null,2))}</pre></details>`;
 }catch(error){$('run-result').textContent=`Could not run: ${error.message}. Start the FastAPI server; see personal/README.md.`;}
 finally{button.disabled=false;}
};
$('run-tests').onclick=async()=>{
 $('run-tests').disabled=true; $('test-output').textContent='Running tests…';
 try {const result=await request('/api/interview/tests',{});$('test-output').textContent=(result.passed?'PASS':'FAIL')+'\n'+result.output;}
 catch(error){$('test-output').textContent=error.message;}
 finally{$('run-tests').disabled=false;}
};
