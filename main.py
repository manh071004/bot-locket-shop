import os
import sys
import subprocess
import time

def run():
    print("==========================================")
    print(" KHOI DONG HE THONG MULTI-BOT TREN RENDER")
    print("==========================================")

    base_dir = os.path.dirname(os.path.abspath(__file__))
    bot_v2_dir = os.path.join(base_dir, "bot-v2")
    bot_tao_dir = os.path.join(base_dir, "bot-tao")

    processes = []

    if os.path.exists(os.path.join(bot_v2_dir, "main.py")):
        print("[*] Khoi dong bot-v2 (Locket Shop)...")
        p_v2 = subprocess.Popen([sys.executable, "main.py"], cwd=bot_v2_dir)
        processes.append(("bot-v2", p_v2))

    if os.path.exists(os.path.join(bot_tao_dir, "main.py")):
        print("[*] Khoi dong bot-tao (Shoppretool_bot)...")
        p_tao = subprocess.Popen([sys.executable, "main.py"], cwd=bot_tao_dir)
        processes.append(("bot-tao", p_tao))

    print(f"[v] Da khoi dong {len(processes)} bot song song!")

    try:
        while True:
            time.sleep(5)
            for i, (name, p) in enumerate(processes):
                if p.poll() is not None:
                    print(f"[!] {name} bi dung (code {p.returncode})! Dang khoi dong lai...")
                    wdir = bot_v2_dir if name == "bot-v2" else bot_tao_dir
                    new_p = subprocess.Popen([sys.executable, "main.py"], cwd=wdir)
                    processes[i] = (name, new_p)
    except KeyboardInterrupt:
        for name, p in processes:
            p.terminate()

if __name__ == "__main__":
    run()
