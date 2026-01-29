import re
import unicodedata
import subprocess

from json import dump
from spotipy import Spotify
from pathlib import Path
from tabulate import tabulate
from shutil import rmtree
from typing import List, Dict, Any, Tuple, Optional


def get_useful_info_for_tracks(tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "name": item["track"]["name"],
            "artists": [artist["name"] for artist in item["track"]["artists"]],
            "release_date": item["track"]["album"]["release_date"],
            "id": item["track"]["id"],
            "isrc": item["track"]["external_ids"].get("isrc"),
            "added_at": item["added_at"],
        }
        for item in tracks
        if item["track"]
    ]


def get_useful_info_for_playlists(playlists: List[Dict[str, Any]], owner_id: str) -> Tuple[List[Dict[str, Any]], List[List[str]]]:
    cleaned = []
    blends = []

    for playlist in playlists:
        if playlist["description"].lower().strip().startswith("a blend of music for"):
            blends.append(playlist["name"].split(" + "))
            continue

        playlist_type = None

        if playlist["owner"]["id"] == owner_id or (
            playlist["owner"]["id"] == "spotify"
            and (
                playlist["name"].lower().startswith("your top songs")
                or "for you" in playlist["name"].lower()
            )
        ):
            playlist_type = "owned"
        elif playlist["collaborative"] is True:
            playlist_type = "collaborative"
        else:
            playlist_type = "followed"

        cleaned.append(
            {
                "name": playlist["name"],
                "description": playlist["description"],
                "id": playlist["id"],
                "owner": {
                    "display_name": playlist["owner"]["display_name"],
                    "id": playlist["owner"]["id"],
                },
                "type": playlist_type,
                "public": playlist["public"],
            }
        )

    return cleaned, blends


def get_useful_info_for_albums(albums: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "name": album["album"]["name"],
            "artists": [artist["name"] for artist in album["album"]["artists"]],
            "id": album["album"]["id"],
            "upc": album["album"]["external_ids"]["upc"],
            "added_at": album["added_at"],
        }
        for album in albums
    ]


def get_useful_info_for_followed(artists: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    return [
        {
            "name": artist["name"],
            "id": artist["id"],
        }
        for artist in artists
    ]


def get_all_items(sp: Spotify, results: Dict[str, Any], key: Optional[str] = None) -> List[Any]:
    items = results["items"]

    while results["next"]:
        results = sp.next(results)
        if key:
            results = results[key]
        items.extend(results["items"])

    return items


def get_liked_songs(sp: Spotify):
    results = sp.current_user_saved_tracks(limit=50)
    items = results["items"]

    while len(results["items"]) > 0:
        results = sp.current_user_saved_tracks(limit=50, offset=results["offset"] + 50)
        items.extend(results["items"])

    return get_useful_info_for_tracks(items)


def get_playlists(sp: Spotify):
    results = sp.current_user_playlists(limit=50)
    items = results["items"]

    while len(results["items"]) > 0:
        results = sp.current_user_playlists(limit=50, offset=results["offset"] + 50)
        items.extend(results["items"])

    return get_useful_info_for_playlists(
        [item for item in items if item is not None], sp.me()["id"]
    )


def get_albums(sp: Spotify):
    albums = get_all_items(sp, sp.current_user_saved_albums(limit=50))
    return get_useful_info_for_albums(albums)


def get_followed_artists(sp: Spotify):
    artists = get_all_items(
        sp, sp.current_user_followed_artists(limit=50)["artists"], "artists"
    )
    return get_useful_info_for_followed(artists)


def get_playlist_tracks(sp: Spotify, playlist):
    results = sp.playlist_tracks(playlist["id"], limit=50)
    items = results["items"]

    while len(results["items"]) > 0:
        results = sp.playlist_tracks(
            playlist["id"], limit=50, offset=results["offset"] + 50
        )
        items.extend(results["items"])

    return get_useful_info_for_tracks(items)


def slugify(value: Any) -> str:
    value = (
        unicodedata.normalize("NFKD", str(value))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-_")


def write(data: Any, path: str) -> None:
    dump(data, open(path, "w"), indent="\t")


def backup(sp: Spotify, playlist_name: Optional[str] = None, root_path: str = "backup") -> None:
    print("Backing up... This might take a while")

    backup_dir = Path(root_path)
    backup_dir.mkdir(parents=True, exist_ok=True)

    if not playlist_name:

        rmtree(f"{root_path}/playlists", ignore_errors=True)
        Path(f"{root_path}/liked-songs.json").unlink(missing_ok=True)
        Path(f"{root_path}/saved-albums.json").unlink(missing_ok=True)
        Path(f"{root_path}/followed-artists.json").unlink(missing_ok=True)
        Path(f"{root_path}/blend-names.json").unlink(missing_ok=True)

    Path(f"{root_path}/playlists/owned").mkdir(parents=True, exist_ok=True)
    Path(f"{root_path}/playlists/collaborative").mkdir(parents=True, exist_ok=True)
    Path(f"{root_path}/playlists/followed").mkdir(parents=True, exist_ok=True)

    if not playlist_name:
        print("Backing up liked songs...")
        songs = get_liked_songs(sp)
        write(songs, f"{root_path}/liked-songs.json")

        print("Backing up albums...")
        albums = get_albums(sp)
        write(albums, f"{root_path}/saved-albums.json")

        print("Backing up followed artists...")
        followed = get_followed_artists(sp)
        write(followed, f"{root_path}/followed-artists.json")

    print("Backing up playlists...")
    playlists, blends = get_playlists(sp)
    for playlist in playlists:
        if playlist_name and playlist["name"] != playlist_name:
            continue

        playlist["tracks"] = get_playlist_tracks(sp, playlist)
        write(
            playlist,
            f"{root_path}/playlists/{playlist['type']}/{slugify(playlist['name'])}-{slugify(playlist['id'])}.json",
        )

    if not playlist_name:
        write(blends, f"{root_path}/blend-names.json")

        print("Commiting and pushing changes...")

        print("Backup complete!")
        print("* Your liked songs were backed up")
        print("* Your followed artists were backed up")
        print("* Your saved albums were backed up")
        print("* Names of people in blends were backed up (excluding large blends)")
        print("* The following playlists were backed up:")

        print(
            tabulate(
                [[x["name"], x["type"]] for x in playlists],
                headers=["Name", "Type"],
                showindex=range(1, len(playlists) + 1),
            )
        )
