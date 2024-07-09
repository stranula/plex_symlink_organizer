import os
import argparse
import shutil
import re
import time
from datetime import datetime, timedelta
from colorama import init, Fore, Style
from config import get_settings, prompt_for_settings
from db import initialize_db, log_processed_folder, get_processed_folders, log_multiple_match, get_multiple_matches, get_unresolved_multiple_matches, update_multiple_match_solution, delete_multiple_match, log_media_item, build_inverted_index, search_inverted_index
from tmdb import search_tv_show, search_tv_show_by_id, search_movie, tmdb_search, update_series_names_from_overseer
from utils import extract_year, extract_resolution, extract_folder_year, sanitize_title
from collections import defaultdict

def group_matches_by_folder(matches):
    grouped = defaultdict(list)
    for match in matches:
        id, original_name, possible_matches, folder_paths = match
        for folder_path in folder_paths:
            grouped[folder_path].append((id, original_name, possible_matches))
    return grouped

init(autoreset=True)

processed_files = set()

def clean_filename(filename):
    """Clean up the filename to avoid double dashes and other inconsistencies."""
    filename = re.sub(r' - - ', ' - ', filename)
    filename = re.sub(r' +', ' ', filename).strip()  # Remove extra spaces
    filename = re.sub(r' -$', '', filename)  # Remove trailing dash
    return filename

# symlinkcreator.py

# symlinkcreator.py

def create_symlinks(src_dir, dest_dir, dest_dir_movies, force=False, id='tmdb', quick_scan=False):
    cleaned_dir = os.path.join(dest_dir, "Cleaned")
    uncleaned_dir = os.path.join(dest_dir, "Uncleaned")
    cleaned_dir_movies = os.path.join(dest_dir_movies, "Cleaned")
    uncleaned_dir_movies = os.path.join(dest_dir_movies, "Uncleaned")

    os.makedirs(cleaned_dir, exist_ok=True)
    os.makedirs(uncleaned_dir, exist_ok=True)
    os.makedirs(cleaned_dir_movies, exist_ok=True)
    os.makedirs(uncleaned_dir_movies, exist_ok=True)

    processed_folders = get_processed_folders()
    multiple_matches = get_multiple_matches()

    if quick_scan:
        dirs_to_check = [os.path.join(src_dir, d) for d in os.listdir(src_dir) if os.path.isdir(os.path.join(src_dir, d))]
    else:
        dirs_to_check = []
        for root, dirs, files in os.walk(src_dir):
            dirs_to_check.append(root)

    inverted_index = build_inverted_index()

    for root in dirs_to_check:
        folder_name = os.path.basename(root)
        parent_folder_name = os.path.basename(os.path.dirname(root))
        combined_folder_name = os.path.join(parent_folder_name, folder_name)

        if combined_folder_name == os.path.basename(src_dir):
            continue

        if combined_folder_name in processed_folders and quick_scan:
            continue
        
        log_processed_folder(combined_folder_name, 'processing')
        
        skip_folder = False
        contains_episode_match = False

        for file in os.listdir(root):
            src_file = os.path.join(root, file)

            if src_file in processed_files:
                continue

            if re.search(r'(S\d{2} ?E\d{2})', file, re.IGNORECASE) or re.search(r'Season|Seasons', folder_name, re.IGNORECASE):
                contains_episode_match = True
                break

        if not contains_episode_match:
            for file in os.listdir(root):
                src_file = os.path.join(root, file)

                if src_file in processed_files:
                    continue

                processed_files.add(src_file)
                # Process as movie
                relative_path = os.path.relpath(src_file, src_dir)
                uncleaned_dest_file = os.path.join(uncleaned_dir_movies, relative_path)
                os.makedirs(os.path.dirname(uncleaned_dest_file), exist_ok=True)
                if not os.path.exists(uncleaned_dest_file):
                    os.symlink(src_file, uncleaned_dest_file)
                    print(f"Created symlink: {uncleaned_dest_file} -> {src_file}")
                log_media_item(src_file, uncleaned_dest_file, tmdb_id=None)  # Pass tmdb_id as None for movies
            continue

        show_folder = None
        log_failure = False  # Initialize a flag to log failure only if all attempts fail

        for file in os.listdir(root):
            src_file = os.path.join(root, file)

            if src_file in processed_files:
                continue

            processed_files.add(src_file)

            episode_match = re.search(r'(.*?)(S\d{2} ?E\d{2})', file, re.IGNORECASE)

            if episode_match:
                episode_identifier = episode_match.group(2)
            else:
                episode_identifier = "Unknown"

            if re.match(r'S\d{2} ?E\d{2}', file, re.IGNORECASE):
                show_name = re.sub(r'\s*(S\d{2}.*|Season \d+).*', '', folder_name).replace('-', ' ').replace('.', ' ').strip()
            else:
                show_name = episode_match.group(1).replace('.', ' ').strip() if episode_match else "Unknown"

            show_name = sanitize_title(show_name)

            if not episode_match:
                if show_folder is None:
                    show_folder = extract_show_name_from_path(root)
                    year = extract_folder_year(folder_name) or extract_year(show_folder)
                    if year:
                        show_folder = re.sub(r'\(\d{4}\)$', '', show_folder).strip()
                        show_folder = re.sub(r'\d{4}$', '', show_folder).strip()

                    if not show_folder and year:
                        # Use the year as the search term if the show name is empty
                        show_folder = str(year)
                        year = None

                    # Normalize show_folder for inverted index search
                    normalized_show_folder = re.sub(r'[^a-z0-9\s.]', '', show_folder.lower())

                    # Log the search criteria
                    print(f"Searching inverted index for: {normalized_show_folder} with year: {year}")

                    # First attempt to find the show using the inverted index with the year
                    search_results = search_inverted_index(normalized_show_folder, inverted_index, year)
                    if not search_results:
                        # Fallback to TMDb search if the inverted index search fails
                        print(f"Searching TMDb for: {show_folder} with year: {year}")
                        show_folder = search_tv_show(show_folder, year, id=id, force=force, folder_path=root)

                        if not show_folder:
                            # Fallback to replacing spaces with periods and searching again
                            fallback_show_folder = normalized_show_folder.replace(' ', '.')
                            print(f"Fallback search inverted index for: {fallback_show_folder} with year: {year}")
                            search_results = search_inverted_index(fallback_show_folder, inverted_index, year)
                            if not search_results:
                                print(f"Fallback search TMDb for: {fallback_show_folder} with year: {year}")
                                show_folder = search_tv_show(fallback_show_folder, year, id=id, force=force, folder_path=root)

                                # If all year-based searches fail, search without the year
                                if not search_results and not show_folder and year:
                                    # Fallback search without year
                                    print(f"Fallback search inverted index for: {normalized_show_folder} without year")
                                    search_results = search_inverted_index(normalized_show_folder, inverted_index)
                                    if not search_results:
                                        print(f"Fallback search TMDb for: {show_folder} without year")
                                        show_folder = search_tv_show(show_folder, None, id=id, force=force, folder_path=root)

                    if search_results:
                        best_match = search_results[0][0]
                        show_folder = f"{best_match[0]} ({best_match[2]}) {{tmdb-{best_match[1]}}}"

                    if show_folder is None:
                        if show_name.lower() != "unknown":
                            log_failure = True  # Set the flag to log the failure later
                        print(f"Unprocessed item: {src_file}")
                        skip_folder = True
                        break
                    if show_folder in multiple_matches:
                        show_folder = multiple_matches[show_folder]
                    show_folder = show_folder.replace('/', '')
                    tmdb_id = extract_tmdb_id_from_show_folder(show_folder)

                extras_folder = os.path.join(cleaned_dir, show_folder, "Extras")
                os.makedirs(extras_folder, exist_ok=True)
                extras_dest_file = os.path.join(extras_folder, file)
                if not os.path.exists(extras_dest_file):
                    os.symlink(src_file, extras_dest_file)
                    print(f"Created symlink for extra: {extras_dest_file} -> {src_file}")
                log_media_item(src_file, extras_dest_file, tmdb_id)  # Include tmdb_id for extras
                continue

            name, ext = os.path.splitext(file)
            
            if '.' in name:
                new_name = re.sub(r'\.', ' ', name)
            else:
                new_name = name

            resolution = extract_resolution(new_name, folder_name, src_file)

            if resolution:
                split_name = new_name.split(resolution)[0]
                new_name = split_name.strip() + ' ' + resolution + ext
            else:
                new_name += ext

            season_number_match = re.search(r'S(\d{2}) ?E\d{2}', episode_identifier, re.IGNORECASE)
            if season_number_match:
                season_number = season_number_match.group(1)
                season_folder = f"Season {int(season_number)}"
            else:
                season_folder = "Unknown Season"

            if show_folder is None:
                show_folder = re.sub(r'\s+$|_+$|-+$|(\()$', '', show_name)
                show_folder = show_folder.rstrip()
                year = extract_folder_year(folder_name) or extract_year(show_folder)
                if year:
                    show_folder = re.sub(r'\(\d{4}\)$', '', show_folder).strip()
                    show_folder = re.sub(r'\d{4}$', '', show_folder).strip()

                if not show_folder and year:
                    # Use the year as the search term if the show name is empty
                    show_folder = str(year)
                    year = None

                # Normalize show_folder for inverted index search
                normalized_show_folder = re.sub(r'[^a-z0-9\s.]', '', show_folder.lower())

                # Log the search criteria
                print(f"Searching inverted index for: {normalized_show_folder} with year: {year}")

                # First attempt to find the show using the inverted index with the year
                search_results = search_inverted_index(normalized_show_folder, inverted_index, year)
                if not search_results:
                    # Fallback to TMDb search if the inverted index search fails
                    print(f"Searching TMDb for: {show_folder} with year: {year}")
                    show_folder = search_tv_show(show_folder, year, id=id, force=force, folder_path=root)

                    if not show_folder:
                        # Fallback to replacing spaces with periods and searching again
                        fallback_show_folder = normalized_show_folder.replace(' ', '.')
                        print(f"Fallback search inverted index for: {fallback_show_folder} with year: {year}")
                        search_results = search_inverted_index(fallback_show_folder, inverted_index, year)
                        if not search_results:
                            print(f"Fallback search TMDb for: {fallback_show_folder} with year: {year}")
                            show_folder = search_tv_show(fallback_show_folder, year, id=id, force=force, folder_path=root)

                            # If all year-based searches fail, search without the year
                            if not search_results and not show_folder and year:
                                # Fallback search without year
                                print(f"Fallback search inverted index for: {normalized_show_folder} without year")
                                search_results = search_inverted_index(normalized_show_folder, inverted_index)
                                if not search_results:
                                    print(f"Fallback search TMDb for: {show_folder} without year")
                                    show_folder = search_tv_show(show_folder, None, id=id, force=force, folder_path=root)

                if search_results:
                    best_match = search_results[0][0]
                    show_folder = f"{best_match[0]} ({best_match[2]}) {{tmdb-{best_match[1]}}}"

                if show_folder is None:
                    if show_name.lower() != "unknown":
                        log_failure = True  # Set the flag to log the failure later
                    print(f"Unprocessed item: {src_file}")
                    skip_folder = True
                    break
                if show_folder in multiple_matches:
                    show_folder = multiple_matches[show_folder]
                show_folder = show_folder.replace('/', '')
                tmdb_id = extract_tmdb_id_from_show_folder(show_folder)

            cleaned_dest_path = os.path.join(cleaned_dir, show_folder, season_folder)
            os.makedirs(cleaned_dest_path, exist_ok=True)

            dest_file_name = f"{show_folder} - {episode_identifier.strip()}"
            if resolution:
                dest_file_name += f" [{resolution}]"
            dest_file_name += ext

            dest_file_name = clean_filename(dest_file_name)
            cleaned_dest_file = os.path.join(cleaned_dest_path, dest_file_name)
            
            if os.path.islink(cleaned_dest_file):
                if os.readlink(cleaned_dest_file) == src_file:
                    continue
                else:
                    os.remove(cleaned_dest_file)
            
            if os.path.exists(cleaned_dest_file) and not os.path.islink(cleaned_dest_file):
                continue

            if os.path.isdir(src_file):
                shutil.copytree(src_file, cleaned_dest_file, symlinks=True)
            else:
                os.symlink(src_file, cleaned_dest_file)
            print(f"Created symlink: {cleaned_dest_file} -> {src_file}")

            relative_path = os.path.relpath(src_file, src_dir)
            uncleaned_dest_file = os.path.join(uncleaned_dir, relative_path)
            os.makedirs(os.path.dirname(uncleaned_dest_file), exist_ok=True)
            if not os.path.exists(uncleaned_dest_file):
                os.symlink(src_file, uncleaned_dest_file)
                print(f"Created symlink: {uncleaned_dest_file} -> {src_file}")

            log_media_item(src_file, cleaned_dest_file, tmdb_id)  # Include tmdb_id for series episodes

        if not skip_folder:
            log_processed_folder(combined_folder_name, 'processed')
        else:
            if log_failure:
                log_multiple_match(folder_name, ["No results found"], root)
            print(f"Skipping folder: {combined_folder_name}")

    # ... other code ...

def search_inverted_index_with_year_range(query, inverted_index, year, range_delta):
    results = []
    if year:
        for delta in range(-range_delta, range_delta + 1):
            search_results = search_inverted_index(query, inverted_index, year + delta)
            if search_results:
                results.extend(search_results)
    else:
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


def extract_show_name_from_path(path):
    folder_name = os.path.basename(path)
    parent_folder = os.path.basename(os.path.dirname(path))

    if parent_folder.lower() == "torrents":
        folder_name = folder_name if folder_name.lower() != "unknown" else None
    else:
        folder_name = parent_folder if parent_folder.lower() != "unknown" else folder_name

    folder_name = re.sub(r'\(.*?\)', '', folder_name)
    folder_name = re.sub(r'Season \d+-\d+', '', folder_name)
    folder_name = re.sub(r'S\d+', '', folder_name)
    folder_name = re.sub(r'E\d+', '', folder_name)
    folder_name = re.sub(r'(\d{3,4}p|x\d{3,4}|HEVC|\d+bit|5\.1)', '', folder_name)
    folder_name = re.sub(r'[._-]', ' ', folder_name).strip()
    folder_name = folder_name.strip()
    return folder_name

def extract_tmdb_id_from_show_folder(show_folder):
    match = re.search(r'\{tmdb-(\d+)\}', show_folder)
    return match.group(1) if match else None

def process_symlink(folder_path, solution):
    settings = get_settings()
    dest_dir = settings.get('dest_dir')
    dest_dir_movies = settings.get('dest_dir_movies')
    cleaned_dir = os.path.join(dest_dir, "Cleaned")
    uncleaned_dir = os.path.join(dest_dir, "Uncleaned")

    parent_folder_name = os.path.basename(folder_path)

    for root, dirs, files in os.walk(folder_path):
        for file in files:
            src_file = os.path.join(root, file)

            episode_match = re.search(r'(.*?)(S\d{2} ?E\d{2})', file, re.IGNORECASE)
            if not episode_match:
                relative_path = os.path.relpath(os.path.join(root, file), folder_path)
                uncleaned_dest_file = os.path.join(uncleaned_dir, relative_path)
                os.makedirs(os.path.dirname(uncleaned_dest_file), exist_ok=True)
                if not os.path.exists(uncleaned_dest_file):
                    os.symlink(src_file, uncleaned_dest_file)
                log_media_item(src_file, uncleaned_dest_file, tmdb_id=None)
                continue

            episode_identifier = episode_match.group(2)
            
            if re.match(r'S\d{2} ?E\d{2}', file, re.IGNORECASE):
                show_name = re.sub(r'\s*(S\d{2}.*|Season \d+).*', '', solution).replace('-', ' ').replace('.', ' ').strip()
            else:
                show_name = episode_match.group(1).replace('.', ' ').strip()

            show_name = sanitize_title(show_name)

            name, ext = os.path.splitext(file)
            
            if '.' in name:
                new_name = re.sub(r'\.', ' ', name)
            else:
                new_name = name

            resolution = extract_resolution(new_name, parent_folder_name, src_file)

            if resolution:
                split_name = new_name.split(resolution)[0]
                new_name = split_name.strip() + ' ' + resolution + ext
            else:
                new_name += ext

            season_number_match = re.search(r'S(\d{2}) ?E\d{2}', episode_identifier, re.IGNORECASE)
            if season_number_match:
                season_number = season_number_match.group(1)
                season_folder = f"Season {int(season_number)}"
            else:
                season_folder = "Unknown Season"

            show_folder = re.sub(r'\s+$|_+$|-+$|(\()$', '', show_name)
            show_folder = show_folder.rstrip()
            
            show_folder = solution.replace('[', '{').replace(']', '}')
            show_folder = show_folder.replace('/', '')
            cleaned_dest_path = os.path.join(cleaned_dir, show_folder, season_folder)
            os.makedirs(cleaned_dest_path, exist_ok=True)

            dest_file_name = f"{show_name.strip()} - {episode_identifier.strip()}"
            if resolution:
                dest_file_name += f" [{resolution}]"
            dest_file_name += ext

            dest_file_name = clean_filename(dest_file_name)
            cleaned_dest_file = os.path.join(cleaned_dest_path, dest_file_name)
            
            if os.path.islink(cleaned_dest_file):
                if os.readlink(cleaned_dest_file) == src_file:
                    continue
                else:
                    os.remove(cleaned_dest_file)
            
            if os.path.exists(cleaned_dest_file) and not os.path.islink(cleaned_dest_file):
                continue

            if os.path.isdir(src_file):
                shutil.copytree(src_file, cleaned_dest_file, symlinks=True)
            else:
                os.symlink(src_file, cleaned_dest_file)

            relative_path = os.path.relpath(os.path.join(root, file), folder_path)
            uncleaned_dest_file = os.path.join(uncleaned_dir, relative_path)
            os.makedirs(os.path.dirname(uncleaned_dest_file), exist_ok=True)
            if not os.path.exists(uncleaned_dest_file):
                os.symlink(src_file, uncleaned_dest_file)

            tmdb_id = extract_tmdb_id_from_show_folder(show_folder)
            log_media_item(src_file, cleaned_dest_file, tmdb_id)

def process_resolved_matches():
    unresolved_matches = get_unresolved_multiple_matches()
    grouped_matches = group_matches_by_folder(unresolved_matches)

    for folder_path, matches in grouped_matches.items():
        ids = [match[0] for match in matches]
        original_names = [match[1] for match in matches]
        possible_matches = matches[0][2]

        while True:
            correct_name = extract_show_name_from_path(folder_path)
            print(f"\nFolder path: {folder_path}")
            print(f"Original file/show names: {', '.join(original_names)}")
            for idx, match in enumerate(possible_matches):
                print(f"{idx + 1}: {match}")
            print(f"{len(possible_matches) + 1}: No matches, input TMDb manually")
            print(f"{len(possible_matches) + 2}: Search TMDb")

            choice = input(Fore.GREEN + "Choose a match (1-3 or input TMDb manually) or press Enter to skip: " + Style.RESET_ALL).strip()
            if choice.isdigit():
                choice = int(choice)
                if 1 <= choice <= len(possible_matches):
                    solution = possible_matches[choice - 1]
                    for id in ids:
                        update_multiple_match_solution(id, solution)
                        print(f"Processing symlink for resolved match: {solution}")
                        process_symlink(folder_path, solution)
                        delete_multiple_match(id)
                    break
                elif choice == len(possible_matches) + 1:
                    manual_tmdb_id = input(Fore.YELLOW + "Enter TMDb ID manually: " + Style.RESET_ALL).strip()
                    if manual_tmdb_id.isdigit():
                        show_folder = search_tv_show_by_id(manual_tmdb_id)
                        if show_folder:
                            show_folder = show_folder.replace('[', '{').replace(']', '}')
                            for id in ids:
                                update_multiple_match_solution(id, show_folder)
                                print(f"Processing symlink for manually entered TMDb ID: {show_folder}")
                                process_symlink(folder_path, show_folder)
                                delete_multiple_match(id)
                            break
                elif choice == len(possible_matches) + 2:
                    search_query = input(Fore.YELLOW + f"Enter search term for TMDb (default: {correct_name}): " + Style.RESET_ALL).strip()
                    if not search_query:
                        search_query = correct_name
                    search_results = tmdb_search(search_query)
                    possible_matches = [
                        f"{result['name']} ({result['first_air_date'][:4]}) [tmdb-{result['id']}]"
                        for result in search_results
                    ]
                    if not possible_matches:
                        possible_matches.append("No results found")
            else:
                print("Skipping this match")
                break


if __name__ == "__main__":
    settings = get_settings()
    initialize_db()

    parser = argparse.ArgumentParser(description="Create symlinks for files from src_dir in dest_dir.")
    parser.add_argument("--force", action="store_true", help="Disregards user input and automatically chooses the first option")
    args = parser.parse_args()

    if 'src_dir' not in settings or 'dest_dir' not in settings or 'dest_dir_movies' not in settings or 'id' not in settings or 'tmdb_api_key' not in settings:
        print("Missing configuration in settings.json. Please provide necessary inputs.")
        settings = prompt_for_settings()
        src_dir = settings['src_dir']
        dest_dir = settings['dest_dir']
        dest_dir_movies = settings['dest_dir_movies']
        id_choice = settings['id']
    else:
        src_dir = settings['src_dir']
        dest_dir = settings['dest_dir']
        dest_dir_movies = settings['dest_dir_movies']
        id_choice = settings['id']

    last_report_time = datetime.now()

    while True:
        current_time = datetime.now()
        if (current_time - last_report_time) > timedelta(minutes=2):
            print("Still checking for new files...")
            last_report_time = current_time
        
        update_series_names_from_overseer()
        create_symlinks(src_dir, dest_dir, dest_dir_movies, force=args.force, id=id_choice, quick_scan=True)
        process_resolved_matches()
        time.sleep(10)  # Poll every 10 seconds
