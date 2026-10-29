/* Disabled controls need a hover/focus target because native buttons cannot focus. */
(() => {
let tooltip=null,active=null;
function hide(){if(tooltip)tooltip.hidden=true;active=null;}
function show(wrapper){
  if(!wrapper?.dataset.disabledReason)return;
  if(!tooltip){tooltip=document.createElement('div');tooltip.id='vm-disabled-tooltip';tooltip.className='vm-disabled-tooltip';tooltip.role='tooltip';document.body.append(tooltip);}
  const layer=wrapper.closest('dialog[open]')||document.body;
  if(tooltip.parentElement!==layer)layer.append(tooltip);
  active=wrapper;tooltip.textContent=wrapper.dataset.disabledReason;tooltip.hidden=false;
  const rect=wrapper.getBoundingClientRect(),box=tooltip.getBoundingClientRect();
  tooltip.style.left=`${Math.max(8,Math.min(innerWidth-box.width-8,rect.left))}px`;
  tooltip.style.top=`${rect.bottom+box.height+16<innerHeight?rect.bottom+8:Math.max(8,rect.top-box.height-8)}px`;
}
function setUnavailable(button,reason=''){
  if(!button)return;
  if(active&&!active.isConnected)hide();
  let wrapper=button.parentElement;
  if(!wrapper?.classList.contains('vm-control-hint')){
    wrapper=document.createElement('span');wrapper.className='vm-control-hint';
    button.before(wrapper);wrapper.append(button);
  }
  button.disabled=!!reason;
  wrapper.dataset.disabledReason=reason;
  if(reason){
    wrapper.tabIndex=0;wrapper.setAttribute('role','group');
    wrapper.setAttribute('aria-label',`${button.textContent.trim()}: ${reason}`);
    wrapper.setAttribute('aria-describedby','vm-disabled-tooltip');
  }else{
    wrapper.removeAttribute('tabindex');wrapper.removeAttribute('role');
    wrapper.removeAttribute('aria-label');wrapper.removeAttribute('aria-describedby');
  }
  if(active===wrapper){if(reason)show(wrapper);else hide();}
}
document.addEventListener('pointerover',event=>{const wrapper=event.target.closest('.vm-control-hint');if(wrapper&&!wrapper.contains(event.relatedTarget))show(wrapper);});
document.addEventListener('pointerout',event=>{if(active&&!active.contains(event.relatedTarget)&&document.activeElement!==active)hide();});
document.addEventListener('focusin',event=>{const wrapper=event.target.closest('.vm-control-hint');if(wrapper)show(wrapper);else hide();});
document.addEventListener('focusout',()=>hide());
document.addEventListener('keydown',event=>{if(event.key==='Escape')hide();});
document.addEventListener('scroll',hide,true);window.addEventListener('resize',hide);
window.SHC.setUnavailable=setUnavailable;
})();
