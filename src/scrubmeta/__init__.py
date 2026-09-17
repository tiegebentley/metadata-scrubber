"""
scrubmeta — strip and randomize metadata on images/videos.

INTENDED USE
------------
This tool exists for personal privacy on files you own: stripping GPS and
device fingerprints from photos before posting them, sanitizing home-video
metadata before sending to family, removing "Edited in <software>" tags from
personal creative work, and similar.

It is NOT built for evading platform moderation, trust-and-safety systems,
content-provenance standards (C2PA, IPTC-origin, watermarks), copyright
detection, or concealing the origin of media in harassment, fraud,
non-consensual intimate imagery, CSAM, or any other illegal use.

See MISSION.md in the repo for the full scope.
"""

__version__ = "0.1.0"

INTENDED_USE_NOTICE = (
    "scrubmeta strips metadata from files YOU OWN, for personal privacy. "
    "It is not for evading moderation, provenance, or copyright detection. "
    "By using it you confirm you own the content you're processing."
)
