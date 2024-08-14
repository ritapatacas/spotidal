========
spotidal
========

**⚠ proceed with caution, this is a lazy work in progress ⚠**


| A threesome of apps that offers you love:
|  Improve your quality of life by syncing your spotify and tidal playlists.
|  Help mitigate the capitalistic rivalry (and monopoly) that rules music streaming platforms!



Features
========
**Transfer all your spotify playlists to tidal**

workflow
---------
#. apis auth
#. fetch playlists data
#. optional selection of playlists
#. look for each track and add to tidal playlist - an easy sync: check if playlist already exists, skip duplicates and log all 404 tracks.

.. 5. tidal-to-master will get you tidal playlists in master quality.

todo
-------
Add tidal download masters feature
Add tidal to spotify transfer feature
Rescan not found tracks
UI

credits
=======

| This package was created with cookiecutter_ and this project `template`_.
| Using mainly `spotipy` and `tidalapi` libraries, but also a lot of other stuff we will mention in the future.

.. _cookiecutter: https://github.com/audreyr/cookiecutter
.. _`template`: https://github.com/audreyr/cookiecutter-pypackage
