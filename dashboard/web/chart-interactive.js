function enableEquityInteraction(svg,a,xy,L,R,W,H){
  if(!svg||!a.length||!xy.length)return;
  const ns='http://www.w3.org/2000/svg';
  let guide=document.createElementNS(ns,'line'),dot=document.createElementNS(ns,'circle');
  guide.setAttribute('class','chart-hover-line'); dot.setAttribute('class','chart-hover-dot');
  guide.setAttribute('y1','18'); guide.setAttribute('y2',String(H-34));
  dot.setAttribute('r','5'); svg.append(guide,dot);
  let tip=document.getElementById('equityTip'); if(!tip){tip=document.createElement('div');tip.id='equityTip';tip.className='equity-tip';svg.parentElement.appendChild(tip)}
  const hide=()=>{guide.style.opacity=dot.style.opacity=tip.style.opacity='0'};
  const show=e=>{let rect=svg.getBoundingClientRect(),cx=e.touches?e.touches[0].clientX:e.clientX,local=(cx-rect.left)/rect.width*W,i=Math.max(0,Math.min(a.length-1,Math.round((local-L)/(W-L-R)*(a.length-1))));let p=xy[i],z=a[i];guide.setAttribute('x1',p.x);guide.setAttribute('x2',p.x);dot.setAttribute('cx',p.x);dot.setAttribute('cy',p.y);guide.style.opacity=dot.style.opacity='1';let pnl=Number(z.pnl||0),date=new Date(z.ts*1000).toLocaleString('ru-RU',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});tip.innerHTML=`<small>${date}</small><b class="${pnl>=0?'good':'bad'}">${pnl>=0?'+':''}$${Math.abs(pnl).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})}</b><span>PNL на этот момент</span>`;tip.style.opacity='1';tip.style.left=Math.max(8,Math.min(rect.width-tip.offsetWidth-8,(p.x/W)*rect.width-tip.offsetWidth/2))+'px';tip.style.top=Math.max(8,(p.y/H)*rect.height-tip.offsetHeight-14)+'px';e.preventDefault&&e.preventDefault()};
  svg.onmousemove=show;svg.ontouchstart=show;svg.ontouchmove=show;svg.onmouseleave=hide;svg.ontouchend=()=>setTimeout(hide,900);
}
