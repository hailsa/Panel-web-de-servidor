const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function element(){
  const classes=new Set();
  return {children:[],dataset:{},textContent:'',innerHTML:'',
    classList:{add:name=>classes.add(name),remove:name=>classes.delete(name),contains:name=>classes.has(name),toggle(name,on){if(on===undefined)on=!classes.has(name);on?classes.add(name):classes.delete(name);}},
    setAttribute(){},addEventListener(){},contains(){return false;},
    append(...children){for(const child of children){child.parent=this;this.children.push(child);}},
    prepend(child){child.parent=this;this.children.unshift(child);},
    get lastElementChild(){return this.children.at(-1);},
    remove(){if(this.parent)this.parent.children=this.parent.children.filter(child=>child!==this);}};
}
const nodes=new Map(),storage=new Map(),timers=[];
const get=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);};
get('notification-panel').classList.add('hidden');
const document={getElementById:get,querySelector:get,querySelectorAll:()=>[],addEventListener(){},documentElement:{dataset:{}},body:element(),createElement:element};
const context={document,localStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value)},
  window:{matchMedia:()=>({matches:false}),addEventListener(){}},Intl,Date,Math,Set,
  setInterval:()=>1,setTimeout:(callback,delay)=>{timers.push({callback,delay});return 1;},
  fetch:async()=>({ok:true,json:async()=>({})})};
vm.runInNewContext(fs.readFileSync('dashboard/app/static/js/base.js','utf8'),context);
context.window.SHC.notify({title:'VM · sample',message:'Estado confirmado',severity:'success'});
assert.equal(get('notification-toasts').children.length,1);
const removal=timers.find(timer=>timer.delay===5000);assert.ok(removal,'toast must expire at five seconds');removal.callback();
assert.equal(get('notification-toasts').children.length,0);
let history=JSON.parse(storage.get('shc-notifications-v1'));
assert.equal(history[0].title,'VM · sample');assert.equal(history[0].read,false);
get('notifications').onclick({stopPropagation(){}});
history=JSON.parse(storage.get('shc-notifications-v1'));assert.equal(history[0].read,true);
assert.equal(history[0].resolved,false,'activity must not be resolved as a hardware alert');
setImmediate(()=>{
  const saved=JSON.parse(storage.get('shc-notifications-v1'));
  assert.ok(saved.some(item=>item.title==='VM · sample'&&!item.resolved),'alert refresh must preserve activity history');
  console.log('Notifications: 5-second expiry, saved history, unread/read and alert refresh OK');
});
