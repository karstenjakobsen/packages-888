import {createServer} from 'node:http';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {randomBytes,scryptSync,timingSafeEqual} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {monthKey,validateSnapshot} from './finance.mjs';
export const DATA_DIR=process.env.MONEY_DATA_DIR||'/home/swarm/packages/4c2d0475-8c2c-4dd5-a040-c84f3d543ac6/money-data';
const ORIGIN='https://money.karstenjakobsen.dk';
export function createService({dataDir=DATA_DIR}={}) {
 const sessions=new Map(),attempts=new Map();
 const json=(res,status,obj)=>{res.writeHead(status,{'content-type':'application/json'});res.end(JSON.stringify(obj));};
 async function settings(){try{return JSON.parse(await readFile(dataDir+'/settings.json','utf8'));}catch{return {};}}
 return createServer(async(req,res)=>{
  res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('Referrer-Policy','no-referrer');
  res.setHeader('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'");
  try{
   const p=new URL(req.url,'http://localhost').pathname;
   const method=req.method;
   if(method==='GET'&&p==='/healthz')return json(res,200,{status:'ok',service:'money',month:monthKey()});
   if(method==='GET'&&p==='/api/status'){const s=await settings();return json(res,200,{month:monthKey(),passwordConfigured:!!s.passwordHash,bilance:'Authorization required in operator Connections',domain:ORIGIN});}
   if(method==='POST'&&p==='/api/login'){
    if(req.headers.origin!==ORIGIN)return json(res,403,{error:'Invalid origin'});
    if(req.headers['content-type']!=='application/json')return json(res,415,{error:'Expected JSON'});
    const ip=req.socket.remoteAddress, a=attempts.get(ip)||{count:0,until:Date.now()+60000};
    if(a.until<Date.now()){a.count=0;a.until=Date.now()+60000;}a.count++;attempts.set(ip,a);
    if(a.count>10)return json(res,429,{error:'Please wait a minute before trying again.'});
    const s=await settings();if(!s.passwordHash)return json(res,503,{error:'Dashboard access is awaiting owner configuration.'});
    let body='';for await(const c of req){body+=c;if(body.length>2048)return json(res,413,{error:'Request too large'});}
    const password=JSON.parse(body).password;
    if(typeof password!=='string')return json(res,400,{error:'Password required'});
    const [salt,hash]=s.passwordHash.split(':');const expected=Buffer.from(hash||'','hex'),actual=scryptSync(password,salt||'',64);
    if(expected.length!==actual.length||!timingSafeEqual(expected,actual))return json(res,401,{error:'Incorrect password'});
    const token=randomBytes(32).toString('hex');for(const [k,v]of sessions)if(v<Date.now())sessions.delete(k);
    if(sessions.size>1000)sessions.clear();sessions.set(token,Date.now()+3600000);
    res.setHeader('Set-Cookie','money_session='+token+'; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=3600');
    return json(res,200,{ok:true});
   }
   if(p==='/api/finances'&&method==='GET'){
    const token=(req.headers.cookie||'').split(';').map(s=>s.trim()).find(s=>s.startsWith('money_session='))?.slice(14);
    if(!token||!(sessions.get(token)>Date.now()))return json(res,401,{error:'Sign in to view your finances.'});
    try{const s=validateSnapshot(JSON.parse(await readFile(dataDir+'/snapshot.json','utf8')));return json(res,200,s);}
    catch{return json(res,503,{error:'No verified Bilance snapshot is available for this month. Complete OAuth and run the monthly sync.'});}
   }
   if(p==='/api/logout'&&method==='POST'){
    if(req.headers.origin!==ORIGIN)return json(res,403,{error:'Invalid origin'});
    const token=(req.headers.cookie||'').split(';').map(s=>s.trim()).find(s=>s.startsWith('money_session='))?.slice(14);
    sessions.delete(token);res.setHeader('Set-Cookie','money_session=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0');return json(res,200,{ok:true});
   }
   const assets={'/':['index.html','text/html; charset=utf-8'],'/app.js':['app.js','text/javascript; charset=utf-8'],'/style.css':['style.css','text/css; charset=utf-8']};
   if(method==='GET'&&assets[p]){const [f,mime]=assets[p];res.writeHead(200,{'content-type':mime});return res.end(await readFile(new URL('./'+f,import.meta.url)));}
   json(res,404,{error:'Not found'});
  }catch{if(!res.headersSent)json(res,400,{error:'Request could not be processed'});else res.end();}
 });
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 await mkdir(DATA_DIR,{recursive:true,mode:0o700});
 await writeFile(DATA_DIR+'/settings.json',JSON.stringify({passwordHash:'',bilanceConnectionId:'5d1f6428-8b8a-4fdf-bde4-717669b9eb17'},null,2),{flag:'wx',mode:0o600}).catch(e=>{if(e.code!=='EEXIST')throw e;});
 const server=createService();server.listen(Number(process.env.PORT||3187),'127.0.0.1');
 for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>server.close(()=>process.exit(0)));
}
