import fs from 'node:fs/promises';
import {PresentationFile,FileBlob} from '@oai/artifact-tool';
const p=await PresentationFile.importPptx(await FileBlob.load('outputs/presentation/Shipment_Risk_Interview.pptx'));
for(let i=0;i<9;i++){
 const png=await p.export({slide:p.slides.getItem(i),format:'png',scale:1});
 await fs.writeFile(`.presentation-build/final-${i+1}.png`,new Uint8Array(await png.arrayBuffer()));
}
