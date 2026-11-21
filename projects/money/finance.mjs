export function monthKey(now = new Date()) { return new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Copenhagen',year:'numeric',month:'2-digit'}).format(now).replace('/', '-'); }
export function validateSnapshot(s, now = new Date()) {
 if(!s || s.version!==1 || s.source!=='Bilance' || s.month!==monthKey(now)) throw Error('Snapshot must be verified Bilance data for the current Copenhagen calendar month.');
 if(!/^[A-Z]{3}$/.test(s.currency) || !Number.isFinite(Date.parse(s.checkedAt)) || Date.parse(s.checkedAt)>now.getTime()+60000) throw Error('Invalid currency or observation time.');
 for(const k of ['income','expenses']) if(!Number.isFinite(s[k]) || s[k]<0) throw Error('Invalid totals');
 for(const k of ['categories','transactions','accounts','budgets']) if(!Array.isArray(s[k]) || s[k].length>10000) throw Error('Invalid '+k);
 const str=(v)=>typeof v==='string'&&v.length<500;
 for(const c of s.categories) if(!str(c.name)||!Number.isFinite(c.amount)||c.amount<0) throw Error('Invalid category');
 for(const t of s.transactions) if(!str(t.description)||!str(t.category)||!/^\d{4}-\d{2}-\d{2}$/.test(t.date)||t.date.slice(0,7)!==s.month||!Number.isFinite(t.amount)) throw Error('Invalid transaction');
 for(const a of s.accounts) if(!str(a.name)||!Number.isFinite(a.balance)) throw Error('Invalid account');
 for(const b of s.budgets) if(!str(b.name)||!Number.isFinite(b.spent)||!Number.isFinite(b.limit)||b.limit<=0||b.spent<0) throw Error('Invalid budget');
 if(typeof s.transactionsComplete!=='boolean') throw Error('Declare transaction completeness');
 return s;
}
