"""Media: the code behind the Media screen and its buttons.

Run in the sandbox as whoever is looking. The pictures are the files'
own: a gallery tile is the file record, and the server makes its
thumbnail (a video's is a frame of it, drawn with ffmpeg). Media keeps two
things of its own: the folders somebody shows (`media.folder`) and the
stars they gave (`media.rating`, by the file's id). Nothing here reads or
changes a file.
"""

from cloudmorrow.quill import Invalid, NotFound, Refused, action, error, toast, ui, view

FILE, FOLDER, RATING = "file", "media.folder", "media.rating"
DRIVE = "my-files"
PHOTO_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".bmp", ".tif", ".tiff", ".avif")
VIDEO_SUFFIXES = (".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts", ".m2ts", ".3gp", ".mpg", ".mpeg", ".ogv")
# Tiles in one go; "Show more" asks for this many again.
PAGE = 300

SHOW = [("", "Photos and videos"), ("photos", "Photos"), ("videos", "Videos")]
STARS = [("", "Any stars")] + [(str(n), "★" * n + ("" if n == 5 else " and up")) for n in range(1, 6)]
SORTS = [("", "Newest first"), ("oldest", "Oldest first"), ("name", "By name"), ("stars", "Most stars first")]


# -- what a file is ----------------------------------------------------------------------
def kind_of(record):
    """'photo', 'video', or None for a file that is neither (or a folder)."""
    if record.get("kind") != "file":
        return None
    name = str(record.get("name") or "").lower()
    mime = str(record.get("mime") or "")
    if mime.startswith("image/") or name.endswith(PHOTO_SUFFIXES):
        return "photo"
    if mime.startswith("video/") or name.endswith(VIDEO_SUFFIXES):
        return "video"
    return None


def plural(count, one, many=None):
    return f"{count} {one if count == 1 else many or one + 's'}"


def clean_path(path):
    return "/".join(part for part in str(path or "").replace("\\", "/").split("/") if part.strip())


def where_said(share, path):
    """A folder as people say it: My Files › Photos, Family › 2026."""
    top = "My Files" if share == DRIVE else share
    return " › ".join([top, *[p for p in path.split("/") if p]])


# -- reading ------------------------------------------------------------------------------
def folders(ctx):
    found = ctx.records.list(FOLDER)
    return sorted(found, key=lambda f: (f.get("share") != DRIVE, str(f.get("share") or ""), str(f["path"]).lower()))


def files_in(ctx, folder):
    """Every photo and video under *folder*; None when the folder is not there (or not theirs)."""
    try:
        listed = ctx.records.list(FILE, share=folder.get("share") or DRIVE, within=folder["path"])
    except (NotFound, Refused, Invalid):
        return None
    return [f for f in listed if kind_of(f)]


def ratings(ctx):
    return {str(r["source"]): r for r in ctx.records.list(RATING)}


def stars_of(rated, file):
    found = rated.get(file.id)
    return int(found["stars"]) if found else 0


def chosen(ctx, name, choices):
    value = str(ctx.params.get(name) or "")
    return value if value in {key for key, _ in choices} else ""


# -- the pictures ------------------------------------------------------------------------
@view("media")
def media(ctx):
    shown = folders(ctx)
    show = chosen(ctx, "show", SHOW)
    least = int(chosen(ctx, "stars", STARS) or 0)
    sort = chosen(ctx, "sort", SORTS)
    only = str(ctx.params.get("folder") or "")
    if only not in {f.id for f in shown}:
        only = ""
    try:
        limit = max(PAGE, int(ctx.params.get("limit") or PAGE))
    except ValueError:
        limit = PAGE

    rated = ratings(ctx)
    everything, missing, seen = [], [], set()
    for folder in shown:
        if only and folder.id != only:
            continue
        found = files_in(ctx, folder)
        if found is None:
            missing.append(where_said(folder.get("share") or DRIVE, folder["path"]))
            continue
        for f in found:
            if f.id not in seen:  # a folder inside another one shown: once
                seen.add(f.id)
                everything.append((folder, f))

    photos = sum(1 for _, f in everything if kind_of(f) == "photo")
    videos = len(everything) - photos
    picked = [
        (folder, f) for folder, f in everything if (not show or kind_of(f) == show[:-1]) and stars_of(rated, f) >= least
    ]
    if sort == "name":
        picked.sort(key=lambda pair: str(pair[1].get("name") or "").lower())
    elif sort == "stars":
        picked.sort(key=lambda pair: str(pair[1].get("modified") or ""), reverse=True)
        picked.sort(key=lambda pair: stars_of(rated, pair[1]), reverse=True)
    else:
        picked.sort(key=lambda pair: str(pair[1].get("modified") or ""), reverse=sort != "oldest")

    tiles = []
    for folder, f in picked[:limit]:
        row = f.to_dict()
        share = folder.get("share") or DRIVE
        row["fields"] = {
            **row["fields"],
            "stars": stars_of(rated, f),
            "where": where_said(share, str(f.get("folder") or "")),
            "badge": "▶ Video" if kind_of(f) == "video" else "",
        }
        tiles.append(row)

    def here(**change):
        params = {"show": show, "stars": str(least or ""), "sort": sort, "folder": only, **change}
        return {k: v for k, v in params.items() if v}

    def menu(choices, current, name):
        label = dict(choices)[current]
        return ui.menu(
            label,
            *(ui.button(said, go="media", params=here(**{name: key})) for key, said in choices if key != current),
        )

    folder_choices = [("", "Every folder")] + [(f.id, where_said(f.get("share") or DRIVE, f["path"])) for f in shown]
    rated_count = sum(1 for _, f in everything if stars_of(rated, f))
    summary = f"{plural(photos, 'photo')} and {plural(videos, 'video')}"
    if rated_count:
        summary += f" · {rated_count} with stars"
    if len(picked) != len(everything):
        summary = f"{len(picked)} of {summary}"

    parts = [
        ui.text("Media", style="title"),
        ui.row(
            menu(SHOW, show, "show"),
            menu(STARS, str(least or ""), "stars"),
            menu(folder_choices, only, "folder"),
            menu(SORTS, sort, "sort"),
        ),
        ui.text(summary, style="muted"),
        ui.gallery(
            tiles,
            title="name",
            subtitle="where",
            badge="badge",
            stars="stars",
            rate="rate",
            empty=(
                "Nothing with these filters."
                if everything
                else "No photos or videos yet. Put them in My Files › Photos or My Files › Videos — from Files, "
                "the phone's camera, the desktop app's mount or WebDAV — or add another folder."
            ),
        ),
    ]
    if len(picked) > limit:
        parts.append(
            ui.button(f"Show {min(PAGE, len(picked) - limit)} more", go="media", params=here(limit=str(limit + PAGE)))
        )
    if missing:
        parts.append(ui.text(f"Not there (yet): {', '.join(missing)}.", style="small"))
    parts += [
        ui.divider(),
        ui.text("Folders", style="subtitle"),
        ui.text("Media shows the photos and videos in these folders, and in every folder inside them.", style="muted"),
        ui.table(
            folder_rows(ctx, shown),
            columns=[("Folder", "where"), ("Holds", "holds")],
            open=False,
            actions=["remove-folder"],
            empty="No folders: Media shows nothing until you add one.",
        ),
        ui.row(ui.button("Add a folder", action="add-folder"), ui.button("Refresh", action="refresh")),
    ]
    return ui.stack(*parts)


def folder_rows(ctx, shown):
    rows = []
    for folder in shown:
        found = files_in(ctx, folder)
        if found is None:
            holds = "not there (yet)"
        else:
            photos = sum(1 for f in found if kind_of(f) == "photo")
            holds = f"{plural(photos, 'photo')}, {plural(len(found) - photos, 'video')}"
        row = folder.to_dict()
        row["fields"] = {
            **row["fields"],
            "where": where_said(folder.get("share") or DRIVE, folder["path"]),
            "holds": holds,
        }
        rows.append(row)
    return rows


# -- buttons ---------------------------------------------------------------------------------
@action("rate")
def rate(ctx, file, stars=0):
    if kind_of(file) is None:
        return error(f"{file['name']} is not a photo or a video")
    if not 0 <= int(stars) <= 5:
        return error("Stars are 0 to 5")
    stars = int(stars)
    found = ctx.records.list(RATING, source=file.id)
    if stars == 0:
        for rating in found:
            ctx.records.delete(RATING, rating.id)
        return None
    if found:
        first, *more = found
        ctx.records.patch(RATING, first.id, {"stars": stars, "name": file["name"]}, rev=first.rev)
        for rating in more:
            ctx.records.delete(RATING, rating.id)
    else:
        ctx.records.create(RATING, source=file.id, name=file["name"], stars=stars)
    return None


@action("add_folder")
def add_folder(ctx, path, share=""):
    share = (share or "").strip() or DRIVE
    path = clean_path(path)
    if not path:
        return error("Say which folder, like Holiday/2026")
    said = where_said(share, path)
    if any(f["path"].lower() == path.lower() and (f.get("share") or DRIVE) == share for f in folders(ctx)):
        return error(f"{said} is shown already")
    if files_in(ctx, {"share": share, "path": path}) is None:
        return error(f"There is no folder {said}")
    ctx.records.create(FOLDER, path=path, share=share)
    return toast(f"Showing {said}")


@action("remove_folder")
def remove_folder(ctx, folder):
    ctx.records.delete(FOLDER, folder.id)
    return toast(f"{where_said(folder.get('share') or DRIVE, folder['path'])} is no longer shown")


@action("refresh")
def refresh(ctx):
    return None
