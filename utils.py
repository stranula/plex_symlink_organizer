import re
import subprocess
import json
import time

# Update this path to the actual location of ffprobe in your project
FFPROBE_PATH = './ffprobe'

def extract_year(query):
    match = re.search(r'\((\d{4})\)$', query.strip())
    if match:
        return int(match.group(1))
    match = re.search(r'(\d{4})$', query.strip())
    if match:
        return int(match.group(1))
    return None

import re

def extract_resolution(name, parent_folder_name=None, file_path=None):
    # First, check the parent folder name for resolution info
    if parent_folder_name:
        resolution_match = re.search(r'(\d{3,4}p)', parent_folder_name, re.IGNORECASE)
        if resolution_match:
            return resolution_match.group(1)

    # Then, check the file name for resolution info
    resolution_match = re.search(r'(\d{3,4}p)', name, re.IGNORECASE)
    if resolution_match:
        return resolution_match.group(1)

    # Finally, fallback to ffprobe if necessary
    if file_path:
        import subprocess
        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=height,width', '-of', 'csv=p=0', file_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if result.returncode == 0:
                width, height = result.stdout.strip().split(',')
                return f"{width}x{height}"
        except Exception as e:
            print(f"Error using ffprobe: {e}")

    return None


def get_resolution_with_ffprobe(file_path):
    """Get video resolution using ffprobe."""
    try:
        result = subprocess.run(
            [FFPROBE_PATH, "-v", "error", "-select_streams", "v:0", 
             "-show_entries", "stream=width,height", "-of", "json", file_path],
            capture_output=True,
            text=True
        )
        probe_data = json.loads(result.stdout)
        width = probe_data['streams'][0]['width']
        height = probe_data['streams'][0]['height']
        if width in [720, 1080, 2160]:
            return f"{width}p"
        else:
            return f"{width}x{height}"
    except Exception as e:
        print(f"Error getting resolution with ffprobe: {e}")
        return None

def extract_folder_year(folder_name):
    match = re.search(r'\((\d{4})\)', folder_name)
    if match:
        return int(match.group(1))
    match = re.search(r'\.(\d{4})\.', folder_name)
    if match:
        return int(match.group(1))
    return None

def sanitize_title(name):
    """Replace special characters in the title with spaces, keeping only letters and numbers."""
    return re.sub(r'[^a-zA-Z0-9\s]', ' ', name).strip()
