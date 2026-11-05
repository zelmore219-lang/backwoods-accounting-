const $=id=>document.getElementById(id);let last;
function render(s){last=s;const busy=['checking','downloading','installing'].includes(s.phase);$('phase').textContent=s.phase;$('current').textContent=s.currentVersion;$('latest').textContent=s.latestVersion||'—';$('message').textContent=s.message;$('notes').textContent=s.notes||'Check for an update to see release notes.';
 if(document.activeElement!==$('feed'))$('feed').value=s.feedUrl;$('enabled').checked=s.enabled;$('auto').checked=s.autoDownload;
 for(const id of ['save','check','feed','enabled','auto'])$(id).disabled=busy;
 $('download').disabled=busy||s.phase!=='available';$('install').disabled=busy||s.phase!=='downloaded';$('progress').hidden=s.phase!=='downloading';$('progress').value=s.percent||0;
}
async function action(name,value){try{render(await window.updates.action(name,value));}catch(e){$('message').textContent=e.message;}}
$('save').onclick=()=>action('configure',{feedUrl:$('feed').value,enabled:$('enabled').checked,autoDownload:$('auto').checked});
for(const name of ['check','download','install'])$(name).onclick=()=>action(name);
window.updates.onState(render);action('status');
