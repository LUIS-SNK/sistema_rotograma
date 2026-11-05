(() => {
  const status = document.getElementById('mapa-status');
  if (!window.L) {status.textContent = 'Não foi possível carregar o mapa. Verifique a conexão com a internet.'; return;}
  const dados = JSON.parse(document.getElementById('dados-mapa-rotograma').textContent);
  const map = L.map('mapa-rotograma').setView([-15.8,-47.9],4);
  const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);
  tiles.on('tileerror', () => {status.textContent='Mapa de fundo indisponível. Os pontos e a faixa continuam disponíveis.';});
  const layers = {Faixa:L.featureGroup().addTo(map), 'Origem e destino':L.featureGroup().addTo(map), Cercas:L.featureGroup().addTo(map), Postos:L.featureGroup().addTo(map)};
  const latlng = p => [p[1],p[0]];
  const bounds = L.latLngBounds([]);
  if (dados.faixa) {
    if (dados.faixa.por_estradas && dados.faixa.raio_km > 0 && window.turf) {
      try { const faixa=turf.buffer(turf.simplify(turf.lineString(dados.faixa.linha),{tolerance:0.00005,highQuality:true}),dados.faixa.raio_km,{units:'kilometers'});
        if(faixa) L.geoJSON(faixa,{style:{color:'#2563eb',weight:1,fillOpacity:0.13}}).addTo(layers.Faixa);
      } catch(e) {status.textContent='Não foi possível desenhar a faixa. O percurso continua disponível.';}
    } else if (dados.faixa.anel) L.polygon(dados.faixa.anel.map(latlng),{color:'#2563eb',weight:2,fillOpacity:0.13}).addTo(layers.Faixa);
    L.polyline(dados.faixa.linha.map(latlng),{color:'#2563eb',dashArray:dados.faixa.por_estradas ? null : '8 6',weight:3}).addTo(layers.Faixa);
    (dados.faixa.anel || dados.faixa.linha).forEach(p => bounds.extend(latlng(p)));
  }
  dados.marcadores.forEach(p => {
    const cor = p.tipo === 'Cerca' ? '#c45b09' : p.tipo === 'Posto' ? '#15803d' : '#1d4ed8';
    const grupo = p.tipo === 'Cerca' ? layers.Cercas : p.tipo === 'Posto' ? layers.Postos : layers['Origem e destino'];
    const popup = document.createElement('div');
    const nome = document.createElement('strong'); nome.textContent=p.tipo+' · '+p.nome; popup.append(nome);
    const detalhe = document.createElement('p'); detalhe.textContent=p.precisao+(p.municipio ? ' · '+p.municipio : ''); popup.append(detalhe);
    L.circleMarker(latlng(p.ponto),{radius:8,color:cor,fillColor:cor,fillOpacity:0.85,weight:2}).bindPopup(popup).addTo(grupo);
    bounds.extend(latlng(p.ponto));
  });
  L.control.layers(null,layers,{collapsed:false}).addTo(map);
  if(bounds.isValid()) map.fitBounds(bounds,{padding:[30,30],maxZoom:12});
  status.textContent=dados.marcadores.length ? dados.marcadores.length+' localizações disponíveis. Use o controle para exibir ou ocultar camadas.' : 'Nenhuma localização disponível. Informe municípios/UF ou coordenadas nos cadastros.';
})();
