import os
import time
import spotipy
import argparse

from spotipy.oauth2 import SpotifyPKCE
from backup import backup
from clean_library import clean_library
from restore import restore
from analyze import analyze
from save_profile import save_profile

client_id = "23fdcace6f3d46ce985f725902d8e38a"
redirect_uri = "http://127.0.0.1:3000/authed"
scope = " ".join(
    [
        "user-library-read",
        "user-library-modify",
        "playlist-read-private",
        "playlist-read-collaborative",
        "playlist-modify-private",
        "playlist-modify-public",
        "user-follow-read",
        "user-follow-modify",
    ]
)

parser = argparse.ArgumentParser(description="Backup and restore spotify library")
parser.add_argument("--backup", action="store_true")
parser.add_argument("--profile")
parser.add_argument("--playlist")
parser.add_argument("--file")
args = parser.parse_args()

import json

TOKEN_DIR = ".tokens"
if not os.path.exists(TOKEN_DIR):
    os.makedirs(TOKEN_DIR)

token_path = None
if args.profile:
    token_path = os.path.join(TOKEN_DIR, args.profile)

if not token_path and not (args.backup or args.file):
    # Interactive selection
    tokens = [f for f in os.listdir(TOKEN_DIR) if not f.startswith(".")]
    
    if not tokens:
        print("No tokens found. Starting new login.")
        token_path = os.path.join(TOKEN_DIR, ".temp_token")
    else:
        print("Select an account:")
        for i, t in enumerate(tokens):
            print(f"{i + 1}. {t}")
        print(f"{len(tokens) + 1}. New Login")
        
        try:
            selection = input("Selection: ")
            if not selection:
                quit()
            selection = int(selection)
            if 1 <= selection <= len(tokens):
                token_path = os.path.join(TOKEN_DIR, tokens[selection - 1])
            elif selection == len(tokens) + 1:
                token_path = os.path.join(TOKEN_DIR, ".temp_token")
            else:
                quit()
        except ValueError:
            quit()
elif not token_path:
    # Automated but no profile specified, try logical default
    tokens = [f for f in os.listdir(TOKEN_DIR) if not f.startswith(".")]
    if len(tokens) == 1:
        token_path = os.path.join(TOKEN_DIR, tokens[0])
    elif not tokens:
        token_path = os.path.join(TOKEN_DIR, ".temp_token")
    else:
        print("Error: Multiple profiles found. Please specify --profile <email>")
        quit()

if os.path.exists(token_path):
    try:
        with open(token_path, 'r') as f:
            token_data = json.load(f)
            if token_data.get('expires_at') and token_data['expires_at'] < time.time():
                print(f"Token for {os.path.basename(token_path)} expired. re-authenticating...")
                # We can't easily force re-auth without clearing, but Spotipy might auto-refresh.
                # If explicitly expired and user wants browser, we could os.remove(token_path).
                # But let's try standard flow first.
    except Exception:
        pass

auth_manager = SpotifyPKCE(
    scope=scope,
    client_id=client_id,
    redirect_uri=redirect_uri,
    cache_path=token_path,
)

if not auth_manager.validate_token(auth_manager.get_cached_token()):
    print(
        "If your browser doesn't open automatically, open",
        auth_manager.get_authorize_url(),
    )

sp = spotipy.Spotify(auth_manager=auth_manager)

if os.path.basename(token_path) == ".temp_token":
    try:
        user_info = sp.me()
        user_id = user_info['uri'].split(':')[-1]
        display_name = user_info['display_name']
        # Sanitize display_name for filename
        safe_display_name = "".join(c for c in display_name if c.isalnum() or c in (' ', '-', '_')).strip()
        new_filename = f"{safe_display_name}-{user_id}"
        
        new_path = os.path.join(TOKEN_DIR, new_filename)
        if os.path.exists(token_path):
             # Save current token to new path
             # spotipy saves to token_path (temp)
             # We rename temp to new
             if os.path.exists(new_path):
                 os.remove(new_path)
             os.rename(token_path, new_path)
             token_path = new_path
             print(f"Token saved as {new_filename}")
    except Exception as e:
        print(f"Warning: Could not rename token file: {e}")

def get_backup_path(sp):
    user_info = sp.me()
    user_id = user_info['uri'].split(':')[-1]
    display_name = user_info['display_name']
    safe_display_name = "".join(c for c in display_name if c.isalnum() or c in (' ', '-', '_')).strip()
    return os.path.join("backup", f"{safe_display_name}-{user_id}")


def select_backup_source():
    root = "backup"
    if not os.path.exists(root):
        print("Backup directory not found.")
        return None
        
    options = []
    
    # Check root itself (Legacy support)
    if os.path.exists(os.path.join(root, "liked-songs.json")):
        options.append(("Root (Legacy)", root))
        
    # Check subfolders
    for d in sorted(os.listdir(root)):
        path = os.path.join(root, d)
        if os.path.isdir(path) and not d.startswith("."):
            if os.path.exists(os.path.join(path, "liked-songs.json")):
                options.append((d, path))
    
    if not options:
        print("No valid backups found (looking for liked-songs.json).")
        return None

    print("\nSelect backup to restore:")
    for i, (name, path) in enumerate(options):
        print(f"{i + 1}. {name}")
        
    try:
        selection = input("Selection: ")
        if not selection:
            return None
        index = int(selection) - 1
        if 0 <= index < len(options):
            return options[index][1]
    except ValueError:
        pass
    print("Invalid selection")
    return None


choice = (
    "1"
    if args.backup
    else "5"
    if args.file
    else "6"
    if args.profile
    else input(
        """What would you like to do? Available:
1. Backup
2. Quick restore (doesn't preserve order of liked songs)
3. Restore (preserves order of liked songs)
4. [DANGEROUS] Clean library
5. Analyze playlist
6. Store a user's profile

Note that while quick restore loses order for liked songs, playlists are always ordered correctly.

[1/2/3/4/5/6/q]: """
    )
)

if choice == "1":
    backup_root = get_backup_path(sp)
    if args.playlist:
        backup(sp, playlist_name=args.playlist, root_path=backup_root)
    else:
        backup(sp, root_path=backup_root)
elif choice == "2":
    backup_root = select_backup_source()
    if backup_root:
        restore(sp, True, root_path=backup_root)
elif choice == "3":
    backup_root = select_backup_source()
    if backup_root:
        restore(sp, False, root_path=backup_root)
elif choice == "4":
    confirm = input(
        f"[{sp.me()['display_name'].upper()}] This will delete everything in your library, including liked songs, playlists, albums and followed artists. Are you sure you want to continue? [y/n] "
    )
    if confirm == "y":
        clean_library(sp)
    else:
        quit()
elif choice == "5":
    analyze(args.file)
elif choice == "6":
    save_profile(sp, args.profile)
else:
    quit()
