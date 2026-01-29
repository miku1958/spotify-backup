from json import load
from os import listdir
from time import sleep, time
from spotipy import Spotify
from collections import deque


def restore(sp: Spotify, quick: bool = False, root_path: str = "backup"):
    print(f"Restoring liked songs...")
    liked_songs = load(open(f"{root_path}/liked-songs.json", "r"))
    ids = [item["id"] for item in reversed(liked_songs)]

    if quick:
        batches = [ids[i : i + 50] for i in range(0, len(ids), 50)]
        for batch in batches:
            sp.current_user_saved_tracks_add(batch)
    else:
        recent_execution_times = deque(maxlen=10)  # 保存最近10次的执行时间
        min_execution_time = float('inf')
        max_execution_time = 0
        total_start_time = time()
        for i, song_id in enumerate(ids):
            print(f"\rRestoring song: {i + 1} of {len(ids)}, Minimum recent 10 execution time: {min_execution_time:.3f}s, Max execution time: {max_execution_time:.3f}s", end='', flush=True)
            start_time = time()
            sp.current_user_saved_tracks_add([song_id])
            execution_time = time() - start_time
            recent_execution_times.append(execution_time)
            min_execution_time = min(recent_execution_times)
            max_execution_time = max(max_execution_time, execution_time)
            if i < len(ids) - 1:
                sleep_time = max(0, 1 - min_execution_time)
                if sleep_time > 0:
                    sleep(sleep_time)
        total_time = time() - total_start_time
        print(f"\nTotal time: {total_time:.2f}s ({total_time/60:.2f}min)")

    print(f"Restoring playlists...")
    playlists = (
        [
            load(open(f"{root_path}/playlists/owned/{playlist}", "r"))
            for playlist in listdir(f"{root_path}/playlists/owned")
        ]
        + [
            load(open(f"{root_path}/playlists/collaborative/{playlist}", "r"))
            for playlist in listdir(f"{root_path}/playlists/collaborative")
        ]
        + [
            load(open(f"{root_path}/playlists/followed/{playlist}", "r"))
            for playlist in listdir(f"{root_path}/playlists/followed")
        ]
    )

    user_id = sp.me()["id"]

    for playlist in playlists:
        if playlist["type"] == "followed":
            try:
                sp.current_user_follow_playlist(playlist["id"])
            except:
                print(f"Couldn't follow playlist: ${playlist['name']}")
        else:
            new_playlist = sp.user_playlist_create(
                user_id,
                playlist["name"],
                public=playlist["public"],
                collaborative=playlist["type"] == "collaborative",
                description=playlist["description"],
            )

            ids = [track["id"] for track in playlist["tracks"]]
            batches = [ids[i : i + 50] for i in range(0, len(ids), 50)]

            for batch in batches:
                sp.user_playlist_add_tracks(user_id, new_playlist["id"], batch)

    print(f"Restoring saved albums...")
    saved_albums = load(open("backup/saved-albums.json", "r"))

    ids = [item["id"] for item in saved_albums]
    batches = [ids[i : i + 50] for i in range(0, len(ids), 50)]

    for batch in batches:
        sp.current_user_saved_albums_add(batch)

    print(f"Restoring artists...")
    followed = load(open("backup/followed-artists.json", "r"))

    ids = [item["id"] for item in followed]
    batches = [ids[i : i + 50] for i in range(0, len(ids), 50)]

    for batch in batches:
        sp.user_follow_artists(batch)
