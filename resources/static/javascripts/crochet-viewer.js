/*!
 * crochet-viewer.js  -  crochetPARADE-style pattern previewer (parser + stitch graph + relaxation + three.js yarn renderer)
 *
 * Requires (load before this file): three.js r128 and its OrbitControls (examples/js/controls/OrbitControls.js).
 * Sample usage:
 *
 *   <div id="view" style="width:800px;height:600px"></div>
 *   <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
 *   <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
 *   <script src="crochet-viewer.js"></script>
 *   <script>
 *     const v = CrochetViewer.mount(document.getElementById('view'), {
 *       mode: 'yarn',            // 'yarn' | 'graph'
 *       thickness: 0.27,         // yarn radius
 *       iterations: 400,         // relaxation steps
 *       background: null,        // CSS colour, or null for transparent (a BACKGROUND: line in the pattern wins)
 *       onStatus: s => {},       // {rows, stitches, links, iteration, iterations, done, warnings}
 *       onError:  m => {},       // message string, or null when the pattern is fine
 *       onHover:  h => {}        // {row, stitch, id, type} or null
 *     });
 *     const err = v.setPattern('ring\nsc5inc\n...');   // null on success, else an error message
 *     v.setMode('graph'); v.setThickness(0.2); v.setVisibleCount(100); v.dispose();
 *   </script>
 */
;(function(root){
'use strict';
// ---------- stitch table ----------
const HT={ss:.4,ch:1,sc:1,rsc:1,hdc:1.5,dc:2,tr:3,dtr:4,trtr:5,longsc:2,longdc:3,longtr:4};
function stInfo(n,defs){
  const d=defs[n]; if(d){if(d.raw)return{...d.raw,raw:d.raw};const b=stInfo(d.copy,defs); if(d.h)b.h=d.h; return b}
  let q=/^(\w*?)(inc|dec)$/.exec(n);if(q&&!/^(ss|sc|hdc|dc|tr)\d/.test(n)&&(q[1]===''||HT[q[1].replace(/^(fp|bp)/,'')]))return stInfo((q[1]||'sc')+(q[2]==='dec'?'2tog':'2inc'),defs);
  let m=/^(fp|bp)?(ss|sc|hdc|dc|trtr|dtr|tr|ch|rsc|longsc|longdc|longtr)(fl|bl)?(?:(\d+)(inc|tog))?$/.exec(n);
  if(m){const N=+m[4]||1,b=m[2];return{h:HT[b]*(m[1]?.8:1),nb:m[5]==='tog'?N:(b==='ch'?0:1),nt:m[5]==='inc'?N:1}}
  if(n==='ring')return{h:0,nb:0,nt:1};
  m=/^(hdc\d+puff|dc\d+bobble|tr4bobble|dc\d+pc|picot3)$/.exec(n);
  if(m)return{h:/^hdc|picot/.test(n)?1.5:/^tr/.test(n)?3:2,nb:1,nt:1};
  return null;
}
// ---------- parser ----------
function parse(s){
  let i=0;
  const bal=(o,c)=>{let d=0,st=i;for(;i<s.length;i++){if(s[i]===o)d++;else if(s[i]===c&&!--d){const r=s.slice(st+1,i);i++;return r}}throw Error('Unbalanced '+o)};
  const label=()=>{const m=/^[A-Za-z_]\w*/.exec(s.slice(i));const L={name:m?m[0]:''};i+=L.name.length;
    if(s[i]==='[')L.b=bal('[',']'); if(s[i]==='[')L.b2=bal('[',']');
    while(i<s.length&&/[\^!+~]/.test(s[i])){if(s[i]==='~')L.rev=1;i++;while(/\d/.test(s[i]||''))i++}
    return L};
  const out=[];
  while(i<s.length){
    const c=s[i];
    if(c===','||c===' '){i++;continue}
    if(c==='<'||c==='>'){i++;out.push({k:'m',m:c});continue}
    if(c==='$'){const j=s.indexOf('$',i+1);if(j<0)throw Error('Unterminated $');const[n,v]=s.slice(i+1,j).split('=');i=j+1;out.push({k:'v',n:n.trim(),v});continue}
    const it={mult:1,star:0,hasN:0,labels:[],att:null,k:'s',name:''};
    let m=/^\d+/.exec(s.slice(i));
    if(m){it.mult=+m[0];it.hasN=1;i+=m[0].length;while(s[i]===' ')i++;if(s[i]==='*'){it.star=1;i++}}
    if(s[i]==='('||s[i]==='['){it.k='g';it.kids=parse(bal(s[i],s[i]==='('?')':']'));
      if(s[i]==='*'&&/\d/.test(s[i+1]||'')){m=/^\d+/.exec(s.slice(i+1));it.mult=+m[0];it.star=1;i+=1+m[0].length}}
    else if(s[i]!=='@'){m=/^[A-Za-z_]\w*/.exec(s.slice(i));if(!m)throw Error('Unexpected "'+s.slice(i,i+8)+'"');it.name=m[0];i+=m[0].length}
    for(;;){
      if(s[i]==='.'&&/[A-Za-z_]/.test(s[i+1]||'')){i++;it.labels.push(label())}
      else if(s[i]==='@'){i++;const a={head:0};m=/^\d+/.exec(s.slice(i));if(m){a.head=+m[0];i+=m[0].length}
        if(s[i]==='[')a.coord=bal('[',']');else a.label=label();it.att=a}
      else break}
    out.push(it);
  }
  return out;
}
// ---------- expansion (repeats, counters, labels) ----------
function ev(e,cx){
  e=String(e).trim();if(e==='')return'';
  e=e.replace(/(\+\+|--)([A-Za-z_]\w*)|([A-Za-z_]\w*)(\+\+|--)|\b(next|prev)\s+([A-Za-z_]\w*)/g,(m,a,v1,v2,b,w,v3)=>{
    const v=v1||v2||v3,pre=a||w,d=(a?a==='++':w?w==='next':b==='++')?1:-1,o=cx.vars[v]||0;cx.vars[v]=o+d;return pre?o+d:o});
  e=e.replace(/[A-Za-z_]\w*/g,v=>v in cx.vars?cx.vars[v]:v);
  if(!/^[\d+\-*\/%() .]*$/.test(e))throw Error('Bad index expression "'+e+'"');
  return Function('return ('+e+')')()|0;
}
function lab(l,cx){
  if(l.b===undefined)return{key:l.name,rev:l.rev,pos:l.b2===undefined?null:ev(l.b2,cx)};
  const[p,o]=l.b.split(';');
  return{key:l.name+'['+p.split(',').map(x=>ev(x,cx)).join(',')+']',ord:o===undefined?null:ev(o,cx),rev:l.rev,pos:l.b2===undefined?null:ev(l.b2,cx)};
}
function expand(items,cx,out){
  for(const it of items){
    if(it.k==='m'){out.push({m:it.m});continue}
    if(it.k==='v'){cx.vars[it.n]=ev(it.v,cx);continue}
    const reps=(it.k==='g'||it.star)?it.mult:1;
    for(let r=0;r<reps;r++){
      let part=[];
      if(it.k==='g')expand(it.kids,cx,part);else part.push({name:it.name,labels:[],att:null});
      if(it.k==='g'){
        const a=part.findIndex(o=>o.m==='<'),b=part.findIndex(o=>o.m==='>');
        if(r===0&&a>=0)part=part.slice(a+1);
        if(r===reps-1&&b>=0&&(a<0||b>a||r>0))part=part.slice(0,part.findIndex(o=>o.m==='>'));
        part=part.filter(o=>!o.m);
      }
      const L=it.labels.map(l=>lab(l,cx));
      const A=it.att?{head:it.att.head,coord:it.att.coord,lab:it.att.label?lab(it.att.label,cx):null}:null;
      for(const o of part){o.labels.push(...L);if(A&&!o.att)o.att=A}
      out.push(...part);
      if(it.k==='s'&&!it.star&&it.hasN)for(let k=1;k<it.mult;k++)out.push({...part[0],labels:[...part[0].labels]});
    }
  }
}
// ---------- text -> rows ----------
function unroll(t){let o='',i=0;
  while(i<t.length){
    if((i===0||t[i-1]==='\n')&&/^[ \t]*\[/.test(t.slice(i,i+40))){
      let j=t.indexOf('[',i),d=0,k=j,nl=0;
      for(;k<t.length;k++){if(t[k]==='[')d++;else if(t[k]===']'&&!--d)break;else if(t[k]==='\n')nl++}
      const m=/^\s*\*\s*(\d+)/.exec(t.slice(k+1));
      if(nl&&m){o+=(t.slice(j+1,k).trim()+'\n').repeat(+m[1]);i=k+1+m[0].length;continue}}
    o+=t[i++]}
  return o}
function rawDef(sp){
  const q=sp.split(':'),fr=x=>x.split('/').reduce((a,b)=>a/ +b);
  const tops=q[0].split(';').filter(Boolean).map(x=>{const m=/^([^(]+)(?:\((\w*)\))?/.exec(x.trim());return{n:m[1],t:m[2]||'hidden'}});
  const bots=(q[1]||'').split('~')[0].split(';').filter(Boolean).map(x=>x.trim().replace(/\[.*?\]/g,'').replace(/^[\d.]+(?=\D)/,''));
  const others=(q[2]||'').split(';').filter(Boolean).map(x=>x.replace(/\(.*\)/,'').trim());
  const conns=(q[3]||'').split(';').filter(Boolean).map(x=>{x=x.replace(/^\*/,'');const m=/^([^-]+)-([^-]+)-([^-]+)$/.exec(x.trim());if(!m)return null;return{a:m[1],b:m[3],len:m[2]==='skip'?null:fr(m[2])}}).filter(Boolean);
  return{raw:{tops,bots,others,conns,nt:tops.length,nb:bots.length,h:1}}}
const c0=x=>+x[1]>0;
function readPattern(txt){
  const W=[],defs={start_at:rawDef('A(start):B~A-B::!-skip-A;B-0.0001-A')},al={},meta={iterations:500,start:0,bg:null};let color=null;
  txt=unroll(txt.replace(/\\[^\\]*\\/g,' '));
  let L=txt.includes('¶')?txt.split('¶').map(x=>x.replace(/\n/g,' ')):txt.split('\n');
  const lines=[];
  L.forEach((raw,n)=>{raw=raw.replace(/#.*$/,'').trim();if(!raw)return;
    if(raw.startsWith('...')&&lines.length&&!/^[A-Z_]+:/.test(lines[lines.length-1].t)){const p=lines[lines.length-1];p.t+=(p.t.endsWith(',')?'':',')+raw.slice(3);return}
    lines.push({t:raw,n:n+1})});
  const rows=[];const cx={vars:{}};
  for(const ln of lines){
    let t=ln.t,m;
    try{
      if(m=/^(DEF|COLOR|BACKGROUND|DOT|INDEX_ARRAY|SORT_LABEL|TRANSFORM_OBJECT):\s*(.*)$/.exec(t)){
        const v=m[2].trim();
        if(m[1]==='DEF'){
          if(m=/^(\w+)\s*=\s*&([^^]*)\^(.*)$/.exec(v))defs[m[1]]=rawDef(m[3]);
          else if(m=/^(\w+)\s*=\s*Copy\((\w+)(?:\s*,\s*([\d.]+))?/.exec(v))defs[m[1]]={copy:m[2],h:+m[3]||0};
          else if(m=/^(\w+)\s*=\s*(.*)$/.exec(v))al[m[1]]=m[2];}
        else if(m[1]==='COLOR')color=v;
        else if(m[1]==='BACKGROUND')meta.bg=v;
        else if(m[1]==='DOT'){if(m=/^(iterations|start|learning_rate)\s*=\s*([\d.]+)/.exec(v))meta[m[1]]=+m[2];else W.push('Row '+ln.n+': only DOT iterations/start are used')}
        else W.push('Row '+ln.n+': '+m[1]+' is not supported (ignored)');
        continue}
      for(const k in al)t=t.replace(new RegExp('(?<![A-Za-z_.@^!])'+k+'(?![\\w])','g'),al[k]);
      const ops=[];expand(parse(t),cx,ops);
      if(ops.length)rows.push({ops,n:ln.n,color});
    }catch(e){throw Error('Row '+ln.n+': '+e.message)}
  }
  return{rows,defs,meta,warn:W};
}
// ---------- stitch graph ----------
function build(P){
  const nodes=[],edges=[],rows=[],groups={},heads={},warn=[...P.warn];let prev=null,ri=-1,cur;
  const nd=o=>(o.id=nodes.length,nodes.push(o),o);
  const E=(a,b,l,k)=>{if(a&&b&&a!==b)edges.push([a.id,b.id,l,k])};
  const tb=a=>{let t=0;for(let k=a;k<ri;k++)if(rows[k].turn)t++;return t};
  const dir=r=>tb(r)%2?-1:1;
  const at=(r,i)=>rows[r]&&rows[r].tops[i]||null;
  function mv(h,s){h.i+=dir(h.r)*s;const T=rows[h.r].tops;
    if(h.i>=T.length){if(h.r<ri){h.r++;h.i=0}else h.i=T.length-1}
    else if(h.i<0){if(h.r>0){h.r--;h.i=rows[h.r].tops.length-1}else h.i=0}}
  const step=h=>{if(h.fresh)h.fresh=false;else mv(h,1);return at(h.r,h.i)};
  const num=(e,h)=>Function('return ('+String(e).replace(/(^|[^\w)])%/g,'$1'+(cur.tops.length)).replace(/@/g,h?h.i:0)+')')()|0;
  function coord(a,h){
    let s=a.coord,ty=null,m=/^(\w+):(.*)$/.exec(s);if(m){ty=m[1];s=m[2]}
    const parts=s.split(',');let r,c;
    if(parts.length===1){if(!h)throw Error('@ used before an attachment point exists');
      const t={r:h.r,i:h.i,fresh:false};mv(t,num(parts[0].replace(/^\s*@/,'0'),h));
      if(ty){let g=0;while(at(t.r,t.i)&&at(t.r,t.i).t!==ty&&g++<999)mv(t,1)}return t}
    r=num(parts[0].replace(/%/g,'%'),h);if(parts[0].trim()==='%')r=ri;else if(r<0)r=ri+r;
    const row=rows[r];if(!row)throw Error('Row '+r+' does not exist yet');
    let T=ty?row.tops.map((n,i)=>[n,i]).filter(x=>x[0].t===ty).map(x=>x[1]):row.tops.map((n,i)=>i);
    c=num(parts[1],h);if(c<0)c+=T.length;
    return{r,i:T[c],fresh:false}}
  // label sets for a row
  function sets(ops){
    const S={};let last=null;
    ops.forEach(op=>{
      if(op.att&&op.att.lab&&op.att.lab.pos==null){
        const l=op.att.lab,info=stInfo(op.name,P.defs),nb=op.name==='sk'?1:info?info.nb:0;
        if(last&&last.key===l.key&&last.ord===l.ord&&!!last.rev===!!l.rev){last.n+=nb;op.set=last}
        else{last={key:l.key,ord:l.ord,rev:l.rev,n:nb,ops:[]};op.set=last;(S[l.key]=S[l.key]||[]).push(last)}
      }else last=null});
    for(const key in S)S[key].forEach(x=>x.all=S[key]);
  }
  function resolve(list){
    const key=list[0].key,G=groups[key];if(!G||!G.length)throw Error('Label '+key+' not found');
    const ss=list.slice();ss.sort((a,b)=>(a.ord??0)-(b.ord??0));
    const N=ss.reduce((a,b)=>a+b.n,0);
    let g=G.slice();if(tb(g[0].r)%2)g.reverse();
    const pts=[];for(let j=0;j<N;j++){const p=N<2?0:j*(g.length-1)/(N-1),a=Math.floor(p+1e-9),f=p-a;
      if(f<1e-6||a+1>=g.length)pts.push(g[Math.min(a,g.length-1)]);
      else{const hn=nd({hidden:1,r:ri,i:-1,t:'hidden'});E(g[a],hn,f,'a');E(g[a+1],hn,1-f,'a');pts.push(hn)}}
    let o=0;ss.forEach(s=>{s.q=pts.slice(o,o+s.n);o+=s.n;if(s.rev)s.q.reverse()});
  }
  function bottom(op,b,hk){
    const a=op.att;let h=heads[hk];
    if(a&&a.lab){
      if(a.lab.pos!=null){const G=groups[a.lab.key];if(!G)throw Error('Label '+a.lab.key+' not found');return G[a.lab.pos%G.length]}
      if(!op.set.q)resolve(op.set.all);const n=op.set.q.shift();const G=groups[a.lab.key],e=G[G.length-1];
      heads[hk]={r:e.r,i:e.i,fresh:false};return n}
    if(a&&a.coord&&b===0){heads[hk]=coord(a,h);const t=heads[hk];return at(t.r,t.i)}
    if(!h){return null}
    return step(h)}
  for(const R of P.rows){
    ri++;cur={tops:[],turn:false};rows.push(cur);
    heads[0]=ri>0?{r:ri-1,i:rows[ri-1].turn?rows[ri-1].tops.length-1:0,fresh:true}:null;
    try{
    sets(R.ops);
    for(const op of R.ops){
      const nm=op.name,hk=op.att?op.att.head:0;
      if(nm==='turn'){cur.turn=true;continue}
      if(nm===''){if(op.att&&op.att.coord)heads[hk]=coord(op.att,heads[hk]);continue}
      if(nm==='sk'){bottom(op,0,hk);continue}
      if(nm==='tie_up')continue;
      if(nm==='start_anew'||nm==='start_a_new_chain'){prev=null;continue}
      const info=stInfo(nm,P.defs);if(!info)throw Error('Unknown stitch "'+nm+'"');
      if(info.raw){const rw=info.raw,B=[];for(let b=0;b<rw.nb;b++)B.push(bottom(op,b,hk));
        const mp={'!':prev};rw.bots.forEach((n,i)=>mp[n]=B[i]);const T=[];
        rw.tops.forEach(tp=>{const n=nd({r:ri,i:cur.tops.length,t:tp.t==='hidden'?nm:tp.t,col:R.color,hidden:/^(hidden|start)$/.test(tp.t)?1:0});cur.tops.push(n);T.push(n);mp[tp.n]=n});
        rw.others.forEach(o=>mp[o]=nd({hidden:1,r:ri,i:-1,t:'hidden'}));
        rw.conns.forEach(c=>{if(c.len!=null)E(mp[c.a],mp[c.b],c.len,(c.a==='!'||c.b==='!')?'s':'a')});
        if(T.length)prev=T[T.length-1];
        for(const l of op.labels)(groups[l.key]=groups[l.key]||[]).push(...T);
        continue}
      const B=[];for(let b=0;b<info.nb;b++){const n=bottom(op,b,hk);if(n)B.push(n)}
      const T=[];for(let k=0;k<info.nt;k++){const n=nd({r:ri,i:cur.tops.length,t:nm,col:R.color});cur.tops.push(n);T.push(n)}
      E(prev,T[0],1,'s');for(let k=1;k<T.length;k++)E(T[k-1],T[k],1,'s');prev=T[T.length-1];
      if(info.nt>1)T.forEach(t=>E(B[0],t,info.h,'a'));else B.forEach(b=>E(b,T[0],info.h,'a'));
      for(const l of op.labels)(groups[l.key]=groups[l.key]||[]).push(...T);
    }}catch(e){throw Error('Row '+R.n+': '+e.message)}
  }
  edges.sort((a,b)=>Math.max(a[0],a[1])-Math.max(b[0],b[1]));
  return{nodes,edges,rows,warn};
}
// ---------- layout ----------
function layout(G,P){
  const{nodes,edges,rows}=G,n=nodes.length,X=new Float32Array(3*n);
  let s=(P.meta.start|0)+1;const rnd=()=>(s=Math.imul(s^s>>>15,1|s)+0x6D2B79F5|0,((s^s>>>7)>>>0)/4294967296);
  rows.forEach((R,r)=>{const m=R.tops.length,flat=R.turn||(r>0&&rows[r-1].turn);let t=0;for(let k=0;k<r;k++)if(rows[k].turn)t++;
    R.tops.forEach((nn,i)=>{const o=3*nn.id;
      if(flat){X[o]=(t%2?-1:1)*(i-(m-1)/2);X[o+1]=r*.9;X[o+2]=0}
      else{const a=2*Math.PI*(i+.5)/m,q=Math.max(m/(2*Math.PI),.3);X[o]=q*Math.cos(a);X[o+1]=r*.9;X[o+2]=q*Math.sin(a)}
      X[o]+=(rnd()-.5)*.2;X[o+1]+=(rnd()-.5)*.2;X[o+2]+=(rnd()-.5)*.2})});
  nodes.forEach(nn=>{if(nn.hidden){const e=edges.find(e=>e[0]===nn.id||e[1]===nn.id);if(e){const o=e[0]===nn.id?e[1]:e[0];for(let k=0;k<3;k++)X[3*nn.id+k]=X[3*o+k]}}});
  const adj=new Set();edges.forEach(e=>{adj.add(e[0]*n+e[1]);adj.add(e[1]*n+e[0])});
  const S=1<<14,head=new Int32Array(S),nxt=new Int32Array(n),R=.8;
  return function relax(iters){
    for(let it=0;it<iters;it++){
      for(const[a,b,l]of edges){const i=3*a,j=3*b,dx=X[j]-X[i],dy=X[j+1]-X[i+1],dz=X[j+2]-X[i+2],d=Math.hypot(dx,dy,dz)||1e-6,f=.45*(d-l)/d;
        X[i]+=dx*f;X[i+1]+=dy*f;X[i+2]+=dz*f;X[j]-=dx*f;X[j+1]-=dy*f;X[j+2]-=dz*f}
      head.fill(-1);
      const H=(x,y,z)=>((x*73856093)^(y*19349663)^(z*83492791))&(S-1);
      for(let i=0;i<n;i++){const h=H(Math.floor(X[3*i]/R),Math.floor(X[3*i+1]/R),Math.floor(X[3*i+2]/R));nxt[i]=head[h];head[h]=i}
      for(let i=0;i<n;i++){const cx=Math.floor(X[3*i]/R),cy=Math.floor(X[3*i+1]/R),cz=Math.floor(X[3*i+2]/R);
        for(let a=-1;a<2;a++)for(let b=-1;b<2;b++)for(let c=-1;c<2;c++)for(let j=head[H(cx+a,cy+b,cz+c)];j>=0;j=nxt[j]){
          if(j<=i||adj.has(i*n+j))continue;
          const dx=X[3*j]-X[3*i],dy=X[3*j+1]-X[3*i+1],dz=X[3*j+2]-X[3*i+2],d=Math.hypot(dx,dy,dz);
          if(d<R&&d>1e-6){const f=.25*(R-d)/d;X[3*i]-=dx*f;X[3*i+1]-=dy*f;X[3*i+2]-=dz*f;X[3*j]+=dx*f;X[3*j+1]+=dy*f;X[3*j+2]+=dz*f}}}
    }
    return X}
}


/* ===================== viewer (three.js r128 + OrbitControls) ===================== */
const DEF_YARN='#d8c3a0';
function mount(el,opts){
  opts=opts||{};
  const T=opts.THREE||root.THREE;
  if(!T)throw new Error('CrochetViewer: three.js not found. Load three.js (r128) first, or pass {THREE}.');
  const OC=opts.OrbitControls||T.OrbitControls;
  if(!OC)throw new Error('CrochetViewer: OrbitControls not found. Load examples/js/controls/OrbitControls.js, or pass {OrbitControls}.');
  const o=Object.assign({mode:'yarn',thickness:.27,iterations:400,background:null,defaultColor:DEF_YARN,onStatus:null,onHover:null,onError:null},opts);
  const R=new T.WebGLRenderer({antialias:true,alpha:true}),S=new T.Scene(),cam=new T.PerspectiveCamera(45,1,.1,3000),
    ctl=new OC(cam,R.domElement),tmp=new T.Object3D(),ray=new T.Raycaster(),mp=new T.Vector2(),
    Yax=new T.Vector3(0,1,0),va=new T.Vector3(),vb=new T.Vector3(),vd=new T.Vector3(),vs=new T.Vector3();
  let G,P,X,mesh,lines,vis=[],job=0,yarn,joints,segs,prevOf,show=Infinity,raf=0,dead=false;
  el.appendChild(R.domElement);R.domElement.style.display='block';
  S.add(new T.HemisphereLight(0xffffff,0x666666,1));const dl=new T.DirectionalLight(0xffffff,1);dl.position.set(1,2,3);S.add(dl);
  const size=()=>{const w=el.clientWidth||300,h=el.clientHeight||300;R.setSize(w,h);cam.aspect=w/h;cam.updateProjectionMatrix()};
  let ro=null;if(typeof ResizeObserver!=='undefined'){ro=new ResizeObserver(size);ro.observe(el)}else root.addEventListener('resize',size);size();
  const yTex=(()=>{const c=document.createElement('canvas');c.width=32;c.height=64;const g=c.getContext('2d');g.fillStyle='#f7f7f7';g.fillRect(0,0,32,64);g.strokeStyle='#cdcdcd';g.lineWidth=6;
    for(let k=-64;k<64;k+=16){g.beginPath();g.moveTo(k,0);g.lineTo(k+32,64);g.stroke()}
    const t=new T.CanvasTexture(c);t.wrapS=t.wrapT=T.RepeatWrapping;t.repeat.set(1,2);t.anisotropy=4;return t})();
  const yMat=new T.MeshStandardMaterial({map:yTex,bumpMap:yTex,bumpScale:.8,roughness:1});
  const colr=(c,d)=>{try{return new T.Color(c||d||o.defaultColor)}catch(e){return new T.Color(d||o.defaultColor)}};
  const err=m=>{o.onError&&o.onError(m)};
  const status=(left,tot)=>{o.onStatus&&o.onStatus({rows:G.rows.length,stitches:vis.length,links:G.edges.length,iteration:tot-left,iterations:tot,done:left===0,warnings:G.warn.slice()})};
  function fit(){if(!vis.length)return;const b=new T.Box3();vis.forEach(n=>b.expandByPoint(tmp.position.set(X[3*n.id],X[3*n.id+1],X[3*n.id+2])));
    const c=b.getCenter(new T.Vector3()),r=b.getSize(new T.Vector3()).length()/2||3;ctl.target.copy(c);
    cam.position.copy(c).add(new T.Vector3(.4,.5,1).normalize().multiplyScalar(r*2.4));cam.far=r*20;cam.updateProjectionMatrix()}
  function hide(q){tmp.scale.set(0,0,0);tmp.position.set(0,0,0);tmp.updateMatrix();yarn.setMatrixAt(q,tmp.matrix)}
  function draw(){
    if(!mesh)return;
    const k=Math.min(show,vis.length),lim=k>=vis.length?1e9:vis[k].id,yr=o.thickness,ym=o.mode!=='graph';
    yarn.visible=joints.visible=ym;mesh.visible=lines.visible=!ym;
    if(ym){
      joints.count=k;tmp.quaternion.identity();
      vis.forEach((n,j)=>{tmp.position.set(X[3*n.id],X[3*n.id+1],X[3*n.id+2]);tmp.scale.setScalar(yr*1.15);tmp.updateMatrix();joints.setMatrixAt(j,tmp.matrix)});
      joints.instanceMatrix.needsUpdate=true;
      segs.forEach((s,q)=>{
        if(s.id>=lim)return hide(q);
        va.set(X[3*s.i],X[3*s.i+1],X[3*s.i+2]);vb.set(X[3*s.j],X[3*s.j+1],X[3*s.j+2]);
        if(s.leg){vd.subVectors(vb,va).normalize();const p=prevOf[s.j];
          if(p>=0)vs.set(X[3*s.j]-X[3*p],X[3*s.j+1]-X[3*p+1],X[3*s.j+2]-X[3*p+2]);else vs.set(1,0,0);
          vs.addScaledVector(vd,-vs.dot(vd));if(vs.lengthSq()<1e-8)vs.set(vd.y,-vd.x,0);
          vs.normalize().multiplyScalar(s.leg*yr*1.5);vb.add(vs)}
        vd.subVectors(vb,va);const L=vd.length();if(L<1e-4)return hide(q);
        tmp.quaternion.setFromUnitVectors(Yax,vd.multiplyScalar(1/L));tmp.position.copy(va).add(vb).multiplyScalar(.5);
        const r=yr*(s.th||1);tmp.scale.set(r,L,r);tmp.updateMatrix();yarn.setMatrixAt(q,tmp.matrix)});
      yarn.instanceMatrix.needsUpdate=true;
    }else{
      mesh.count=k;tmp.quaternion.identity();tmp.scale.setScalar(1);
      vis.forEach((n,j)=>{tmp.position.set(X[3*n.id],X[3*n.id+1],X[3*n.id+2]);tmp.updateMatrix();mesh.setMatrixAt(j,tmp.matrix)});mesh.instanceMatrix.needsUpdate=true;
      const p=lines.geometry.attributes.position.array;let c=0;
      G.edges.forEach(e=>{if(Math.max(e[0],e[1])>=lim)return;for(let t=0;t<3;t++){p[6*c+t]=X[3*e[0]+t];p[6*c+3+t]=X[3*e[1]+t]}c++});
      lines.geometry.attributes.position.needsUpdate=true;lines.geometry.setDrawRange(0,2*c)}
  }
  function clear(){if(!mesh)return;S.remove(mesh,lines,yarn,joints);mesh.dispose();mesh.geometry.dispose();lines.geometry.dispose();lines.material.dispose();yarn.dispose();yarn.geometry.dispose();joints.dispose();joints.geometry.dispose();mesh=null}
  /** Parse + build + start relaxing. Returns null on success, or an error message string. */
  function setPattern(text){
    const me=++job;let p,g;
    try{p=readPattern(String(text||''));g=build(p)}catch(e){err(e.message);return e.message}
    if(!g.nodes.length){const m='Nothing to draw.';err(m);return m}
    err(null);P=p;G=g;
    const relax=layout(G,P);vis=G.nodes.filter(n=>!n.hidden);clear();
    S.background=null;const bg=P.meta.bg||o.background;if(bg)try{S.background=new T.Color(bg)}catch(e){}
    mesh=new T.InstancedMesh(new T.SphereGeometry(.27,10,8),new T.MeshStandardMaterial({roughness:.7}),vis.length);
    vis.forEach((n,j)=>mesh.setColorAt(j,colr(n.col,'#9a9a96')));
    const bgm=new T.BufferGeometry(),ne=G.edges.length,col=new Float32Array(ne*6);
    G.edges.forEach((e,j)=>{const c=e[3]==='s'?[.23,.51,.96]:[.9,.3,.3];col.set([...c,...c],6*j)});
    bgm.setAttribute('position',new T.BufferAttribute(new Float32Array(ne*6),3));bgm.setAttribute('color',new T.BufferAttribute(col,3));
    lines=new T.LineSegments(bgm,new T.LineBasicMaterial({vertexColors:true}));
    prevOf=new Int32Array(G.nodes.length).fill(-1);G.edges.forEach(e=>{if(e[3]==='s'&&prevOf[e[1]]<0)prevOf[e[1]]=e[0]});
    segs=[];G.edges.forEach(e=>{const a=G.nodes[e[0]],b=G.nodes[e[1]],lo=Math.min(e[0],e[1]),hi=Math.max(e[0],e[1]),col=G.nodes[hi].col||G.nodes[lo].col,id=hi;
      if(a.hidden||b.hidden)segs.push({i:e[0],j:e[1],id,col,th:.6});
      else if(e[3]==='s')segs.push({i:e[0],j:e[1],id,col});
      else{segs.push({i:lo,j:hi,id,col,leg:1});segs.push({i:lo,j:hi,id,col,leg:-1})}});
    yarn=new T.InstancedMesh(new T.CylinderGeometry(1,1,1,8,1,false),yMat,segs.length);
    segs.forEach((s,q)=>yarn.setColorAt(q,colr(s.col)));
    joints=new T.InstancedMesh(new T.SphereGeometry(1,10,8),yMat,vis.length);
    vis.forEach((n,j)=>joints.setColorAt(j,colr(n.col)));
    [mesh,lines,yarn,joints].forEach(m=>m.frustumCulled=false);S.add(mesh,lines,yarn,joints);
    X=relax(0);draw();fit();
    const tot=Math.max(0,o.iterations|0);let left=tot;status(left,tot);
    (function f(){if(me!==job||dead)return;const s=Math.min(8,left);X=relax(s);left-=s;draw();status(left,tot);
      if(left>0)raf=requestAnimationFrame(f);else fit()})();
    return null}
  R.domElement.addEventListener('pointermove',ev=>{
    if(!o.onHover||!mesh)return;const r=R.domElement.getBoundingClientRect();
    mp.set((ev.clientX-r.left)/r.width*2-1,-(ev.clientY-r.top)/r.height*2+1);ray.setFromCamera(mp,cam);
    const h=ray.intersectObject(o.mode==='graph'?mesh:joints)[0],n=h&&vis[h.instanceId];
    o.onHover(n?{row:n.r,stitch:n.i,id:n.id,type:n.t}:null)});
  (function loop(){if(dead)return;requestAnimationFrame(loop);ctl.update();R.render(S,cam)})();
  return{
    setPattern,
    /** 'yarn' (default) or 'graph' (spheres + links) */
    setMode(m){o.mode=m==='graph'?'graph':'yarn';draw()},
    /** yarn radius, roughly 0.1 - 0.4 */
    setThickness(v){o.thickness=+v;draw()},
    /** relaxation iterations used by the next setPattern() call */
    setIterations(n){o.iterations=n|0},
    /** show only the first n stitches (in working order); omit/Infinity for all */
    setVisibleCount(n){show=n==null?Infinity:Math.max(0,n|0);draw()},
    getStitchCount(){return vis.length},
    fit,
    /** underlying three.js objects, for advanced use */
    three:{renderer:R,scene:S,camera:cam,controls:ctl},
    dispose(){dead=true;job++;cancelAnimationFrame(raf);clear();ro?ro.disconnect():root.removeEventListener('resize',size);ctl.dispose();R.dispose();yTex.dispose();yMat.dispose();if(R.domElement.parentNode)R.domElement.parentNode.removeChild(R.domElement)}
  };
}
const api={mount,readPattern,build,layout,version:'1.0.0'};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
root.CrochetViewer=api;
})(typeof window!=='undefined'?window:globalThis);
