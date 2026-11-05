/* Editor Leaflet: pontos de passagem ordenados, cálculo após soltar e percurso assinado. */
(() => {
  const cfg = JSON.parse(document.getElementById('editor-rota-config').textContent);
  const modo = document.getElementById('rota-modo');
  const painel = document.getElementById('editor-rota');
  const status = document.getElementById('rota-status');
  const token = document.getElementById('rota-token');
  const form = modo.form;
  const perfil = document.getElementById('rota-perfil');
  const botao = document.getElementById('calcular-rota');
  const limpar = document.getElementById('limpar-passagens');
  const margem = form.elements.faixa_raio_km;
  let rota = cfg.rota, pontos = rota ? rota.pontos.slice(1,-1) : [];
  let map, camadas, marcadorLayer, controle, versao = 0, timer, ocupada=false;
  const ll = p => [p[1],p[0]];
  if (rota) perfil.value=rota.perfil;

  function invalidar(mensagem) {
    versao++;
    token.value='';
    status.textContent=mensagem || 'O percurso foi alterado. Calcule a rota antes de salvar.';
    if (camadas) {camadas.clearLayers();marcadorLayer.clearLayers();}
  }
  function dados() {
    const d={perfil:perfil.value,intermediarios:pontos};
    ['origem','destino','origem_uf','destino_uf','origem_latitude','origem_longitude','destino_latitude','destino_longitude'].forEach(k => d[k]=form.elements[k].value);
    return d;
  }
  function iniciarMapa() {
    if(map) {setTimeout(() => map.invalidateSize(),0);return true;}
    if(!window.L) {status.textContent='Não foi possível carregar o mapa. Verifique a internet e recarregue a página.';return false;}
    map=L.map('mapa-editor-rota').setView([-19,-48],5);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).on('tileerror',() => {
      status.textContent='Mapa de fundo indisponível. Verifique a conexão com a internet.';
    }).addTo(map);
    camadas=L.featureGroup().addTo(map);marcadorLayer=L.featureGroup().addTo(map);
    return true;
  }
  function desenhar(enquadrar=false) {
    if(!map || !rota) return;
    camadas.clearLayers();marcadorLayer.clearLayers();
    if(window.turf) {
      try {
        const r=Number(margem.value.replace(',','.'));
        if(r>0 && r<=200) {
          const linha=turf.simplify(turf.lineString(rota.caminho),{tolerance:0.00005,highQuality:true});
          const area=turf.buffer(linha,r,{units:'kilometers',steps:12});
          if(area) L.geoJSON(area,{style:{color:'#2563eb',weight:1,fillOpacity:0.16,interactive:false}}).addTo(camadas);
        }
      } catch(e) {status.textContent='Percurso disponível. Não foi possível desenhar sua faixa.';}
    }
    const linha=L.polyline(rota.caminho.map(ll),{color:'#2563eb',weight:5}).addTo(camadas);
    linha.on('click', e => {
      if(ocupada) return;
      if(pontos.length>=48) {status.textContent='Limite de 48 pontos intermediários atingido.';return;}
      if(!window.turf) {status.textContent='Recarregue a página para habilitar a edição do percurso.';return;}
      const local=turf.nearestPointOnLine(turf.lineString(rota.caminho),turf.point([e.latlng.lng,e.latlng.lat]));
      const trecho=local.properties.index;
      let pos=0;
      while(pos<pontos.length && rota.indices[pos+1]<=trecho) pos++;
      pontos.splice(pos,0,[e.latlng.lng,e.latlng.lat]);
      invalidar('Adicionando ponto de passagem…');calcular();
    });
    const caminho=[rota.pontos[0],...pontos,rota.pontos[rota.pontos.length-1]];
    caminho.forEach((p,i) => {
      const extremo=i===0 || i===caminho.length-1;
      const label=i===0 ? 'O' : i===caminho.length-1 ? 'D' : String(i);
      const icon=L.divIcon({className:'rota-ponto',html:'<span>'+label+'</span>',iconSize:[30,30],iconAnchor:[15,15]});
      const marker=L.marker(ll(p),{draggable:true,icon,keyboard:true,title:extremo ? (i===0?'Origem':'Destino') : 'Ponto de passagem '+i}).addTo(marcadorLayer);
      marker.on('dragend',() => {
        const q=marker.getLatLng();
        if(extremo) {
          const prefixo=i===0?'origem_':'destino_';
          form.elements[prefixo+'latitude'].value=q.lat.toFixed(7);
          form.elements[prefixo+'longitude'].value=q.lng.toFixed(7);
        } else pontos[i-1]=[q.lng,q.lat];
        invalidar('Recalculando percurso após ajuste…');calcular();
      });
    });
    const lista=document.getElementById('pontos-rota');lista.replaceChildren();
    pontos.forEach((p,i) => {
      const li=document.createElement('li');li.append('Passagem '+(i+1)+' · '+p[1].toFixed(5)+', '+p[0].toFixed(5)+' ');
      const remover=document.createElement('button');remover.type='button';remover.className='btn small';remover.textContent='Remover';
      remover.disabled=ocupada;
      remover.onclick=() => {pontos.splice(i,1);invalidar();calcular();};li.append(remover);lista.append(li);
    });
    if(enquadrar) map.fitBounds(linha.getBounds(),{padding:[35,35],maxZoom:13});
  }
  async function calcular() {
    clearTimeout(timer);
    if(modo.value!=='estradas' || ocupada || !iniciarMapa()) return;
    invalidar('Calculando percurso pelas estradas…');
    const minhaVersao=versao;
    ocupada=true;botao.disabled=true;limpar.disabled=true;
    const abortador=new AbortController();const prazo=setTimeout(() => abortador.abort(),35000);
    try {
      const resposta=await fetch(cfg.url,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':cfg.token},body:JSON.stringify(dados()),signal:abortador.signal});
      const resultado=await resposta.json();
      if(minhaVersao!==versao || modo.value!=='estradas') return;
      if(!resposta.ok) throw new Error(resultado.erro || 'Não foi possível calcular a rota.');
      rota=resultado.rota;token.value=resultado.token;
      status.textContent='Percurso calculado · '+rota.distancia_km.toFixed(1)+' km. Ajuste os pontos e salve o rotograma para confirmar.';
      desenhar(true);
    } catch(e) {
      if(minhaVersao===versao) {
        status.textContent=(e.name==='AbortError'?'O cálculo demorou demais. Tente novamente.':(e.message || 'Falha de conexão. Tente novamente.')) + (rota ? ' O desenho anterior permanece como referência. Ajuste ou remova a passagem e calcule novamente antes de salvar.' : '');
        if(rota) desenhar(false);
      }
    } finally {clearTimeout(prazo);ocupada=false;botao.disabled=false;limpar.disabled=false;document.querySelectorAll('#pontos-rota button').forEach(b => b.disabled=false);}
  }
  modo.addEventListener('change',() => {
    versao++;painel.hidden=modo.value!=='estradas';
    if(!painel.hidden) {iniciarMapa();if(rota && token.value) desenhar(true);}
  });
  botao.onclick=calcular;
  limpar.onclick=() => {pontos=[];invalidar();calcular();};
  perfil.onchange=() => {invalidar();calcular();};
  ['origem','destino','origem_uf','destino_uf','origem_latitude','origem_longitude','destino_latitude','destino_longitude'].forEach(k => {
    form.elements[k].addEventListener('input',() => {pontos=[];rota=null;invalidar();clearTimeout(timer);});
    form.elements[k].addEventListener('change',() => {
      if(form.elements.origem.value.trim() && form.elements.destino.value.trim()) timer=setTimeout(calcular,700);
    });
  });
  margem.addEventListener('input',() => {clearTimeout(timer);timer=setTimeout(() => desenhar(false),250);});
  form.addEventListener('submit',e => {
    if(modo.value==='estradas' && (!token.value || ocupada)) {e.preventDefault();status.textContent='Calcule a rota e aguarde sua conclusão antes de salvar o rotograma.';status.scrollIntoView({block:'center'});}
  });
  if(!painel.hidden && iniciarMapa()) {
    if(rota && token.value) {desenhar(true);status.textContent='Percurso salvo · '+rota.distancia_km.toFixed(1)+' km. Você pode ajustar os pontos de passagem.';}
    else status.textContent='Informe os extremos e clique em Calcular rota.';
  }
})();
