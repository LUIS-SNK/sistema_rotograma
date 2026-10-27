"use strict";
const buscaPosto = document.getElementById("pesquisar-posto");
const selectPosto = document.getElementById("posto-selecionado");
const opcoesPosto = Array.from(selectPosto.options).slice(1);
const normalizarPosto = texto => texto.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("pt-BR").trim().replace(/\s+/g, " ");
buscaPosto.addEventListener("input", () => {
    const termo = normalizarPosto(buscaPosto.value);
    const selecionado = selectPosto.value;
    const filtradas = opcoesPosto.filter(opcao => normalizarPosto(opcao.dataset.nome).includes(termo));
    selectPosto.replaceChildren(new Option(filtradas.length ? "Selecione um posto ativo" : "Nenhum posto encontrado", ""), ...filtradas);
    selectPosto.value = filtradas.some(opcao => opcao.value === selecionado) ? selecionado : "";
    document.getElementById("resultado-postos").textContent = `${filtradas.length} posto(s) encontrado(s).`;
});
