"""Datas civis e verificador interno independente de acessos ao navegador."""
import calendar
import threading
from datetime import date, datetime
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")
UFS = ("AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO")


def hoje():
    return datetime.now(FUSO).date()


def somar_meses(data, meses):
    total = data.year * 12 + data.month - 1 + meses
    ano, mes = divmod(total, 12)
    mes += 1
    return date(ano, mes, min(data.day, calendar.monthrange(ano, mes)[1]))


def vencimento(referencia):
    return somar_meses(referencia, 24) if referencia else None


def ler_referencia(valor, obrigatoria=False, regularizacao=False):
    if not valor:
        if obrigatoria:
            raise ValueError("Informe a data de referência.")
        return None
    try:
        data = date.fromisoformat(valor)
        fim = vencimento(data)
    except (ValueError, OverflowError):
        raise ValueError("Informe uma data de referência válida.")
    if data > hoje():
        raise ValueError("A data de referência não pode estar no futuro.")
    if regularizacao and fim <= hoje():
        raise ValueError("A nova referência deve resultar em validade vigente.")
    return data


def situacao_validade(item, dia=None):
    dia = dia or hoje()
    fim = getattr(item, "data_vencimento", None)
    if not fim:
        return "sem_data"
    if fim <= dia:
        return "vencido"
    if dia >= somar_meses(fim, -1):
        return "proximo"
    return "vigente"


class VerificadorInterno:
    """Uma thread por aplicação; a rotina usa também uma concessão no banco."""
    def __init__(self, app, verificar, intervalo=900):
        self.app = app
        self.verificar = verificar
        self.intervalo = intervalo
        self.parar = threading.Event()
        self.thread = None
        self.lock = threading.Lock()

    def iniciar(self):
        with self.lock:
            if self.thread and self.thread.is_alive():
                return
            self.parar.clear()
            self.thread = threading.Thread(target=self._executar, name="validade-rotogramas", daemon=True)
            self.thread.start()

    def _executar(self):
        while not self.parar.is_set():
            try:
                with self.app.app_context():
                    self.verificar()
            except Exception:
                self.app.logger.exception("Falha no verificador de validade; nova tentativa no próximo ciclo.")
            if self.parar.wait(self.intervalo):
                break

    def encerrar(self):
        self.parar.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=5)
