---
slogan: "Monitoring wird erst zum Sicherheitsnetz, wenn es niemals aufhört hinzusehen."
title: "Monitoring, Teil II: Cloudflare, Firewall, das große Ganze + Claude MCP-Server (read & write*)"
slug: monitoring-homelab-teil-2-cloudflare-firewall
date: 2026-09-28
updated: 2026-09-29
description: "Eine Woche nach dem ersten selbstgebauten MCP-Server: sechs neue Dashboards, ein Sicherheitsnetz aus Cloudflare-Firewall und Tailscale-Funnel, und der Befund, dass Human-in-the-Loop für die kleinen Dinge immer unwichtiger wird."
summary: >-
  Vor einer Woche war der erste eigene, schreibfähige MCP-Server noch ein "grober Fahrplan" am Ende eines Artikels. Was seither daraus geworden ist: sechs Live-Dashboards (Gatekeeper, Ascent, Backup, System, Alerts, Connections), die innerhalb von 48 Stunden nach dem ersten Commit bereits eine echte Entra-ID-Anmeldung, echte Cloudflare-Firewall-Daten und einen Fix für einen selbst verursachten Fehler hatten. Der Artikel zeigt das neue Verbindungen-Dashboard, das auf einen Blick zeigt, was heute alles überwacht wird -- MCP-Server, Broker, Cloudflare, Search Console, Wirtschaftskalender, LLM-Wrapper -- und zeichnet das große Sicherheitsbild: zwei komplett getrennte Zugangswege (Cloudflare-Tunnel für brauckmann.ch, Tailscale Funnel für die eigene ts.net-Adresse), die beide auf dieselbe, nach außen portlose Infrastruktur treffen.
tags: [Monitoring, Cloudflare, Security, Claude, MCP]
thumb: /static/img/thumbs/monitoring-homelab-teil-2-cloudflare-firewall.jpg
draft: false
changelog:
  - datum: 2026-09-29
    text: "Nachtrag zur Prompt-Injection-Härtung ergänzt (Dank an Volker Skwarek), Dashboard-Animation heller und langsamer, mehrere Formulierungen präzisiert, Titel gestrafft."
  - datum: 2026-09-28
    text: "Artikel veröffentlicht: sechs neue Dashboards, Sicherheitsnetz- und Big-Picture-Diagramm."
---

<!-- ===== Radar-Grafik: KI-Monitoring als Sicherheitsnetz (Anfang) ===== -->
<p><strong>Dieses Netz ist mehrstufig abgesichert, so wie ich es auch für Ihr Unternehmen aufbaue: erkennen, beobachten, sperren -- jede Schicht einzeln schaltbar, messbar und umkehrbar.</strong></p>

<p>Ganz außen sitzt <strong>Cloudflare mit DDoS-Schutz, Firewall-Regeln und Rate Limiting</strong>: Was zu schnell und zu viel kommt, wird gedrosselt. Verschlüsselt wird ab TLS 1.2, alles darunter wird abgelehnt. <strong>KI-Sammler werden gesperrt</strong>, und wer sich nicht ausweist und trotzdem mitliest, läuft in ein <strong>Honeypot (Link Maze Injection)</strong> für Crawler. Dahinter arbeitet ein <strong>Edge-Proxy</strong> (Caddy) als Proxy zwischen den Netzen: Die Website hat keinen eingehenden Port, der Tunnel geht nur nach draußen, das Produktivsystem liegt in der DMZ (Demilitarisierte Zone). Auf den Servern <strong>liest CrowdSec die Logs</strong> mit und erkennt Angriffsmuster in Echtzeit.</p>

<p>Als Security Layer sind zwei Komponenten vorgesehen: Ein lokaler <strong>Firewall-Bouncer auf nftables-Basis</strong> blockiert erkannte Angreifer direkt über deren IP-Adresse auf dem Server. Parallel dazu trägt ein <strong>Cloudflare-Bouncer</strong> dieselben <strong>IP-Sperren</strong> bis an die Cloudflare-Kante (Edge), sodass schädlicher Datenverkehr blockiert wird, noch bevor er die Server-Infrastruktur überhaupt erreicht.</p>

<p>Ein <strong>nftables-Bouncer sperrt</strong> erkannte Angreifer direkt lokal aus, während ein Cloudflare-Bouncer diese Sperren bis an die Cloudflare-Edge spiegelt – so erreichen Angriffe den Server in der DMZ erst gar nicht. Für klassische Setups lässt sich <strong>Fail2ban optional einbinden</strong>. Nach erfolgreicher Testphase und nachgewiesener Fehlalarmfreiheit ist das System nun scharf geschaltet. Fernzugriffe erfolgen nicht über eine offene Shell, sondern über eine Handvoll fest definierter Aktionen. Über all dem wachen rund um die Uhr sechs Live-Dashboards sowie ein KI-gestütztes Monitoring.</p>

<p>Wie das in der Praxis aussieht, zeigt die folgende Szene: Das Radar dreht sich ohne Pause, jede Umdrehung bringt neue Bedrohungen -- Bugs, Fehlkonfigurationen, offene Ports, ablaufende Zertifikate -- <strong>und jede einzelne wird erfasst, beschossen und ausgeschaltet, bevor sie die Mitte erreicht</strong>. Genau das ist der Unterschied zwischen einem Dashboard, das zeigt, und einem Monitoring, das handelt.</p>

<style>
.kr-radar{position:relative;width:100%;aspect-ratio:1200/720;border-radius:16px;overflow:hidden;background:#03060c;margin:0}
.kr-radar>svg,.kr-radar>canvas{position:absolute;inset:0;width:100%;height:100%;display:block}
.kr-radar>.kr-ov{pointer-events:none}
.kr-radar .kr-blink{animation:kr-bl 1.6s steps(2) infinite}
@keyframes kr-bl{50%{opacity:.15}}
@media (prefers-reduced-motion:reduce){.kr-radar .kr-blink{animation:none}}
.kr-radar-figure{margin:1.75rem 0 1.9rem}
.kr-laptop{--k:.9;--ext:min(60px,4vw);--ram:9px;width:calc(var(--k)*(100% + 2*var(--ext)));margin:0 calc((100% - var(--k)*(100% + 2*var(--ext)))/2)}
.kr-lid{position:relative;margin:0 calc(var(--k)*var(--ext) - var(--ram)) -1px;padding:var(--ram) var(--ram) 22px;background:linear-gradient(180deg,#0a0a0c 0%,#050506 100%);border-radius:19px 19px 0 0;box-shadow:0 0 0 1px #5d636b,0 0 0 2.5px #b4b9c0,0 0 0 3.5px #e8eaed,0 -2px 6px 3px rgba(255,255,255,.08),inset 0 0 0 1px #24272c}
.kr-lid::before{content:"";position:absolute;top:var(--ram);left:50%;width:11%;height:11px;transform:translateX(-50%);background:#050506;border-radius:0 0 9px 9px;z-index:6}
.kr-lid::after{content:"";position:absolute;top:var(--ram);left:50%;width:4px;height:4px;margin:3px 0 0 -2px;border-radius:50%;background:#14171c;box-shadow:0 0 0 1px #23272e;z-index:7}
.kr-lid .kr-radar{border-radius:9px 9px 3px 3px}
.kr-base{position:relative;height:clamp(18px,4.2vw,27px);border-radius:1px 1px 30px 30px/1px 1px 17px 17px;background:repeating-linear-gradient(90deg,rgba(255,255,255,.07) 0 1px,rgba(0,0,0,.035) 1px 2px),linear-gradient(90deg,rgba(0,0,0,.22) 0%,rgba(255,255,255,0) 5%,rgba(255,255,255,.16) 30%,rgba(255,255,255,0) 50%,rgba(255,255,255,.16) 70%,rgba(255,255,255,0) 95%,rgba(0,0,0,.22) 100%),linear-gradient(180deg,#f6f7f9 0%,#e5e7ea 12%,#cdd1d6 40%,#b6bbc2 70%,#8d939b 100%);box-shadow:inset 0 1px 0 #fff,inset 0 -2px 3px rgba(0,0,0,.3),0 16px 24px -12px rgba(0,0,0,.6)}
.kr-base::before{content:"";position:absolute;left:0;right:0;top:0;height:32%;border-radius:1px 1px 0 0;background:linear-gradient(180deg,rgba(255,255,255,.9),rgba(255,255,255,.25));border-bottom:1px solid rgba(90,96,104,.45)}
.kr-mulde{position:absolute;top:0;left:50%;width:17%;height:45%;transform:translateX(-50%);background:linear-gradient(180deg,#9aa0a7 0%,#d6d9de 55%,#eceef1 100%);border-radius:0 0 18px 18px/0 0 12px 12px;box-shadow:inset 0 2px 3px rgba(0,0,0,.4),inset 0 -1px 0 #fff;z-index:2}
.kr-fuss{position:absolute;bottom:-5px;width:8%;height:6px;background:linear-gradient(180deg,#3a3d42,#17181b);border-radius:0 0 6px 6px}
.kr-f1{left:8%}
.kr-f2{right:8%}
.kr-radar-figure figcaption{text-align:center;font-size:0.85rem;color:var(--fg-muted);margin-top:1rem}
</style>
<figure class="kr-radar-figure">
<div class="kr-laptop"><div class="kr-lid">
<div class="kr-radar" id="kr-stage">
<!-- HINTERGRUND + RADAR-GEHÄUSE -->
<canvas id="kr-stars"></canvas>
<svg viewBox="-200 -70 1200 720" aria-hidden="true">
<defs>
  <linearGradient id="kr-floor" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#0a1726"/><stop offset="1" stop-color="#12304a"/></linearGradient>
  <linearGradient id="kr-ceil" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#05080f"/><stop offset="1" stop-color="#0c1d30"/></linearGradient>
  <filter id="kr-soft"><feGaussianBlur stdDeviation="1.1"/></filter>
  <filter id="kr-lightblur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="4"/></filter>
  <linearGradient id="kr-metal" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#9aa3ad"/><stop offset=".25" stop-color="#e3e7eb"/><stop offset=".5" stop-color="#6b737c"/><stop offset=".75" stop-color="#c6ccd2"/><stop offset="1" stop-color="#3c4249"/></linearGradient>
  <linearGradient id="kr-metalIn" x1="1" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#8e969f"/><stop offset=".5" stop-color="#2b3036"/><stop offset="1" stop-color="#5a6169"/></linearGradient>
  <radialGradient id="kr-screen" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#0c2a17"/><stop offset=".7" stop-color="#061a0e"/><stop offset="1" stop-color="#010603"/></radialGradient>
  <radialGradient id="kr-screw"><stop offset="0" stop-color="#e5e7eb"/><stop offset=".7" stop-color="#6b7280"/><stop offset="1" stop-color="#1f2937"/></radialGradient>
  <radialGradient id="kr-core"><stop offset="0" stop-color="#4ade80" stop-opacity=".35"/><stop offset="1" stop-color="#4ade80" stop-opacity="0"/></radialGradient>
  <filter id="kr-glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <filter id="kr-bigglow" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <filter id="kr-brushed"><feTurbulence type="fractalNoise" baseFrequency=".02 .9" numOctaves="2"/><feColorMatrix values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 .18 0"/></filter>
  <filter id="kr-shadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="14" stdDeviation="14" flood-color="#000" flood-opacity=".75"/></filter>
  <filter id="kr-engrave"><feOffset dy="1" in="SourceAlpha" result="o"/><feFlood flood-color="#fff" flood-opacity=".45"/><feComposite in2="o" operator="in" result="h"/><feMerge><feMergeNode in="h"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <clipPath id="kr-bez"><circle cx="400" cy="275" r="255"/></clipPath>
  <path id="kr-bezelArc" d="M 400 275 m -228 0 a 228 228 0 1 1 456 0"/>
</defs>
<!-- Gehäuse -->
<g filter="url(#kr-shadow)"><circle cx="400" cy="275" r="255" fill="url(#kr-metal)"/></g>
<rect x="140" y="15" width="520" height="520" filter="url(#kr-brushed)" clip-path="url(#kr-bez)" opacity=".9"/>
<circle cx="400" cy="275" r="253" fill="none" stroke="#fff" stroke-opacity=".35"/>
<circle cx="400" cy="275" r="218" fill="url(#kr-metalIn)"/>
<circle cx="400" cy="275" r="211" fill="#020604"/>
<text font-size="12.5" font-weight="700" letter-spacing="3" fill="#2a2f35" filter="url(#kr-engrave)" font-family="ui-monospace,Menlo,monospace"><textPath href="#kr-bezelArc" startOffset="50%" text-anchor="middle">KI-GESTÜTZTES MONITORING · RUND UM DIE UHR</textPath></text>
<g id="kr-screws"></g>
<!-- Schirm-Basis -->
<circle cx="400" cy="275" r="205" fill="url(#kr-screen)"/>
<circle cx="400" cy="275" r="80" fill="url(#kr-core)"/>
<g fill="none" stroke="#4ade80" stroke-opacity=".28" filter="url(#kr-glow)">
  <circle cx="400" cy="275" r="190"/><circle cx="400" cy="275" r="140"/><circle cx="400" cy="275" r="90"/>
  <line x1="195" y1="275" x2="605" y2="275"/><line x1="400" y1="70" x2="400" y2="480"/>
  <line x1="255" y1="130" x2="545" y2="420" stroke-opacity=".12"/><line x1="545" y1="130" x2="255" y2="420" stroke-opacity=".12"/>
</g>
<g id="kr-ticks" stroke="#4ade80" stroke-opacity=".45"></g>
<circle cx="400" cy="275" r="52" fill="#052e16" fill-opacity=".85" stroke="#4ade80" stroke-width="2" filter="url(#kr-bigglow)"/>
<text x="400" y="271" text-anchor="middle" fill="#bbf7d0" font-size="15" font-weight="700" font-family="ui-monospace,Menlo,monospace" filter="url(#kr-glow)">BUSINESS</text>
<text x="400" y="290" text-anchor="middle" fill="#86efac" font-size="11" font-family="ui-monospace,Menlo,monospace" filter="url(#kr-glow)">GESCHÜTZT ✓</text>
<circle cx="560" cy="485" r="5" fill="#22c55e" filter="url(#kr-bigglow)"><animate attributeName="opacity" values="1;.35;1" dur="2s" repeatCount="indefinite"/></circle>
</svg>
<!-- DYNAMIK: Sweep, Bedrohungen, Labels, Buddy, Laser -->
<canvas id="kr-cv"></canvas>
<!-- GLAS / SCANLINES ÜBER DEM SCHIRM -->
<svg class="kr-ov" viewBox="-200 -70 1200 720" aria-hidden="true">
<defs>
  <pattern id="kr-scan" width="4" height="4" patternUnits="userSpaceOnUse"><rect width="4" height="1.3" fill="#000" opacity=".35"/></pattern>
  <radialGradient id="kr-vign" cx="50%" cy="50%" r="50%"><stop offset=".65" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".75"/></radialGradient>
  <linearGradient id="kr-glass" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".2"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
  <filter id="kr-noise"><feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" stitchTiles="stitch"/><feColorMatrix values="0 0 0 0 .6  0 0 0 0 1  0 0 0 0 .7  0 0 0 .35 0"/></filter>
  <clipPath id="kr-scr"><circle cx="400" cy="275" r="205"/></clipPath>
</defs>
<g clip-path="url(#kr-scr)">
  <rect x="195" y="70" width="410" height="410" fill="url(#kr-scan)"/>
  <rect x="195" y="70" width="410" height="410" filter="url(#kr-noise)" opacity=".16"/>
  <circle cx="400" cy="275" r="205" fill="url(#kr-vign)"/>
  <ellipse cx="350" cy="165" rx="170" ry="95" fill="url(#kr-glass)" transform="rotate(-18 350 165)"/>
  <path d="M235 330 A175 175 0 0 0 330 440" fill="none" stroke="#fff" stroke-opacity=".08" stroke-width="6" stroke-linecap="round"/>
</g>
<circle cx="400" cy="275" r="205" fill="none" stroke="#000" stroke-width="4" stroke-opacity=".7"/>
</svg>
</div>
</div><div class="kr-base"><span class="kr-mulde"></span><span class="kr-fuss kr-f1"></span><span class="kr-fuss kr-f2"></span></div></div>
<figcaption>Rund um die Uhr im Einsatz: KI-gestütztes Monitoring erkennt Abweichungen, bevor sie zum Vorfall werden -- und räumt sie aus dem Weg.</figcaption>
</figure>
<script>
(function(){
const NS="http://www.w3.org/2000/svg",CX=400,CY=275,SR=205,P=6000;
const VB={x:-200,y:-70,w:1200,h:720};
const el=(t,a,p)=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);p.appendChild(e);return e};
const rnd=(a,b)=>a+Math.random()*(b-a);
/* ---------- Sternenhimmel (wie auf der Plattform-Seite, dichter und schneller) ---------- */
(function(){
  const cs=document.getElementById("kr-stars"),sg=cs.getContext("2d"),stg=document.getElementById("kr-stage");
  const EB=[{r:.6,v:12,a:.30,d:5500},{r:1,v:26,a:.48,d:9000},{r:1.7,v:50,a:.66,d:18000}];
  let B=0,H=0,st=[],run=false,last=0,raf=0;
  function sow(){st=[];EB.forEach(e=>{const n=Math.round(B*H/e.d);for(let i=0;i<n;i++)st.push({x:Math.random()*B,y:Math.random()*H,r:e.r*(.75+Math.random()*.5),v:e.v,a:e.a*(.6+Math.random()*.4)})})}
  function size(){const d=Math.min(devicePixelRatio||1,2),w=stg.clientWidth,h=stg.clientHeight;if(w===B&&h===H)return false;B=w;H=h;cs.width=w*d;cs.height=h*d;sg.setTransform(d,0,0,d,0,0);sow();return true}
  function draw(){sg.clearRect(0,0,B,H);sg.fillStyle="#fff";for(const s of st){sg.globalAlpha=s.a;sg.beginPath();sg.arc(s.x,s.y,s.r,0,6.2832);sg.fill()}sg.globalAlpha=1}
  function tick(t){if(!run)return;const dt=last?Math.min((t-last)/1000,.1):0;last=t;for(const s of st){s.x-=s.v*dt;if(s.x<-3){s.x=B+3;s.y=Math.random()*H}}draw();raf=requestAnimationFrame(tick)}
  function go(){if(run)return;run=true;last=0;raf=requestAnimationFrame(tick)}
  function stop(){run=false;if(raf)cancelAnimationFrame(raf)}
  size();draw();
  addEventListener("resize",()=>{if(size())draw()});
  if(matchMedia&&matchMedia("(prefers-reduced-motion: reduce)").matches)return;
  if(!window.IntersectionObserver){go();return}
  new IntersectionObserver(e=>e.forEach(x=>x.isIntersecting?go():stop()),{threshold:0}).observe(stg);
})();
/* ---------- Schrauben, Gradskala ---------- */
const sc=document.getElementById("kr-screws");
[0,45,135,180].forEach(a=>{const r=237,x=CX+r*Math.cos(a*Math.PI/180),y=CY+r*Math.sin(a*Math.PI/180);
 el("circle",{cx:x,cy:y,r:7,fill:"url(#kr-screw)",stroke:"#1f2937","stroke-width":.8},sc);
 el("line",{x1:x-4.5,y1:y,x2:x+4.5,y2:y,stroke:"#374151","stroke-width":1.6,transform:`rotate(${a+20} ${x} ${y})`},sc);});
const tk=document.getElementById("kr-ticks");
for(let d=0;d<360;d+=5){const a=d*Math.PI/180,l=d%30?5:11;
 el("line",{x1:CX+(SR-l)*Math.cos(a),y1:CY+(SR-l)*Math.sin(a),x2:CX+(SR-2)*Math.cos(a),y2:CY+(SR-2)*Math.sin(a)},tk);}
/* ---------- Bedrohungen: 4 Sätze à 4 ---------- */
const C="crit",W="warn";
const SETS=[
 [["Bug","NullRef · backup-job",C],["Fehlkonfiguration","Rule 443 → any",W],["Sicherheitslücke","CVE · exposed service",C],["Stille Abweichung","Disk I/O +3 %/Tag",W]],
 [["Speicher voll","/var 94 % belegt",W],["Zertifikat läuft ab","TLS · noch 3 Tage",W],["Brute-Force","SSH · 1200 Versuche",C],["Dienst hängt","Container-Restart-Loop",C]],
 [["Backup fehlgeschlagen","Nightly · Exit 1",C],["Memory Leak","RAM +40 MB/h",W],["Offener Port","8080 öffentlich",C],["Latenz-Spike","p95 > 900 ms",W]],
 [["Prompt-Injection","LLM-Input manipuliert",C],["Veraltetes Paket","openssl · bekannte CVE",W],["DNS-Fehler","NXDOMAIN-Welle",W],["Überhitzung","CPU 88 °C",W]]
];
// Positionen in Uhrzeit (12 = oben)
const POS=[[12,3,6,9],[10.5,2,4.5,8],[1,5,7,11],[11,3.5,5.5,8.5]];
const COL={crit:"#f87171",warn:"#fbbf24"};
const norm=x=>((x%360)+360)%360;
const rounds={};let lastPos=-1;
function round(r){
  if(rounds[r])return rounds[r];
  let p;do{p=(Math.random()*POS.length)|0}while(p===lastPos);lastPos=p;
  const set=SETS[((r%4)+4)%4];
  const th=set.map(([n,d,s],i)=>{
    const a=POS[p][i]*30-90+rnd(-7,7),hit=r*P+norm(a+90)/360*P;
    return {n,d,s,a,r:rnd(105,178),hit,fire:hit+550,arrive:hit+820,fired:false,boom:false};
  });
  delete rounds[r-3];
  return rounds[r]=th;
}
/* ---------- Canvas ---------- */
const cv=document.getElementById("kr-cv"),ctx=cv.getContext("2d"),stage=document.getElementById("kr-stage");
function resize(){const d=Math.min(devicePixelRatio||1,2),w=stage.clientWidth,h=stage.clientHeight;
  cv.width=w*d;cv.height=h*d;const s=w/VB.w*d;ctx.setTransform(s,0,0,s,-VB.x*s,-VB.y*s);}
addEventListener("resize",resize);resize();
const MONO="ui-monospace,SFMono-Regular,Menlo,monospace";
const pos=t=>{const a=t.a*Math.PI/180;return[CX+t.r*Math.cos(a),CY+t.r*Math.sin(a)]};
const lerp=(a,b,p)=>a+(b-a)*p;
function invader(x,y,col,s,frame){
  ctx.save();ctx.shadowColor=col;ctx.shadowBlur=14;ctx.fillStyle=col;
  ctx.beginPath();ctx.roundRect?ctx.roundRect(x-13*s,y-11*s,26*s,20*s,4*s):ctx.rect(x-13*s,y-11*s,26*s,20*s);ctx.fill();
  const b=frame?5:9;ctx.fillRect(x-(b+2)*s,y+8*s,4*s,4*s);ctx.fillRect(x+(b-2)*s,y+8*s,4*s,4*s);
  ctx.shadowBlur=0;ctx.fillStyle="#12140f";
  ctx.beginPath();ctx.arc(x-5*s,y-1*s,2.2*s,0,7);ctx.fill();ctx.beginPath();ctx.arc(x+5*s,y-1*s,2.2*s,0,7);ctx.fill();
  ctx.restore();
}
// Buddy – Zeichnung 1:1 aus der Kontor-Seite (zeichneBuddy)
function buddyDraw(x,y,w,s){
  const b=1.1*s;ctx.save();ctx.shadowColor="rgba(0,0,0,.6)";ctx.shadowBlur=8*s;ctx.fillStyle="#fff";
  ctx.fillRect(x-9*s-b,y-12*s-b,18*s+2*b,20*s+2*b);ctx.fillRect(x-13*s-b,y-4*s-b,4*s+2*b,8*s+2*b);ctx.fillRect(x+9*s-b,y-4*s-b,4*s+2*b,8*s+2*b);
  ctx.fillRect(x-9*s+w*s-b,y+8*s-b,4*s+2*b,6*s+2*b);ctx.fillRect(x-2*s-b,y+8*s-b,4*s+2*b,6*s+2*b);ctx.fillRect(x+5*s-w*s-b,y+8*s-b,4*s+2*b,6*s+2*b);
  ctx.restore();
  ctx.fillStyle="#c9765a";ctx.fillRect(x-9*s,y-12*s,18*s,20*s);ctx.fillRect(x-13*s,y-4*s,4*s,8*s);ctx.fillRect(x+9*s,y-4*s,4*s,8*s);
  ctx.fillStyle="#181818";ctx.fillRect(x-6*s,y-4*s,3*s,3*s);ctx.fillRect(x+3*s,y-4*s,3*s,3*s);
  ctx.fillStyle="#c9765a";ctx.fillRect(x-9*s+w*s,y+8*s,4*s,6*s);ctx.fillRect(x-2*s,y+8*s,4*s,6*s);ctx.fillRect(x+5*s-w*s,y+8*s,4*s,6*s);
}
function explosion(x,y,col){const o=[];for(let i=0;i<22;i++){const w=Math.PI*2*i/22+Math.random()*.3,v=1.4+Math.random()*2.6;
  o.push({x,y,vx:Math.cos(w)*v,vy:Math.sin(w)*v,l:1,c:Math.random()<.5?"#f2ffb8":col})}return o}
const BS=2,BY=590;let bx=CX,parts=[],shots=[];
const t0=performance.now();
function label(t,now){
  const [x,y]=pos(t),a=t.a*Math.PI/180,R=264,px=CX+R*Math.cos(a),py=CY+R*Math.sin(a);
  const age=now-t.hit,life=P*.82;
  let al=Math.min(1,age/180);if(age>life-500)al=Math.max(0,(life-age)/500);
  if(al<=0)return;
  const sn=Math.sin(a),cs=Math.cos(a);let ex,ey=py,anchor,tx,lines;
  if(sn<-.88){anchor="center";ex=px;tx=px;lines=[py-44,py-24,py-7]}
  else if(sn>.88){const dir=cs>=0?1:-1;ex=CX+dir*175;anchor=dir>0?"left":"right";tx=ex+dir*8;lines=[ey-6,ey+14,ey+32]}
  else{const dir=cs>=0?1:-1;ex=CX+dir*300;anchor=dir>0?"left":"right";tx=ex+dir*8;lines=[ey-6,ey+14,ey+32]}
  ctx.save();ctx.globalAlpha=al;
  ctx.strokeStyle="rgba(134,239,172,.6)";ctx.lineWidth=1.2;ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(px,py);ctx.lineTo(ex,ey);ctx.stroke();
  ctx.textAlign=anchor;ctx.textBaseline="alphabetic";
  const col=COL[t.s];ctx.shadowColor=col;ctx.shadowBlur=10;ctx.fillStyle=col;
  ctx.font=`800 20px ${MONO}`;ctx.fillText(t.n.toUpperCase(),tx,lines[0]);
  ctx.shadowBlur=6;ctx.shadowColor="#22c55e";ctx.fillStyle="#bbf7d0";ctx.font=`500 14px ${MONO}`;ctx.fillText(t.d,tx,lines[1]);
  const ok=now>=t.arrive;ctx.font=`700 13px ${MONO}`;
  ctx.fillStyle=ok?"#4ade80":"#fbbf24";ctx.shadowColor=ctx.fillStyle;
  ctx.fillText(ok?"✓ ABGEFANGEN":(t.s===C?"▲ KRITISCH · ERKANNT":"▲ ERKANNT"),tx,lines[2]);
  ctx.restore();
}
function frame(nowAbs){
  const now=nowAbs-t0,r=Math.floor(now/P);
  ctx.save();ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,cv.width,cv.height);ctx.restore();
  const live=[...round(r-1),...round(r)].filter(t=>now>=t.hit&&now<t.hit+P*.82);
  round(r+1);
  // Schirm (geclippt): Sweep + Invader
  ctx.save();ctx.beginPath();ctx.arc(CX,CY,SR,0,7);ctx.clip();
  const th=(now%P)/P*Math.PI*2-Math.PI/2;
  if(ctx.createConicGradient){const g=ctx.createConicGradient(th,CX,CY);
    g.addColorStop(0,"rgba(74,222,128,0)");g.addColorStop(.62,"rgba(74,222,128,0)");g.addColorStop(.85,"rgba(74,222,128,.10)");
    g.addColorStop(.97,"rgba(74,222,128,.35)");g.addColorStop(1,"rgba(134,239,172,.85)");ctx.fillStyle=g;ctx.fillRect(CX-SR,CY-SR,2*SR,2*SR);}
  ctx.strokeStyle="rgba(187,247,208,.9)";ctx.lineWidth=2;ctx.shadowColor="#4ade80";ctx.shadowBlur=10;
  ctx.beginPath();ctx.moveTo(CX,CY);ctx.lineTo(CX+SR*Math.cos(th),CY+SR*Math.sin(th));ctx.stroke();ctx.shadowBlur=0;
  live.forEach(t=>{const [x,y]=pos(t);
    if(now<t.arrive){const pulse=1+.25*Math.sin(now/90);
      ctx.strokeStyle=COL[t.s];ctx.globalAlpha=.6;ctx.lineWidth=1.2;ctx.setLineDash([6,5]);
      ctx.strokeRect(x-20*pulse,y-20*pulse,40*pulse,40*pulse);ctx.setLineDash([]);ctx.globalAlpha=1;
      invader(x,y,COL[t.s],1,Math.floor(now/380)%2);}
    else if(now<t.arrive+700){const p=(now-t.arrive)/700;ctx.strokeStyle=`rgba(74,222,128,${1-p})`;ctx.lineWidth=2;
      ctx.beginPath();ctx.arc(x,y,8+p*26,0,7);ctx.stroke();}
  });
  ctx.restore();
  // Labels
  live.forEach(t=>label(t,now));
  // Buddy zielt auf die nächste Bedrohung
  const next=live.filter(t=>!t.fired).sort((a,b)=>a.fire-b.fire)[0];
  if(next){const [x]=pos(next);const target=CX+Math.max(-90,Math.min(90,(x-CX)*.6));
    const d=target-bx;bx+=Math.abs(d)>3.5?Math.sign(d)*3.5:d;}
  live.forEach(t=>{
    if(!t.fired&&now>=t.fire){t.fired=true;const [x,y]=pos(t);shots.push({x0:bx,y0:BY-12*BS-4,x1:x,y1:y,t0:now,t1:t.arrive})}
    if(!t.boom&&now>=t.arrive){t.boom=true;const [x,y]=pos(t);parts.push(...explosion(x,y,COL[t.s]))}
  });
  // Laser
  shots=shots.filter(s=>now<s.t1+120);
  shots.forEach(s=>{const p=Math.min(1,(now-s.t0)/(s.t1-s.t0)),dx=s.x1-s.x0,dy=s.y1-s.y0,L=Math.hypot(dx,dy),ux=dx/L,uy=dy/L;
    const hx=lerp(s.x0,s.x1,p),hy=lerp(s.y0,s.y1,p);
    ctx.save();ctx.lineCap="round";
    ctx.strokeStyle="rgba(200,226,58,.18)";ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(s.x0,s.y0);ctx.lineTo(hx,hy);ctx.stroke();
    ctx.shadowColor="#c8e23a";ctx.shadowBlur=14;ctx.strokeStyle="#f2ffb8";ctx.lineWidth=3.5;
    ctx.beginPath();ctx.moveTo(hx,hy);ctx.lineTo(hx-ux*22,hy-uy*22);ctx.stroke();
    if(now-s.t0<90){ctx.fillStyle="#f2ffb8";ctx.beginPath();ctx.arc(s.x0,s.y0,6,0,7);ctx.fill();}
    ctx.restore();});
  // Explosionen
  parts.forEach(q=>{q.x+=q.vx;q.y+=q.vy;q.vy+=.03;q.l-=.022});parts=parts.filter(q=>q.l>0);
  parts.forEach(q=>{ctx.globalAlpha=q.l;ctx.fillStyle=q.c;ctx.beginPath();ctx.arc(q.x,q.y,2.6,0,7);ctx.fill()});ctx.globalAlpha=1;
  // Buddy
  buddyDraw(bx,BY+Math.sin(now/260)*2,Math.sin(now/140)*2.4,BS);
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
})();
</script>
<!-- ===== Radar-Grafik (Ende) ===== -->

<div class="callout">
<p>Der Nutzen davon beschränkt sich nicht auf den eigenen Betrieb. <strong>Kontinuierliches, KI-gestütztes Monitoring wirkt als Sicherheitsnetz</strong>, unabhängig davon, wer ein System im Tagesgeschäft betreut: Es prüft Konfiguration und Verhalten laufend gegen den Ist-Zustand, fängt Fehlkonfigurationen und Abweichungen ab, bevor sie zum Vorfall werden, und gibt dem Management eine objektive, nachvollziehbare Kontrollebene -- statt sich allein auf die Selbsteinschätzung einer einzelnen Fachkraft verlassen zu müssen. Das ist für jedes Unternehmen relevant, unabhängig davon, wie erfahren das eigene Team ist.</p>

<p>Ein Punkt daraus ist mir besonders wichtig: Gerade wenn im Ernstfall die Frage im Raum steht, wo eine Ursache wirklich lag, entscheidet oft nicht die Sachlage, sondern wer die überzeugendere Geschichte erzählt -- und genau da hilft eine lückenlose, automatisiert mitschreibende Kontrollebene allen Beteiligten weiter. <strong>Wenn jede Änderung, jeder Alarm und jeder Fix mit Zeitstempel dokumentiert ist, lässt sich eine Ursache objektiv nachvollziehen, statt sie bei Behauptung gegen Behauptung zu belassen.</strong> Das schafft Klarheit für alle Seiten, schützt gewachsene Kundenbeziehungen vor unnötigem Vertrauensverlust und macht am Ende auch die eigene Arbeit sichtbar.</p>

<p><strong>Läuft die eigene ICT-Landschaft über die Jahre zu einem unübersichtlichen Gewucher aus Diensten, Ausnahmen und Alt-Konfigurationen zusammen? Ich helfe gerne dabei</strong>, dieses Ökosystem zurechtzustutzen, das wilde Wachstum an Irritationen einzudämmen und es mit KI-gestützten Mechanismen dauerhaft in den Griff zu bekommen.</p>
</div>

<h2 id="was-das-fuer-unternehmen-bedeutet">KI-gestütztes Monitoring wirkt als Sicherheitsnetz</h2>

<p><strong>Jedes dieser Werkzeuge sieht seine eigene Ergebnisse: die Security den Angriff von außen, der Betrieb den Fehler von innen. Das Bindeglied dazwischen haben wir jetzt -- eine KI, die beide Bereiche verbindet, Ausnahmen pflegt, meldet, bei freigegebenen Aktionen selbst eingreift und sauber trennt, was ein Betriebsrisiko ist und was nur zweit- oder drittrangig.</strong></p>

<p><em>Ein Dashboard zeigt, was gerade ist. Ein Sicherheitsnetz fängt ab, was schiefgeht, bevor es jemand bemerkt -- genau das macht aus Monitoring ein Sicherheitsnetz: dass es niemals aufhört hinzusehen.</em></p>

<figure class="netz-diagramm">
<div class="risiken">
  <div class="risiko"><div class="circ" style="--c-bg:var(--md-coral-bg);--c-fg:var(--md-coral-fg)"><i class="ti ti-bug"></i></div><div class="lbl">Bug</div></div>
  <div class="risiko"><div class="circ" style="--c-bg:var(--md-warning-bg);--c-fg:var(--md-warning-fg)"><i class="ti ti-alert-triangle"></i></div><div class="lbl">Fehlkonfiguration</div></div>
  <div class="risiko"><div class="circ" style="--c-bg:var(--md-coral-bg);--c-fg:var(--md-coral-fg)"><i class="ti ti-lock-open"></i></div><div class="lbl">Sicherheitslücke</div></div>
  <div class="risiko"><div class="circ" style="--c-bg:var(--md-warning-bg);--c-fg:var(--md-warning-fg)"><i class="ti ti-eye-off"></i></div><div class="lbl">Stille Abweichung</div></div>
</div>
<div class="fallweg">
  <div class="fallspur"><span class="fallpunkt" style="animation-delay:0s"></span></div>
  <div class="fallspur"><span class="fallpunkt" style="animation-delay:.45s"></span></div>
  <div class="fallspur"><span class="fallpunkt" style="animation-delay:.9s"></span></div>
  <div class="fallspur"><span class="fallpunkt" style="animation-delay:1.35s"></span></div>
</div>
<div class="netz"><span class="netz-label">KI-gestütztes Monitoring · rund um die Uhr</span></div>
<div class="fallweg fallweg-einzeln">
  <div class="fallspur"><span class="fallpunkt" style="animation-delay:.2s"></span></div>
</div>
<div class="ergebnis"><div class="circ ergebnis-circ" style="--c-bg:var(--md-success-bg);--c-fg:var(--md-success-fg)"><i class="ti ti-shield-check"></i></div><div class="lbl">Business bleibt geschützt</div></div>
<figcaption>Kein Vorfall entsteht aus dem Nichts -- er beginnt als kleine Abweichung. Das Netz fängt sie ab, bevor sie unten ankommt.</figcaption>
</figure>

<p><em>Vor einer Woche endete <a href="/artikel/netdata-homelab-monitoring-claude/">der erste Artikel dieser Reihe</a> mit einem "groben Fahrplan": Wer aus dem reinen Lese-MCP-Server einen echten Assistenten machen will, der auch handeln darf, braucht eigene Tools, echte Authentifizierung, einen Bestätigungsschritt vor heiklen Aktionen und ein Protokoll, das mitschreibt. Eine Woche und 35 Commits später ist aus dem Fahrplan ein laufendes System geworden -- und ein paar Dinge daran haben mich selbst überrascht.</em></p>

<h2 id="teil-1-48-stunden">Nach einer Woche das Resümee: Die ersten 48 Stunden entschieden alles</h2>

<p>Das neue Monitoring ging am 20.9. um 21:57 Uhr in Betrieb -- read-only, nur intern über das eigene Tailscale-Netz erreichbar. Was in den folgenden gut 31 Stunden passierte, lässt sich lückenlos im Git-Log nachvollziehen, weil jede Änderung ein eigener Commit ist:</p>

<ul>
<li><strong>Innerhalb der ersten Stunde:</strong> aus einem geteilten Passwort wurde eine echte Microsoft-Entra-ID-Anmeldung mit Multi-Faktor -- inklusive der Kleinarbeit, die dazugehört (OAuth-Discovery-Dokument ergänzt, fehlender Standard-Scope nachgetragen, eigener App-Scope angelegt).</li>
<li><strong>Am nächsten Abend:</strong> ein erstes richtiges Dashboard ("Gatekeeper") mit echten Cloudflare-Firewall-Daten statt Platzhaltertext -- und noch am selben Abend der Fund, dass eine Kennzahl direkt und live bei Cloudflare abgefragt wurde, was bei jedem Seitenaufruf Kontingent gekostet hätte. Umgebaut auf einen Netdata-Sensor, der das im Hintergrund erledigt.</li>
<li><strong>Bis zum übernächsten Morgen, 31 Stunden nach dem ersten Commit:</strong> sechs vollständige Dashboards, ein zentrales Menü, eine Ampel-Färbung nach echtem Alarmstatus -- und mittendrin ein Moment, der die Sache auf den Punkt bringt: Ein automatischer "Beheben"-Knopf für einen vollen Arbeitsspeicher hatte den falschen Mechanismus benutzt (er leerte einen Cache, der mit dem eigentlichen Problem -- zu wenig Swap -- nichts zu tun hatte). Der Fehler wurde nicht von mir gefunden, sondern <strong>13 Minuten später im selben Lauf korrigiert</strong>, mit einem Commit, dessen Nachricht es selbst so benennt: "fixt eigenen Fehler".</li>
</ul>

<p>Das ist der eigentliche Befund dieser Woche, und er ist grösser als jedes einzelne Dashboard: Wenn ein System <strong>sich selbst beim Fehlermachen zusehen kann</strong> -- weil jeder Handgriff sofort als Metrik, Log-Zeile oder Alarm sichtbar wird -- dann muss ein Mensch nicht mehr jeden einzelnen Schritt kontrollieren. Kleinere Fehler fallen sofort auf und werden sofort behoben, oft bevor überhaupt jemand hinschaut. Genau dasselbe Muster zeigte sich diese Woche noch zweimal, in kleinerem Massstab: ein kurzzeitiger Cloudflare-API-Ausfall (sechs Minuten, danach von selbst wieder grün) und ein Wirtschaftskalender-Termin, der strukturell nie einen Wert bekommt und fälschlich als "überfällig" gemeldet wurde -- beides in derselben Sitzung gefunden und behoben, in der sie auffielen. Human-in-the-Loop wird damit nicht überflüssig -- aber für genau diese Klasse von Problemen, den kleinen, klar erkennbaren Fehlern, spürbar unwichtiger.</p>

<h2 id="teil-2-das-dashboard">Das neue Dashboard: alles auf einen Blick</h2>

<p><em>Nachtrag vom selben Abend:</em> Die komplette Oberfläche lief bis eben auf Deutsch -- auf ausdrücklichen Wunsch jetzt komplett Englisch, bis in die Menüs und die von der KI selbst zusammengebauten Statustexte hinein, damit auch ein internationales Publikum sofort versteht, was da steht. Alle sechs Seiten im Wechsel, helles Design (der Standard der meisten Besucher hier im Blog), Ports/IP-Adresse/interne Subdomains anonymisiert -- bei den längeren Dashboards scrollt die Animation einmal von oben nach unten durch, statt einfach oben abzuschneiden:</p>

<p>
<img src="/static/img/monitoring2-dashboards-all-six-light.gif" alt="Animation: alle sechs Dashboards im Wechsel -- Gatekeeper, Ascent, Backup, System, Alerts, Connections" style="max-width:100%;border-radius:12px;border:1px solid var(--border)">
</p>

<p>Genau dieses Zusehen-können ist der Kern der "Connections"-Seite (letzter Frame oben). Sechs Gruppen, auf einen Blick:</p>

<ul>
<li><strong>MCP-Server</strong> -- alle laufenden MCP-Prozesse dieses Ökosystems (Wirtschaftskalender, Produkte, Kontor-Status, dieser Server selbst), inklusive der Frage, ob der öffentliche Zugang über brauckmann.ch tatsächlich noch dort ankommt, wo er soll.</li>
<li><strong>Broker</strong> -- vier unabhängige Saxo-Bank-Verbindungen (SIM, Live, Tour-Demo, ein separates Projekt), jede mit eigenem Keepalive-Log.</li>
<li><strong>Cloudflare</strong> -- zwei API-Tokens (eigene Zone, Website-Projekt) plus eine Live-Liste aller Subdomains inklusive HTTP-Status.</li>
<li><strong>Google / Search Console</strong> -- ob das Dienstkonto für die tägliche Indexierungsprüfung noch funktioniert.</li>
<li><strong>Wirtschaftskalender</strong> -- ob Termine, die schon vergangen sind, auch wirklich einen Ist-Wert bekommen haben.</li>
<li><strong>LLM-Wrapper</strong> -- die eigene, Claude-Abo-basierte OpenAI-kompatible Schnittstelle, über die sämtliche Analysen laufen.</li>
</ul>

<p>Das klingt nach viel -- und ist es auch. Das ganze Ökosystem ist über die Zeit gewachsen: mehrere Docker-Container, mehrere Host-systemd-Dienste, zwei getrennte öffentliche Zugänge, vier Broker-Verbindungen, ein Dutzend Subdomains. Unter der Haube stehen dafür heute weit über hundert einzelne Sensoren und Zusammenhänge. Der eigentliche Punkt ist aber nicht die Zahl, sondern dass sich all das mit einem kurzen Gespräch mit der KI durchsuchen, erklären und -- wie die beiden Fixes von heute Nachmittag zeigen -- auch korrigieren lässt, ohne dass ein Mensch selbst durch Log-Dateien, Cronjobs und Datenbanktabellen graben muss.</p>

<h2 id="teil-3-das-grosse-bild">Das große Bild: zwei Wege ins System, eine Kontrolle</h2>

<p>Der spannendere Teil ist aber, was hinter diesen grünen Punkten steckt -- speziell bei Cloudflare, wo öffentlich erreichbare Dienste am meisten Angriffsfläche bieten. Der Blick dorthin ist der erste Frame der Animation ganz oben: über 9'000 Anfragen in 24 Stunden, 25 automatisch blockiert, Verkehrsweg Internet → Cloudflare Proxy → Cloudflare Tunnel → internes Netzwerk, Ende-zu-Ende ausgehend, kein eingehender Port.</p>

<p>Die kurze Fassung des Sicherheitsbilds: Es gibt zwei völlig unabhängige, öffentlich erreichbare Wege in dieses System hinein -- und keiner davon öffnet direkt einen Port am Server.</p>

<figure class="bp-diagramm">
<div class="bp-eingaenge">
  <div class="bp-box bp-cf"><i class="ti ti-cloud"></i><span class="bp-lbl">Cloudflare</span><span class="bp-sub">DNS · Proxy · WAF · brauckmann.ch</span></div>
  <div class="bp-box bp-ts"><i class="ti ti-network"></i><span class="bp-lbl">Tailscale Funnel</span><span class="bp-sub">VPN-Mesh · ts.net-Adresse</span></div>
</div>
<div class="bp-pfeile">
  <div class="fallspur"><span class="fallpunkt" style="animation-delay:0s"></span></div>
  <div class="fallspur"><span class="fallpunkt" style="animation-delay:.6s"></span></div>
</div>
<div class="bp-edge"><span class="bp-edge-label">Cloudflare Tunnel -- ausgehend, kein eingehender Port</span></div>
<div class="bp-pfeil-solo">↓</div>
<div class="bp-edge" style="max-width:340px;"><span class="bp-edge-label">Caddy Edge -- Proxy-Container</span></div>
<div class="bp-pfeil-solo">↓ Zugang zum internen Netz</div>
<div class="bp-intern">
  <span class="bp-svc">Kontor</span>
  <span class="bp-svc">Status-MCP</span>
  <span class="bp-svc">Kalender</span>
  <span class="bp-svc">Website</span>
  <span class="bp-svc">Blog</span>
</div>
<figcaption>Zwei unabhängige Eingänge, ein gemeinsamer Proxy-Container, dahinter das interne Netz -- kein Weg öffnet direkt einen Port am Server.</figcaption>
</figure>

<ul>
<li><strong>Weg 1, brauckmann.ch und die übrigen eigenen Domains:</strong> Cloudflare als DNS- und Proxy-Schicht mit WAF, Bot-Schutz und Firewall-Regeln davor, dahinter ein Cloudflare-Tunnel (<code>cloudflared</code>), der die Verbindung <strong>ausgehend</strong> vom Server aus aufbaut -- am Router ist dafür kein einziger Port geöffnet. Der Tunnel liefert an einen zentralen Caddy-Edge, der je nach Pfad an den richtigen internen Dienst weiterreicht. Die eine dokumentierte Ausnahme: zwei technische Subdomains für MCP-Anbindungen zeigen direkt auf einen lokalen Port statt über den gemeinsamen Caddy-Edge zu laufen -- ohne die gemeinsamen Security-Header, dafür mit einem eigenen Bearer-Token als Schutz. Bewusst offen dokumentiert, nicht versteckt.</li>
<li><strong>Weg 2, die eigene ts.net-Adresse:</strong> Tailscale Funnel, also ein VPN-Mesh mit einer eigenen, öffentlich freigeschalteten Ausnahme -- komplett getrennt von Cloudflare, eigenes Zertifikat, eigener Pfad, landet aber am Ende beim selben internen Caddy-Edge.</li>
</ul>

<p>Beide Wege laufen am Ende durch dieselbe lokale Infrastruktur auf demselben Server -- aber jeder Dienst dahinter hat seine eigene, unabhängige Zugriffskontrolle: die Trading-Oberfläche selbst mit einer dreistufigen Vertrauenslogik (lokales Netz / Tailnet / öffentlicher Funnel, mit Passwort und Einmalcode für die zwei strengeren Stufen), die Status- und Admin-Dashboards über echte Microsoft-Entra-ID-Anmeldung mit Multi-Faktor. Fällt einer der beiden äusseren Wege aus oder wird missbraucht, ist der andere davon komplett unberührt -- zwei unabhängige Frontends vor derselben, nach aussen portlosen Basis.</p>

<h2 id="nachtrag-prompt-injection">Nachtrag, einen Tag später: eine Lücke, die reines Perimeter-Denken nicht sieht</h2>

<p>Alles bisher Beschriebene -- Firewall, Tunnel, Zugriffskontrolle -- dreht sich um die Frage, <em>wer</em> ins System hineinkommt. Es gibt eine zweite Frage, die genauso wichtig ist und die im Sicherheitsbild oben komplett fehlt: Was, wenn eine Anfrage ganz regulär durch alle Türen hereinkommt -- als Wirtschaftskalender-Termin, als Alarmtext, als ganz gewöhnlicher Text --, aber etwas enthält, das die KI dahinter als Anweisung statt als Daten liest? Genau das ist <strong>Prompt Injection</strong>, Platz eins der <a href="https://genai.owasp.org/llm-top-10/">OWASP Top 10 für LLM-Anwendungen</a>, und der Anstoss dazu kam von aussen: <a href="https://www.linkedin.com/feed/update/urn:li:ugcPost:7432466152238362624/">einer LinkedIn-Folge von Volker Skwarek</a> (Hochschule für Angewandte Wissenschaften Hamburg) über genau dieses Thema. Ohne diesen Anstoss wäre das hier vermutlich nicht angeschaut worden -- danke dafür, Volker.</p>

<p>Der Check auf die eigene, in diesem Artikel beschriebene Infrastruktur brachte einen echten, wenn auch eingedämmten Fund: Kontors Analyse-Agent bekommt bei jeder Frage einen Kontext-Block mit aktuellen Marktdaten, dem eigenen Handelsplan -- und dem Titel des nächsten anstehenden Wirtschaftstermins. Dieser Titel stammt roh von externen Quellen (Trading Economics, Finnhub, ForexFactory) und landete bislang unverändert im Prompt. Ein böswillig formulierter Termintitel hätte also theoretisch versuchen können, sich als Anweisung an die KI auszugeben, statt als das gelesen zu werden, was er ist: ein Stück Text zum Anzeigen. Der Blast Radius war durch die bestehende Architektur schon vorher eng begrenzt -- derselbe Chat-Pfad schaltet Werkzeuge serverseitig komplett ab und erzwingt eine harte Ein-Zug-Grenze, eine erfolgreiche Injection hätte also nie mehr als die angezeigte Antwort verfälschen können. Trotzdem: eine offene Tür, die jetzt zu ist.</p>

<p>Die Gegenmassnahme, wie im Rest dieses Artikels dokumentiert und überwacht statt nur einmalig gefixt: Freitext-Felder aus dem Kalender werden jetzt auf eine sinnvolle Länge begrenzt und von Steuerzeichen befreit, bevor sie den Prompt erreichen, und der System-Prompt selbst trennt jetzt explizit zwischen Datenmaterial und Anweisung -- ein Termintitel, der wie ein Befehl klingt, bleibt ein Termintitel. Und wie es zu diesem Ökosystem passt: ein neuer, alle 15 Minuten laufender Netdata-Sensor prüft seither, ob genau diese Absicherung im Quelltext noch steht, sichtbar als eigene "LLM Security"-Kachel auf der Connections-Seite von oben und als eigene Karte auf dem Gatekeeper-Dashboard -- derselbe Mechanismus, der schon den eigenen Fehler beim Arbeitsspeicher-Alarm 13 Minuten nach dem Auftreten fing, wacht jetzt auch hier mit:</p>

<p>
<img src="/static/img/monitoring2-llm-security-connections.png" alt="Connections-Dashboard mit rot eingekreister neuer 'LLM Security'-Kachel" style="max-width:100%;border-radius:12px;border:1px solid var(--border)">
</p>

<p>
<img src="/static/img/monitoring2-llm-hardening-gatekeeper.png" alt="Gatekeeper-Dashboard mit rot eingekreister Karte 'LLM prompt-injection hardening'" style="max-width:100%;border-radius:12px;border:1px solid var(--border)">
</p>

<h2 id="zusammengefasst">Zusammengefasst</h2>

<p>Eine Woche, 35 Commits, sechs Dashboards, ein selbst gefundener und selbst behobener Fehler binnen 13 Minuten -- und ein Sicherheitsbild mit zwei unabhängigen, portlosen Zugangswegen zu derselben Infrastruktur. Der grösste Unterschied zur Realität von vorher ist nicht die Zahl der Sensoren, <strong>sondern dass kleine Fehler nicht mehr liegen bleiben, bis jemand zufällig draufschaut.</strong></p>
