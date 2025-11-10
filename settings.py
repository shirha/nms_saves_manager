# config.py
import json
from pathlib import Path
import shutil
import sys
from colorama import Fore, Style, init
import random

# ANSI escape code for ESC text                        90
YELLOW, GRAY, BLUE, GREEN, RED = "\x1b[93m", "\x1b[90m", "\x1b[36m", "\x1b[32m", "\x1b[91m"
# ANSI escape code to reset text color to default
RESET = "\x1b[0m"
ESC = ["\x1b[90m","\x1b[36m","\x1b[36m\x1b[7m","\x1b[32m","\x1b[32m\x1b[7m","\x1b[45m","\x1b[7m"][0]#[random.randint(0, 5)]
ESC = BLUE

def load_config():
    """
    Loads or sets up the NMS Saves Manager configuration.
    
    Returns:
        dict: Config with keys: 'GAME_SAVES_DIR' (Path), 'STEAM_ID' (str), 'MODE' (str),
              'game_saves' (str, prod path), 'hg' (bool, validation flag).
    """
    config_file = Path("config.json")
    root = list(map(str, range(2, 31)))  # Save file indices for validation
    print(RESET)

    def hg_lookup(gf: Path) -> bool:
        """Checks if the given path contains .hg save files (indicating a valid NMS saves dir)."""
        is_occupied = any((gf / f"save{i}.hg").exists() for i in root)
        if not is_occupied:
            print(f"\nWarning: '.hg' save files not found in {gf}")
            print("This may indicate an invalid or empty NMS saves directory.")
        return is_occupied
    
    def show():
        #mode='prod'
        print(f"\n{ESC} NMS Saves Manager config loaded - Mode: {mode:4} {RESET}")
        print(f"{ESC} {GRAY if mode == 'prod' else YELLOW}'dev'{RESET} - Environment")
        print(f"{ESC} {RESET}  Game Saves Dir: st_{steam_id} - {YELLOW}sandbox{RESET}")
        print(f"{ESC} {RESET}  Backup Pool Dir: NMS_dev_Pool")
        print(f"{ESC} {RESET}")
        print(f"{ESC} {GRAY if mode == 'dev' else RED}'prod'{RESET} - Environment")
        print(f"{ESC} {RESET}  Game Saves Dir: {game_saves}/st_{steam_id} {'✅' if is_occupied else '❌'}")
        print(f"{ESC} {RESET}  Backup Pool Dir: NMS_prod_Pool")
        print(f"{ESC}                                              {RESET}")

    # Load existing config if available
    if config_file.exists():
        try:
            with open(config_file, "r") as f:
                config = json.load(f)
            mode = config.get('mode', 'dev')  # Default to dev if unspecified
            steam_id = config['steam_id']
            game_saves = config['game_saves'] # ...HelloGames/NMS
            dev_dir = Path(f"st_{steam_id}")
            prod_dir = Path(f"{game_saves}/{dev_dir}")
            
            # Validate the selected dir
            is_occupied = hg_lookup(prod_dir) # (game_saves_dir if mode == "prod" else Path(game_saves))
            if not is_occupied and mode == "prod":
                print("Production directory validation failed. Switching to dev mode.")
                mode = 'dev'
                config['mode'] = mode
                config['hg'] = False
                with open(config_file, "w") as f:
                    json.dump(config, f, indent=4)

            # based on mode
            game_saves_dir = str(prod_dir if mode == "prod" else dev_dir)
            show()
            
            # Ensure dev sandbox exists if in dev mode
            if mode == 'dev':
                _setup_dev_sandbox(prod_dir, dev_dir)
            
            return {
                'GAME_SAVES_DIR': game_saves_dir,
                'STEAM_ID': steam_id,
                'MODE': mode,
                'game_saves': game_saves,
                'hg': is_occupied
            }
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error loading config.json: {e}. Starting fresh setup.")
            config_file.unlink()  # Remove invalid config to restart
    
    # Fresh setup: Guide user through configuration
    print("\n=== NMS Saves Manager Setup ===")
    print("We'll create a safe sandbox (dev) environment for testing.")
    print("Later, you can switch to 'prod' for real game saves.\n")
    
    while True:
        try:
            user_id = input(f"Enter Windows user_id (e.g., your username for C:/Users/<user_id>): {YELLOW}").strip()
            print(RESET, end="")
            steam_id = input(f"Enter Steam ID (17 digits, e.g., 12345678901234567): {YELLOW}").strip()
            print(RESET, end="")
            game_saves = f"C:/Users/{user_id}/AppData/Roaming/HelloGames/NMS"
            dev_dir = Path(f"st_{steam_id}")
            prod_dir = Path(f"{game_saves}/{dev_dir}")
            is_occupied = hg_lookup(prod_dir)

            if is_occupied:
                print(f'Success! Found {sum(1 for i in range(2, 32, 2) if (prod_dir / f"save{i}.hg").exists())} Saves.')
                break
            else:
                response = input("\nProduction directory appears empty/invalid. Do you want to retry input? (y/n): ").strip().lower()
                if response != 'y':
                    print("Setup aborted. Fix your NMS installation and run again.")
                    sys.exit(1)
                # print("Proceeding with sandbox creation (no real saves detected).")
        except KeyboardInterrupt:
            print(RESET, end="")
            sys.exit(0)


        # if not steam_id.isdigit() or len(steam_id) != 17:
        #     print("Invalid Steam ID. Please try again.")
        #     sys.exit(1)
        
    
    # Save initial config in dev mode
    config = {
        'steam_id': steam_id,
        'game_saves': game_saves,
        'mode': 'dev',
        'hg': is_occupied
    }
    # print(config)
    mode = config['mode']
    game_saves_dir = f"st_{steam_id}"
    show()
    with open(config_file, "w") as f:
        json.dump(config, f, indent=4)
    
    # Offer prod mode switch
    if is_occupied:
        # Setup dev sandbox
        _setup_dev_sandbox(prod_dir, dev_dir)
        # response = input("\nSetup complete! Sandbox created for safe testing.\nSwitch to 'prod' mode now? (y/n): ").strip().lower()
        # if response == 'y':
        #     game_saves_dir = prod_dir
        #     mode = 'prod'
        #     config['mode'] = 'prod'
        #     with open(config_file, "w") as f:
        #         json.dump(config, f, indent=4)
        #     print("Switched to production mode. Be careful - this affects real saves!")
        # else:
        # print("Staying in 'dev' mode. Edit config.json manually to switch to 'prod' later.")
        print("\nSetup complete! Sandbox created for safe testing.\nEdit config.json manually to switch to 'prod' later.\n")
    # else:
    #     print("Staying in dev mode. Once NMS saves are detected, rerun to enable 'prod'.")
    
    # print(f"\nFinal config - Mode: {mode}, Game Saves Dir: {game_saves_dir}")
    
    return {
        'GAME_SAVES_DIR': game_saves_dir,
        'STEAM_ID': steam_id,
        'MODE': mode,
        'game_saves': game_saves,
        'hg': is_occupied
    }

def _setup_dev_sandbox(prod_dir: Path, dev_dir: Path):
    """Creates or updates the dev sandbox by copying .hg files from prod_dir."""

    if dev_dir.exists():
        print(f"Dev sandbox already exists: {dev_dir}\n")
        return
    
    print(f"Creating dev sandbox: {dev_dir}")
    dev_dir.mkdir()
    
    # Copy relevant .hg files (mf_save*.hg and save*.hg)
    copied = 0
    if prod_dir.exists():
        for fname in prod_dir.iterdir():
            if (fname.suffix == '.hg' and 
                (fname.name.startswith('mf_save') or fname.name.startswith('save'))):
                shutil.copy2(fname, dev_dir / fname.name)
                copied += 1
    
    print(f"Dev sandbox created - Copied {copied} save files.")
    # if copied == 0:
    #     print("Note: No save files copied (empty prod dir). Sandbox is ready for testing.")
