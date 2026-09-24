import time
from .config import load_leaders, setting

def main():
    leaders = load_leaders()
    mode = setting("MODE", "PAPER").upper()
    if mode != "PAPER":
        raise RuntimeError("v0.1 refuses to run outside PAPER mode")
    print(f"Polymarket Copy Engine v0.1 | mode={mode} | leaders={len(leaders)}")
    for leader in leaders:
        print(f"- {leader.name}: {leader.wallet}")
    print("Paper engine initialized. Public data adapters are the next milestone.")
    while True:
        time.sleep(float(setting("POLL_SECONDS", "2")))

if __name__ == "__main__":
    main()
