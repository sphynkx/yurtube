import subprocess
import json
from typing import Any, Dict

def probe_ffprobe_json(file_path: str) -> Dict[str, Any]:
    """
    Run ffprobe on a file and return the data as a dictionary.
    
    :param file_path: Path to the file to probe
    :return: Parsed ffprobe output as Python dictionary
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        file_path,
    ]
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFprobe failed: {e.stderr}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse JSON from ffprobe: {str(e)}")