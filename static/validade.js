"use strict";
document.querySelectorAll("[data-referencia]").forEach(campo => {
    const destino = campo.closest("form").querySelector("[data-vencimento]");
    function atualizar() {
        const partes = campo.value.split("-").map(Number);
        if (partes.length !== 3 || partes.some(p => !Number.isFinite(p)) || !campo.value) { destino.value = "Não informada"; return; }
        const [ano, mes, dia] = partes;
        const fimMes = new Date(0); fimMes.setUTCFullYear(ano + 2, mes, 0);
        const limite = fimMes.getUTCDate();
        destino.value = `${String(Math.min(dia, limite)).padStart(2,"0")}/${String(mes).padStart(2,"0")}/${String(ano+2).padStart(4,"0")}`;
    }
    campo.addEventListener("input", atualizar); atualizar();
});
