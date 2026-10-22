"""Media's tests: the real record store, files and gate, and quill.py, on this machine.

`cm quill test` runs them; `cm quill test --sandbox` runs the same tests
with quill.py in the sandbox, as a server runs it.
"""

import contextlib

import pytest
from cloudmorrow.quill.testing import Harness

FILE, FOLDER, RATING = "file", "media.folder", "media.rating"


@pytest.fixture()
def q():
    with Harness(".") as harness:
        yield harness


def a_file(q, name, folder):
    """A file in My Files, put there the way an upload is: a few bytes with the right name is enough."""
    parts = folder.split("/")
    for depth in range(1, len(parts) + 1):
        with contextlib.suppress(Exception):  # there already
            q.seed(FILE, share="my-files", path="/".join(parts[:depth]), kind="folder")
    part = q._tmp / name
    part.write_bytes(b"\x00" * 16)
    q.state.records.put(q._principal(), FILE, {"share": "my-files", "folder": folder, "name": name}, part)
    return next(f for f in q.list(FILE, share="my-files", folder=folder) if f["name"] == name)


def gallery(q, **params):
    view = q.view("media", **params)
    (found,) = view.find("gallery")
    return found


def names(tiles):
    return sorted(t["fields"]["name"] for t in tiles["records"])


def test_everybody_starts_with_photos_and_videos(q):
    assert sorted(f["path"] for f in q.list(FOLDER)) == ["Photos", "Videos"]


def test_the_photos_and_videos_in_the_folders_are_tiles_and_nothing_else_is(q):
    a_file(q, "sunset.jpg", "Photos")
    a_file(q, "beach.png", "Photos/Holiday 2026")
    a_file(q, "waves.mp4", "Videos")
    a_file(q, "notes.txt", "Photos")
    a_file(q, "elsewhere.jpg", "Documents")
    tiles = gallery(q)
    assert names(tiles) == ["beach.png", "sunset.jpg", "waves.mp4"]
    assert tiles["rate"] == "rate" and tiles["stars"] == "stars"
    by_name = {t["fields"]["name"]: t["fields"] for t in tiles["records"]}
    assert by_name["beach.png"]["where"] == "My Files › Photos › Holiday 2026"
    assert by_name["waves.mp4"]["badge"] == "▶ Video" and by_name["sunset.jpg"]["badge"] == ""
    assert "2 photos and 1 video" in q.view("media").text()


def test_stars_are_given_changed_and_taken_away(q):
    photo = a_file(q, "sunset.jpg", "Photos")
    assert q.act("rate", photo, stars=4).ok
    assert [(r["source"], r["stars"]) for r in q.list(RATING)] == [(photo.id, 4)]
    assert gallery(q)["records"][0]["fields"]["stars"] == 4
    assert q.act("rate", photo, stars=2).ok
    assert [r["stars"] for r in q.list(RATING)] == [2]
    assert q.act("rate", photo, stars=0).ok
    assert q.list(RATING) == []
    assert "0 to 5" in q.act("rate", photo, stars=6).error
    document = a_file(q, "notes.txt", "Photos")
    assert "not a photo or a video" in q.act("rate", document, stars=3).error


def test_the_filters_pick_by_kind_stars_and_folder_and_the_sort_orders(q):
    a = a_file(q, "a.jpg", "Photos")
    b = a_file(q, "b.mp4", "Videos")
    a_file(q, "c.jpg", "Photos")
    q.act("rate", a, stars=5)
    q.act("rate", b, stars=3)
    assert names(gallery(q, show="photos")) == ["a.jpg", "c.jpg"]
    assert names(gallery(q, show="videos")) == ["b.mp4"]
    assert names(gallery(q, stars="3")) == ["a.jpg", "b.mp4"]
    assert names(gallery(q, stars="4")) == ["a.jpg"]
    videos = next(f for f in q.list(FOLDER) if f["path"] == "Videos")
    assert names(gallery(q, folder=videos.id)) == ["b.mp4"]
    by_stars = [t["fields"]["name"] for t in gallery(q, sort="stars")["records"]]
    assert by_stars[:2] == ["a.jpg", "b.mp4"]
    assert [t["fields"]["name"] for t in gallery(q, sort="name")["records"]] == ["a.jpg", "b.mp4", "c.jpg"]
    assert "1 of 2 photos and 1 video" in q.view("media", stars="4").text()
    # Nonsense in the address is no filter at all.
    assert names(gallery(q, show="cats", stars="9", folder="nope")) == ["a.jpg", "b.mp4", "c.jpg"]


def test_another_folder_can_be_added_and_taken_away(q):
    a_file(q, "old.jpg", "Scans/1990")
    assert names(gallery(q)) == []
    assert "There is no folder" in q.act("add-folder", path="Nowhere").error
    done = q.act("add-folder", path="/Scans/")
    assert done.ok and done.toast == "Showing My Files › Scans"
    assert "shown already" in q.act("add-folder", path="scans").error
    assert names(gallery(q)) == ["old.jpg"]
    assert "My Files › Scans" in q.view("media").text()
    scans = next(f for f in q.list(FOLDER) if f["path"] == "Scans")
    assert q.act("remove-folder", scans).ok
    assert names(gallery(q)) == []
    assert q.list(FILE, share="my-files", folder="Scans/1990"), "the files stay where they are"


def test_a_folder_inside_another_one_shown_shows_its_files_once(q):
    a_file(q, "one.jpg", "Photos/Trip")
    q.act("add-folder", path="Photos/Trip")
    assert names(gallery(q)) == ["one.jpg"]


def test_a_folder_that_is_gone_is_said_not_failed(q):
    q.seed(FOLDER, path="Gone", share="my-files")
    view = q.view("media")
    assert "Not there (yet): My Files › Gone" in view.text()


def test_nothing_yet_says_where_to_put_them(q):
    assert "No photos or videos yet" in q.view("media").text()
