import sqlite3
from collections import defaultdict
import re
import json

DB_FILE = 'symlinks.db'

def initialize_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS MediaItems (
            id INTEGER PRIMARY KEY,
            src_dir TEXT UNIQUE,
            symlink TEXT,
            tmdb_id TEXT,
            deprecated INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS ProcessedFolders (
                        id INTEGER PRIMARY KEY,
                        folder_name TEXT UNIQUE,
                        status TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS MultipleMatches (
                        id INTEGER PRIMARY KEY,
                        original_name TEXT,
                        possible_matches TEXT,
                        solution TEXT,
                        folder_paths TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS WrongPattern (
                        id INTEGER PRIMARY KEY,
                        filename TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS TmdbSeriesNames (
                        tmdb_id INTEGER PRIMARY KEY,
                        series_name TEXT,
                        year INTEGER)''')
    conn.commit()
    conn.close()

def log_media_item(src_dir, symlink, tmdb_id=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO MediaItems (src_dir, symlink, tmdb_id)
        VALUES (?, ?, ?)
        ON CONFLICT(src_dir) DO UPDATE SET
        symlink=excluded.symlink,
        tmdb_id=excluded.tmdb_id
    ''', (src_dir, symlink, tmdb_id))
    conn.commit()
    conn.close()

def mark_folder_deprecated(folder_path):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE MediaItems
        SET deprecated = 1
        WHERE src_dir LIKE ?
    ''', (f"{folder_path}%",))
    conn.commit()
    conn.close()

def mark_folder_active(folder_path):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE MediaItems
        SET deprecated = 0
        WHERE src_dir LIKE ?
    ''', (f"{folder_path}%",))
    conn.commit()
    conn.close()

def get_all_source_folders():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT src_dir
        FROM MediaItems
        WHERE deprecated = 0
    ''')
    folders = [os.path.abspath(row[0]) for row in cursor.fetchall()]
    conn.close()
    return folders

def remove_symlink_entry(symlink_path):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        DELETE FROM MediaItems
        WHERE symlink = ?
    ''', (symlink_path,))
    conn.commit()
    conn.close()

def log_multiple_match(original_name, possible_matches, folder_path):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    possible_matches_json = json.dumps(possible_matches)
    folder_paths_json = json.dumps([folder_path])
    cursor.execute('''INSERT INTO MultipleMatches (original_name, possible_matches, folder_paths)
                      VALUES (?, ?, ?)''', (original_name, possible_matches_json, folder_paths_json))
    conn.commit()
    conn.close()

def log_processed_folder(folder_name, status):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''INSERT OR IGNORE INTO ProcessedFolders (folder_name, status)
                      VALUES (?, ?)''', (folder_name, status))
    cursor.execute('''UPDATE ProcessedFolders SET status = ? WHERE folder_name = ?''', (status, folder_name))
    conn.commit()
    conn.close()

def get_processed_folders():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''SELECT folder_name FROM ProcessedFolders''')
    processed_folders = [row[0] for row in cursor.fetchall()]
    conn.close()
    return processed_folders

def get_multiple_matches():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''SELECT original_name, solution FROM MultipleMatches WHERE solution IS NOT NULL''')
    multiple_matches = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return multiple_matches

def get_unresolved_multiple_matches():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''SELECT id, original_name, possible_matches, folder_paths 
                      FROM MultipleMatches WHERE solution IS NULL''')
    unresolved_matches = cursor.fetchall()
    conn.close()
    matches = []
    for row in unresolved_matches:
        id, original_name, possible_matches, folder_paths = row
        try:
            possible_matches = json.loads(possible_matches)
        except json.JSONDecodeError:
            possible_matches = []
        try:
            folder_paths = json.loads(folder_paths) if folder_paths else []
        except json.JSONDecodeError:
            folder_paths = []
        matches.append((id, original_name, possible_matches, folder_paths))
    return matches

def update_multiple_match_solution(id, solution):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''UPDATE MultipleMatches SET solution = ? WHERE id = ?''', (solution, id))
    conn.commit()
    conn.close()

def delete_multiple_match(id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''DELETE FROM MultipleMatches WHERE id = ?''', (id,))
    conn.commit()
    conn.close()

def log_wrong_pattern(filename):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO WrongPattern (filename)
                      VALUES (?)''', (filename,))
    conn.commit()
    conn.close()

def store_tmdb_series_name(tmdb_id, series_name, year):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO TmdbSeriesNames (tmdb_id, series_name, year)
        VALUES (?, ?, ?)
        ON CONFLICT(tmdb_id) DO UPDATE SET
        series_name=excluded.series_name,
        year=excluded.year
    ''', (tmdb_id, series_name, year))
    conn.commit()
    conn.close()

def get_tmdb_series_name(tmdb_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''SELECT series_name, year FROM TmdbSeriesNames WHERE tmdb_id = ?''', (tmdb_id,))
    result = cursor.fetchone()
    conn.close()
    return result if result else (None, None)

def build_inverted_index():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''SELECT tmdb_id, series_name, year FROM TmdbSeriesNames''')
    series = cursor.fetchall()
    conn.close()
    
    inverted_index = defaultdict(list)
    
    for tmdb_id, series_name, year in series:
        ngrams = generate_ngrams(series_name)
        for ngram in ngrams:
            inverted_index[ngram].append((series_name, tmdb_id, year))
    
    return inverted_index

def generate_ngrams(text, n=3):
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s.]', '', text)  # Keep periods
    words = text.split()
    ngrams = set()
    for word in words:
        for i in range(len(word) - n + 1):
            ngrams.add(word[i:i+n])
    return ngrams


def search_inverted_index(query, inverted_index, year=None):
    query = re.sub(r'[^a-z0-9\s.]', '', query.lower())  # Normalize query with periods
    query_ngrams = generate_ngrams(query)
    results = defaultdict(int)

    for ngram in query_ngrams:
        if ngram in inverted_index:
            for series_name, tmdb_id, series_year in inverted_index[ngram]:
                if year is None or series_year == year:
                    results[(series_name, tmdb_id, series_year)] += 1

    sorted_results = sorted(results.items(), key=lambda item: item[1], reverse=True)
    return sorted_results


# Example usage
def search_series(query):
    inverted_index = build_inverted_index()
    results = search_inverted_index(query, inverted_index)
    for (series_name, tmdb_id, year), score in results:
        print(f"Series: {series_name}, TMDb ID: {tmdb_id}, Year: {year}, Score: {score}")
