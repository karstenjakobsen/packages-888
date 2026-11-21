import {readFile,writeFile,mkdir} from 'node:fs/promises';import {randomBytes,scryptSync} from 'node:crypto';import {DATA_DIR} from './server.mjs';
let input='';for await(const c of process.stdin)input+=c;
const password=input.trim();if(password.length<16)throw Error('Use at least 16 characters. Supply through stdin; never command arguments.');
await mkdir(DATA_DIR,{recursive:true,mode:0o700});let config={};try{config=JSON.parse(await readFile(DATA_DIR+'/settings.json','utf8'));}catch{}
const salt=randomBytes(16).toString('hex');config.passwordHash=salt+':'+scryptSync(password,salt,64).toString('hex');
await writeFile(DATA_DIR+'/settings.json',JSON.stringify(config,null,2),{mode:0o600});console.log('Dashboard password configured.');
