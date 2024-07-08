import requests
from functools import lru_cache
from config import get_api_key, prompt_for_api_key
from db import log_multiple_match
from fuzzywuzzy import fuzz
import re

def clean_search_query(query):
    # Log the initial query
    #print(f"Initial query: {query}")

    # Extract year if present
    year_match = re.search(r'\((\d{4})\)|\b(\d{4})\b', query)
    year = year_match.group(1) or year_match.group(2) if year_match else None
    #print(f"Extracted year: {year}")

    # Remove unnecessary parts, including everything after them
    patterns_to_remove = [
        r'\(\d{4}\)',  # Year in parentheses
        r'\b\d{4}\b',  # Year without parentheses
        r'S\d{2}',     # Season identifier
        r'E\d{2}',     # Episode identifier
        r'\d{3,4}p',   # Resolution
        r'BluRay',     # Media type
        r'x\d{3,4}',   # Codec info
        r'HEVC',       # Codec info
        r'\d{1,2}bit', # Bit depth
        r'AAC',        # Audio codec
        r'Season \d+', # Season information
        r'\d+x\d+',    # Episode format like 1x01
        r'Complete',   # 'Complete' marker
        r'Extras',     # 'Extras' marker
        r'\[',         # Start of square brackets
        r'\(',         # Start of parentheses
        r'EDGE2020',   # Release group
        r'EDG',        # Release group short form
    ]

    # Find the earliest occurrence of any pattern
    earliest_pos = len(query)
    for pattern in patterns_to_remove:
        match = re.search(pattern, query, re.IGNORECASE)
        if match and match.start() < earliest_pos:
            earliest_pos = match.start()

    # Cut off the query at the earliest pattern occurrence
    query = query[:earliest_pos].strip()
    #print(f"Query after pattern removal: {query}")

    # Clean up remaining punctuation and whitespace
    query = re.sub(r'[._-]', ' ', query)
    query = re.sub(r'\s+', ' ', query).strip()
    #print(f"Final cleaned query: {query}")

    return query, year

@lru_cache(maxsize=None)
def search_tv_show(query, year=None, id='tmdb', force=False, folder_path=None):
    api_key = get_api_key()
    if not api_key:
        api_key = prompt_for_api_key()

    query, extracted_year = clean_search_query(query)
    if not year and extracted_year:
        year = extracted_year

    def perform_search(year):
        url = "https://api.themoviedb.org/3/search/tv"
        params = {
            'api_key': api_key,
            'query': query
        }
        if year:
            params['first_air_date_year'] = year

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json().get('results', [])
        except requests.exceptions.RequestException as e:
            print(f"Error fetching TMDb data: {e}")
            return []

    #print(f"Performing search with query: {query} and year: {year}")
    results = perform_search(year)

    if not results and year:
        print(f"Retrying search with query: {query} and year: {year + 1}")
        results = perform_search(year + 1)

    if not results and year:
        print(f"Retrying search with query: {query} and year: {year - 1}")
        results = perform_search(year - 1)

    if results:
        query_stripped = query.lower()
        for result in results:
            if result['name'].lower() == query_stripped:
                tmdb_id = result['id']
                show_name = result['name']
                show_year = result['first_air_date'][:4] if result['first_air_date'] else "Unknown Year"
                return f"{show_name} ({show_year}) {{tmdb-{tmdb_id}}}"

        matches = [(result, fuzz.ratio(query.lower(), result['name'].lower())) for result in results]
        best_match = max(matches, key=lambda x: x[1])

        if best_match[1] > 90:
            chosen_show = best_match[0]
        else:
            for result in results:
                match_list = [f"{result['name']} ({result['first_air_date'][:4]}) [tmdb-{result['id']}]"]
                log_multiple_match(query, match_list, folder_path)
            return None

        show_name = chosen_show.get('name')
        first_air_date = chosen_show.get('first_air_date')
        show_year = first_air_date.split('-')[0] if first_air_date else "Unknown Year"
        tmdb_id = chosen_show.get('id')
        proper_name = f"{show_name} ({show_year}) {{tmdb-{tmdb_id}}}"
        return proper_name
    else:
        print(f"No results found for query: {query} year={year}")
        log_multiple_match(query, ["No results found"], folder_path)
        return None

def search_tv_show_by_id(tmdb_id):
    api_key = get_api_key()
    if not api_key:
        api_key = prompt_for_api_key()

    url = f"https://api.themoviedb.org/3/tv/{tmdb_id}"
    params = {
        'api_key': api_key
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        show = response.json()
        show_name = show.get('name')
        first_air_date = show.get('first_air_date')
        show_year = first_air_date.split('-')[0] if first_air_date else "Unknown Year"
        proper_name = f"{show_name} ({show_year}) {{tmdb-{tmdb_id}}}"
        return proper_name
    except requests.exceptions.RequestException as e:
        print(f"Error fetching TMDb data for ID {tmdb_id}: {e}")
        return None

@lru_cache(maxsize=None)
def search_movie(query, year=None):
    api_key = get_api_key()
    if not api_key:
        api_key = prompt_for_api_key()

    url = "https://api.themoviedb.org/3/search/movie"
    params = {
        'api_key': api_key,
        'query': query
    }
    if year:
        params['year'] = year

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        results = response.json().get('results', [])
        if results:
            return results[0]
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching movie data: {e}")
        return None

def tmdb_search(query):
    api_key = get_api_key()
    if not api_key:
        api_key = prompt_for_api_key()

    url = "https://api.themoviedb.org/3/search/tv"
    params = {
        'api_key': api_key,
        'query': query
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        results = response.json().get('results', [])
        return results
    except requests.exceptions.RequestException as e:
        print(f"Error fetching TMDb search results: {e}")
        return []
