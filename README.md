This set of scripts was inspired by https://github.com/mercuryy-1337/debridshowrenamer is intended to work with zurg https://github.com/debridmediamanager/zurg-testing and/or pd_zurg https://github.com/I-am-PUID-0/pd_zurg/

When Zurg is mounted, I have all of the playable files load into a /torrents/ folder and then use this script to sort them into:
   - Movies
       - Uncleaned
       - Cleaned
   - Shows
       - Uncleaned
       - Cleaned

The first set of sorting just sorts based on if the folder has the SXXEXX series format in it. If it does, it will be symlinked into Shows/Uncleaned, if it does not, the largest file will be symlinked into Movies/Uncleaned.
As of now, movies do not undergo further processing.

Series, goes through cleaning in order to search tmdb to try to create symlinks to match Plex formatting. If the folder can't be matched, it will be saved until the end for the user to manually assign the tmdb-id or search tmdb to make the correct association.

The script is run by running symlinkcreator.py. It will then ask you for the required settings to run correctly.

Upon running, and completing the first pass, the script will check the src_dir folder every 10 seconds for any changes. If there are any detected, it will process these new files and then reload the appropriate library in the plex server.
