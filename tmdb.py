import requests
from functools import lru_cache
from config import get_overseer_settings, get_api_key, prompt_for_api_key
from db import store_tmdb_series_name, get_tmdb_series_name, log_multiple_match, build_inverted_index, search_inverted_index
from fuzzywuzzy import fuzz
import re

def clean_search_query(query):
    year_match = re.search(r'\((\d{4})\)|\b(\d{4})\b', query)
    year = year_match.group(1) or year_match.group(2) if year_match else None
    query = re.sub(r'\([^)]*\)|\{[^}]*\}', '', query)

    patterns_to_remove = [
        r'\(\d{4}\)',  
        r'\b\d{4}\b',  
        r'S\d{2}',     
        r'E\d{2}',     
        r'\d{3,4}p',   
        r'BluRay',     
        r'x\d{3,4}',   
        r'HEVC',       
        r'\d{1,2}bit', 
        r'AAC',        
        r'Season \d+', 
        r'\d+x\d+',    
        r'Complete',   
        r'Extras',     
        r'\[',         
        r'\(',         
    ]
    
    earliest_pos = len(query)
    for pattern in patterns_to_remove:
        match = re.search(pattern, query, re.IGNORECASE)
        if match and match.start() < earliest_pos:
            earliest_pos = match.start()
    
    query = query[:earliest_pos].strip()
    query = re.sub(r'[._-]', ' ', query)
    query = re.sub(r'\s+', ' ', query).strip()
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

    results = perform_search(year)

    if not results and year:
        results = perform_search(year + 1)

    if not results and year:
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
            return None

        show_name = chosen_show.get('name')
        first_air_date = chosen_show.get('first_air_date')
        show_year = first_air_date.split('-')[0] if first_air_date else "Unknown Year"
        tmdb_id = chosen_show.get('id')
        proper_name = f"{show_name} ({show_year}) {{tmdb-{tmdb_id}}}"
        return proper_name
    else:
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

def get_overseer_requests():
    overseer_api_address, overseer_api_key = get_overseer_settings()
    if not overseer_api_address or not overseer_api_key:
        print("Overseer API address or key is not set.")
        return []

    url = f"{overseer_api_address}/api/v1/request"
    headers = {
        "X-Api-Key": overseer_api_key,
        "accept": "application/json"
    }

    all_requests = []
    skip = 0
    take = 2000
    while True:
        params = {
            "take": take,
            "skip": skip,
            "sort": "added"
        }
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            if not results:
                break
            all_requests.extend(results)
            skip += take
        except requests.exceptions.RequestException as e:
            print(f"Error fetching Overseer data: {e}")
            break

    return all_requests

def fetch_tmdb_series_name(tmdb_id):
    api_key = get_api_key()
    url = f"https://api.themoviedb.org/3/tv/{tmdb_id}?api_key={api_key}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        series_name = data.get('name')
        year = data.get('first_air_date', '').split('-')[0] if data.get('first_air_date') else None
        return series_name, year
    except requests.exceptions.RequestException as e:
        print(f"Error fetching TMDb data for ID {tmdb_id}: {e}")
        return None, None

def update_series_names_from_overseer():
    requests_data = get_overseer_requests()
    tmdb_id_count = 0
    missing_tmdb_id_count = 0
    for request in requests_data:
        media = request.get('media', {})
        tmdb_id = media.get('tmdbId')
        if tmdb_id:
            if request.get('type') == 'tv':
                tmdb_id_count += 1
                series_name, year = get_tmdb_series_name(tmdb_id)
                if not series_name:
                    series_name, year = fetch_tmdb_series_name(tmdb_id)
                    if series_name:
                        store_tmdb_series_name(tmdb_id, series_name, year)
        else:
            missing_tmdb_id_count += 1
            print(f"Missing TMDb ID for request: {request}")

    print(f"Total TMDb IDs found: {tmdb_id_count}")
    print(f"Total requests without TMDb ID: {missing_tmdb_id_count}")


def search_series_using_inverted_index(query):
    inverted_index = build_inverted_index()
    results = search_inverted_index(query, inverted_index)
    return results

def search_tv_show_with_year_range(query, year, id, force, folder_path, range_delta):
    if year is not None:
        for delta in range(-range_delta, range_delta + 1):
            result = search_tv_show(query, year + delta, id=id, force=force, folder_path=folder_path)
            if result:
                return result
    else:
        result = search_tv_show(query, year, id=id, force=force, folder_path=folder_path)
        if result:
            return result
    return None