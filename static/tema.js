(() => {
    "use strict";
    const chave = "rotogramas-tema";
    const raiz = document.documentElement;
    const preferenciaSistema = window.matchMedia("(prefers-color-scheme: dark)");
    let escolha = null;
    try { escolha = localStorage.getItem(chave); } catch (_) { /* Armazenamento pode estar indisponível. */ }
    if (escolha !== "dark" && escolha !== "light") escolha = null;
    function aplicar(tema) {
        raiz.dataset.theme = tema;
        const botao = document.getElementById("alternar-tema");
        if (!botao) return;
        const escuro = tema === "dark";
        const acao = escuro ? "Modo claro" : "Modo escuro";
        botao.querySelector("[data-theme-label]").textContent = acao;
        botao.querySelector("[data-theme-icon]").textContent = escuro ? "☀" : "☾";
        botao.setAttribute("aria-label", escuro ? "Ativar modo claro" : "Ativar modo escuro");
        botao.setAttribute("aria-pressed", String(escuro));
        botao.title = escuro ? "Ativar modo claro" : "Ativar modo escuro";
    }
    aplicar(escolha || (preferenciaSistema.matches ? "dark" : "light"));
    document.addEventListener("DOMContentLoaded", () => {
        const botao = document.getElementById("alternar-tema");
        if (!botao) return;
        botao.hidden = false;
        aplicar(raiz.dataset.theme);
        botao.addEventListener("click", () => {
            escolha = raiz.dataset.theme === "dark" ? "light" : "dark";
            aplicar(escolha);
            try { localStorage.setItem(chave, escolha); } catch (_) { /* Mantém o tema nesta página. */ }
        });
    });
    preferenciaSistema.addEventListener("change", evento => {
        if (!escolha) aplicar(evento.matches ? "dark" : "light");
    });
    window.addEventListener("storage", evento => {
        if (evento.key !== chave && evento.key !== null) return;
        escolha = evento.newValue === "dark" || evento.newValue === "light" ? evento.newValue : null;
        aplicar(escolha || (preferenciaSistema.matches ? "dark" : "light"));
    });
})();
