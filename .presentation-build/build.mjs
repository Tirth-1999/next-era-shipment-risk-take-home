import fs from 'node:fs/promises';
import path from 'node:path';
import {Presentation, PresentationFile} from '@oai/artifact-tool';
import {resolvePresentationFont, finalizePresentation} from '/Users/tirthcshah/.codex/plugins/cache/openai-primary-runtime/presentations/26.909.12148/skills/presentations/container_tools/artifact_tool_utils.mjs';
const root=process.cwd();
const dir=path.join(root,'.presentation-build');
const skill='/Users/tirthcshah/.codex/plugins/cache/openai-primary-runtime/presentations/26.909.12148/skills/presentations';
const evaluation=JSON.parse(await fs.readFile(path.join(root,'outputs/final_model/evaluation.json'),'utf8'));
const validation=JSON.parse(await fs.readFile(path.join(root,'outputs/notebook_results/validation_selection.json'),'utf8'));
const heading=resolvePresentationFont({fontFamily:'Georgia'});
const body=resolvePresentationFont({fontFamily:'Arial'});
const C={paper:'#F5F4EF',green:'#203B33',ink:'#222B2B',muted:'#657372',lime:'#DAEB9C',pale:'#E8EEDC',white:'#FFFFFF',line:'#DFE4D7'};
const deck=Presentation.create({slideSize:{width:1280,height:720}});
const all=[];
function text(s,value,x,y,w,h,size=26,color=C.ink,font=body,bold=false){
 const shape=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 shape.text=value;shape.text.style={typeface:font,fontSize:size,color,bold,autoFit:'none'};
 return shape;
}
function slide(title,notes,dark=false){
 const s=deck.slides.add();s.background.fill=dark?C.green:C.paper;all.push(s);
 if(title)text(s,title,70,50,1130,100,48,dark?C.white:C.green,heading);
 text(s,`${String(all.length).padStart(2,'0')}`,1160,665,50,28,16,dark?C.lime:C.muted);
 s.speakerNotes.textFrame.setText(notes);
 return s;
}
function table(s,values,y=205,widths=[500,300,300],highlight=-1){
 const height=values.length*61;
 const t=s.tables.add({rows:values.length,columns:values[0].length,left:70,top:y,width:1140,height,columnWidths:widths,values});
 t.borders.assign({fill:C.line,width:1,style:'solid'});
 for(let r=0;r<values.length;r++){
  t.rows[r].height=61;
  for(let c=0;c<values[0].length;c++){
   const cell=t.getCell(r,c);cell.fill=r===0?C.green:r===highlight?C.pale:C.white;
   cell.text.style={typeface:body,fontSize:24,color:r===0?C.white:C.ink,bold:r===0||r===highlight,autoFit:'none'};
  }
 }
 return t;
}
let s=slide('',`This is an optional interview presentation for the refrigerated-shipment risk exercise. The assignment asks for a local engine, not a UI or slides. These materials support the discussion and are separate from the assessed implementation.\nSource: README.md, DECISIONS.md, demo/style.css.`,true);
text(s,'SHIPMENT RISK LAB',76,80,900,50,23,C.lime,body);
text(s,'Risk at the\ndecision time',70,205,1080,200,82,C.white,heading);
text(s,'A six-hour incident forecast using the information available then',76,462,1020,85,30,C.white);
text(s,'Tirth Shah',76,612,600,40,24,C.lime);

s=slide('A late correction cannot rewrite earlier knowledge',`Use the example from notebooks 02–04 and the UI lesson. The original measurement is 8°C at 9 AM, available at 9:05. The correction is 5°C and arrives at noon. At 11 AM we must still use 8°C. Receipt controls availability. Device time defines measurement age and the lookback. Duplicates with the same event/revision add no measurements. At noon the 9 AM point sits on the open left edge of the three-hour window, so it may supply latest temperature but not window summaries. Historical reconstruction also depends on retaining the relevant records.\nSources: notebooks/02_duplicates_and_revisions.ipynb, src/dispatch_risk/features.py, demo/server.py.`);
text(s,'One reading, two revisions',70,163,1060,45,27,C.muted);
table(s,[['Prediction time','Available value','Reason'],['09:00','No reading','Receipt is at 09:05'],['11:00','8°C','Correction has not arrived'],['12:00','5°C','Correction is now available']],230,[300,290,550],2);
text(s,'All example times are UTC. Receipt time determines what the platform could know.',70,550,1120,65,24,C.green);

s=slide('Nine temperature and freshness features',`Explain feature engineering before model weights. Features are deterministic descriptions of available telemetry. Latest temperature can be outside the lookback and is flagged stale after three hours. Mean weights observations equally. Trend uses least squares over actual elapsed hours and needs two distinct times. All raw numeric features feed a fitted imputer and nine missing indicators. Logistic regression also uses training-fitted scaling. The engine rejects measurements ahead of their receipt time without reviving a superseded revision. Door, compressor and location events are not model features in this version.\nSources: src/dispatch_risk/features.py, src/dispatch_risk/training.py.`);
text(s,'Current reading',70,192,480,50,34,C.green,heading);
text(s,'Latest temperature\nMeasurement age\nArrival delay\nMissing-temperature indicator',70,270,500,235,29);
text(s,'Three-hour lookback',690,192,510,50,34,C.green,heading);
text(s,'Reading count\nMean and maximum temperature\nTemperature trend\nObservation span',690,270,510,235,29);
text(s,'Missing trend means insufficient timing evidence. A measured zero trend means flat readings.',70,565,1120,70,25,C.muted);

s=slide('Training waits for the outcome and its report',`A Monday 11 AM decision has a horizon ending Monday 5 PM. The 48-hour grace makes the row eligible Wednesday 5 PM. Apply the gate to both classes and restrict reports to the relevant label cutoff. Absence of a report becomes an assumed negative only for a mature row. Split shipments by their first decision timestamp, approximately 60/20/20, and keep a shipment in one group. The builder currently omits immature checkpoints and records counts. The interface has no observation cutoff, so max decision time supplies an explicit assumption. This is a contract concern to discuss, not certified audit coverage.\nSources: src/dispatch_risk/training.py, outputs/notebook_results/split_policy.json, DECISIONS.md.`);
text(s,'6 hours of follow-up + 48 hours for reporting',70,163,1140,55,32,C.green);
table(s,[['Partition','Purpose','Reports available by'],['Training','Fit preprocessing and model','Validation start'],['Validation','Choose the model','Test start'],['Test','Evaluate the fixed choice','Observation cutoff']],250,[270,470,400]);
text(s,'Chronological shipment groups keep the same shipment out of both fitting and evaluation.',70,530,1120,60,25);
text(s,'The 48-hour completeness rule and the observation cutoff remain assumptions.',70,610,1120,35,22,C.muted);

s=slide('Logistic regression met the declared selection rule',`The validation comparison used 1,026 training rows and 306 validation rows with 21 incidents. Each candidate fit its preprocessing on the same training partition. The rule required improvement on constant AP and Brier, then selected the simplest candidate within 0.002 Brier of the best eligible score. Simplicity order was logistic, shallow tree, forest, boosting. Boosting had higher AP, while logistic had lower Brier and won the declared rule. This is an engineering preference, not a statistical significance claim. We did not pick again after seeing test results.\nSource: outputs/notebook_results/validation_selection.json.`);
const names={constant:'Constant baseline',logistic_regression:'Logistic regression',shallow_tree:'Shallow tree',random_forest:'Random forest',gradient_boosting:'Gradient boosting'};
table(s,[['Validation candidate','Average precision','Brier score'],...validation.validation_results.map(r=>[names[r.model],r.average_precision.toFixed(4),r.brier.toFixed(5)])],190,[570,290,280],2);
text(s,'Beat the baseline on both metrics, then choose the simplest within 0.002 of the best Brier score.',70,580,1130,65,24,C.green);

s=slide('Held-out performance against the baseline',`After selection, refit logistic regression on 1,386 mature development rows at test start. Held-out evaluation has 309 checkpoints from 104 shipments and 25 positives. AP is a ranking measure. Brier and log loss assess probability error, but Brier alone does not certify calibration. At the illustrative 20% threshold there are 24 TP, 0 FP and 1 FN, giving recall 0.96 and precision 1.0. Constant test AP is 0.080906 and Brier 0.074380. Source, freshness and trend-availability slices exist in the report. The coast-source slice has 14 incidents and Brier about 0.00992, illustrating that pooled scores hide variation. Small synthetic data and assumed negatives limit generalization.\nSources: outputs/final_model/evaluation.json, notebooks/13_final_evaluation_and_model_artifact.ipynb.`);
text(s,'309 held-out checkpoints with 25 incidents',70,165,1100,52,29,C.muted);
table(s,[['Test metric','Logistic regression','Constant baseline'],['Average precision',evaluation.test.average_precision.toFixed(4),evaluation.constant_test.average_precision.toFixed(4)],['Brier score',evaluation.test.brier.toFixed(5),evaluation.constant_test.brier.toFixed(5)],['Log loss',evaluation.test.log_loss.toFixed(4),evaluation.constant_test.log_loss.toFixed(4)]],240,[520,320,300]);
text(s,'At a 20% threshold: 24 incidents detected, 1 missed, 0 false alarms.',70,526,1120,55,28,C.green);
text(s,'Synthetic data. The threshold is illustrative. Real shipment performance remains untested.',70,603,1120,45,23,C.muted);

s=slide('Bounded history and safe model reload',`The state uses at most max_shipments shipment records and at most 128 revision records per shipment, plus a bounded event-ID index. Each event is limited to 16 KiB. This bounds structures, not exact process RSS. Eviction removes shipment history and its identity entries. History loss produces degraded reasons. Duplicate recognition cannot extend across eviction without unbounded tombstones. A single RLock protects scoring and state transitions. Reload validates a candidate before swapping the immutable model. Failure keeps the old model, and initial load failure raises. Snapshots capture LRU order, records, counters and model version before atomic file replacement. Restore requires the same model version.\nEvidence: 27 tests passed after the UI addition. The core replay audit is in outputs/final_model/verification.json, which records 20 tests at that earlier stage. A different stream had 12,881 deliveries and respected capacity 32.\nSources: src/dispatch_risk/engine.py, tests/test_engine.py, tests/test_demo.py, MY_LEARNINGS.md checkpoint 17.`);
text(s,'32',70,180,300,115,80,C.green,heading);
text(s,'shipments in the capacity stress check',70,308,480,65,27);
text(s,'128',700,180,300,115,80,C.green,heading);
text(s,'revision records allowed per shipment',700,308,480,65,27);
text(s,'Identical replays produce identical prediction and snapshot bytes.',70,426,1110,55,29);
text(s,'A failed model reload leaves the previous model and telemetry intact.',70,498,1110,55,29);
text(s,'Discarded history limits reconstruction. The prediction exposes that limitation.',70,584,1120,55,24,C.muted);

s=slide('The remaining engineering priorities',`These are priorities, not completed upgrades. First, align the builder with the requested per-decision row contract. The current binary TrainingRow cannot honestly represent an unknown outcome, and omitting immature rows is a documented interpretation. An explicit observation cutoff and a separate censored-result record would make the contract clearer if the interface can be extended. Until then, retain disclosure and focused tests rather than relabel unknowns as zero. Second, benchmark hot-shipment scoring, snapshot pause duration, concurrent reload latency and actual RSS. Third, validate on audited real data across multiple time periods, check calibration and choose thresholds based on incident cost and response capacity. Additional hardening includes snapshot byte limits and extreme-input cases. Python 3.11 is declared but only 3.14 was tested here.\nSources: README.md, DECISIONS.md, src/dispatch_risk/training.py, src/dispatch_risk/engine.py, outputs/final_model/verification.json.`);
text(s,'Before submission',70,188,350,50,31,C.green,heading);
text(s,'Resolve or explicitly defend omitted immature rows. The README requests a row at every decision time.',460,188,720,95,27);
text(s,'Before scaling',70,339,350,50,31,C.green,heading);
text(s,'Measure process memory and scoring latency under load. Bound snapshot input size and test the minimum Python version.',460,339,720,110,27);
text(s,'Before real use',70,510,350,50,31,C.green,heading);
text(s,'Confirm outcome coverage, validate on real shipments and set alert thresholds from operational costs.',460,510,720,100,27);

s=slide('The live walkthrough makes each decision visible',`Open the local UI before the presentation. Run PYTHONPATH=src .venv/bin/python -m demo.server if necessary. Start in The late correction with capacity two, shipment-A, 11 AM and follow-time unchecked. The first click is a duplicate. The second is the noon correction. Show unchanged digest and prediction at 11 AM, then score at noon. Show feature boundaries as needed. Save before stepping into eviction, then restore and read the byte-identity message. Try invalid reload and show that the score remains unchanged. Each tab has independent playback. If the browser is unavailable use RUNBOOK.md and the CLI. Ask the panel which requirement they would like to change.\nSources: demo/README.md, demo/server.py, RUNBOOK.md.`,true);
text(s,'1  Inspect the 8°C reading at 11 AM',76,196,1110,55,32,C.white);
text(s,'2  Deliver the duplicate and noon correction',76,277,1110,55,32,C.white);
text(s,'3  Compare the 11 AM and noon predictions',76,358,1110,55,32,C.white);
text(s,'4  Demonstrate eviction, restore and failed reload',76,439,1110,55,32,C.white);
text(s,'http://127.0.0.1:8765',76,566,1100,60,33,C.lime);

await fs.mkdir(dir,{recursive:true});
await (await PresentationFile.exportPptx(deck)).save(path.join(dir,'candidate.pptx'));
for(let i=0;i<all.length;i++){
 const png=await deck.export({slide:all[i],format:'png',scale:1});
 await fs.writeFile(path.join(dir,`slide-${i+1}.png`),new Uint8Array(await png.arrayBuffer()));
}
const result=await finalizePresentation({workspaceDir:root,candidatePath:path.join(dir,'candidate.pptx'),finalPath:path.join(root,'outputs/presentation/Shipment_Risk_Interview.pptx'),pythonExecutable:'/Users/tirthcshah/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3',integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',...[2,4,5,6].flatMap(n=>['--require-native-table-slide',String(n)])],requiredNativeTableOwnerSlides:[2,4,5,6],fontPolicy:{basis:'design',families:[heading,body]},verifyArtifactToolImport:true,receiptPath:path.join(dir,'validation.json')});
console.log(JSON.stringify(result));
