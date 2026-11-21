import {mkdir,writeFile,rename} from 'node:fs/promises';import {DATA_DIR} from './server.mjs';import {validateSnapshot} from './finance.mjs';
let input='';for await(const c of process.stdin){input+=c;if(input.length>5000000)throw Error('Snapshot too large');}
const snapshot=validateSnapshot(JSON.parse(input));await mkdir(DATA_DIR,{recursive:true,mode:0o700});
const temporary=DATA_DIR+'/snapshot-'+process.pid+'.tmp';await writeFile(temporary,JSON.stringify(snapshot),{mode:0o600,flag:'wx'});await rename(temporary,DATA_DIR+'/snapshot.json');console.log('Verified monthly snapshot saved.');
