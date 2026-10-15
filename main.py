import os, sys, asyncio


def run():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    bot_v2_dir = os.path.join(base_dir, "bot-v2")
    if os.path.exists(bot_v2_dir):
        os.chdir(bot_v2_dir)
        sys.path.insert(0, bot_v2_dir)
        import main as bot_v2_main
        asyncio.run(bot_v2_main.main())


if __name__ == "__main__":
    run()
