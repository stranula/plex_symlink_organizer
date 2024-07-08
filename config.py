import json
import os

SETTINGS_FILE = 'settings.json'

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=4)
    except IOError as e:
        print(f"Error saving settings: {e}")

def get_settings():
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
    except IOError as e:
        print(f"Error loading settings: {e}")
    return {}

def prompt_for_settings():
    settings = {}
    settings['src_dir'] = input("Enter the source directory for your media files: ")
    settings['dest_dir'] = input("Enter the destination directory for TV shows: ")
    settings['dest_dir_movies'] = input("Enter the destination directory for movies: ")
    settings['id'] = input("Enter the default ID type (tmdb/imdb): ")
    settings['tmdb_api_key'] = input("Enter your TMDb API key: ")
    settings['plex_url'] = input("Enter your Plex server URL (e.g., http://localhost:32400): ")
    settings['plex_token'] = input("Enter your Plex token: ")
    settings['plex_tv_section_id'] = input("Enter your Plex library section ID for TV shows: ")
    settings['plex_movie_section_id'] = input("Enter your Plex library section ID for movies: ")

    save_settings(settings)
    return settings

def get_api_key():
    settings = get_settings()
    return settings.get('tmdb_api_key')

def prompt_for_api_key():
    api_key = input("Enter your TMDb API key: ")
    settings = get_settings()
    settings['tmdb_api_key'] = api_key
    save_settings(settings)
    return api_key
