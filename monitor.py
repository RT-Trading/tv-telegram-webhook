import time
from main import check_trades, log_error

if __name__ == "__main__":
    while True:
        try:
            check_trades()
        except Exception as e:
            log_error(f"Hauptfehler (Worker): {e}")
        time.sleep(120)  # alle 10 Minuten
