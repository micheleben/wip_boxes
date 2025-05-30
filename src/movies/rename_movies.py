import os
import re
import fnmatch
def remove_unwanted_files(directory, target_patterns=None):
    """
    Remove unwanted files in the given directory based on patterns
    
    Args:
        directory: Path to directory to clean
        target_patterns: List of filename patterns to remove (supports wildcards)
    """
    # Default patterns if none provided
    if target_patterns is None:
        target_patterns = [
            "www.YTS.MX.jpg",    # Specific YTS image file
            "www.YTS.RE.jpg",    # Specific YTS image file
            #"*.srt",             # Any subtitle files
            "YTSProxies.com.txt" # Specific YTS notepad
        ]
    
    files_removed = 0
    
    # Scan all files in directory
    for filename in os.listdir(directory):
        # Check if file matches any of our patterns
        for pattern in target_patterns:
            if fnmatch.fnmatch(filename, pattern):
                file_path = os.path.join(directory, filename)
                os.remove(file_path)
                print(f"  Removed: '{filename}' from {directory}")
                files_removed += 1
                break  # No need to check other patterns
    
    return files_removed

def clean_movie_filename(main_directory, target_patterns=None):
    # Regular expressions for different filename patterns
    original_pattern = r'(.*?)\.(\d{4})\..*\.(mp4|avi|mkv)'  # Original pattern with dots
    correct_pattern = r'^(.*?) \((\d{4})\)\.(mp4|avi|mkv)$'  # Already corrected pattern
    
    # Get all subdirectories in the main directory
    subdirs = [d for d in os.listdir(main_directory) if os.path.isdir(os.path.join(main_directory, d))]
    
    for subdir in subdirs:
        subdir_path = os.path.join(main_directory, subdir)
        print(f"Processing directory: {subdir_path}")
        
         # First, remove any YTS image files
        files_removed = remove_unwanted_files(subdir_path, target_patterns)

        for filename in os.listdir(subdir_path):
            if filename.endswith('.mp4') or filename.endswith('.avi') or filename.endswith('.mkv'):
                # Check if file already has the correct format
                correct_match = re.search(correct_pattern, filename)
                if correct_match:
                    print(f"  Already correct format: '{filename}'")
                    continue
                
                # Try to match the original pattern with dots
                original_match = re.search(original_pattern, filename)
                if original_match:
                    title = original_match.group(1).replace('.', ' ')
                    year = original_match.group(2)
                    new_filename = f"{title} ({year}).mp4"
                    
                    # Full paths for rename operation
                    old_path = os.path.join(subdir_path, filename)
                    new_path = os.path.join(subdir_path, new_filename)
                    
                    # Rename the file
                    os.rename(old_path, new_path)
                    print(f"  Renamed: '{filename}' → '{new_filename}'")
                else:
                    print(f"  ERROR: '{filename}' doesn't match any expected pattern")



# Example usage
if __name__ == "__main__":
    main_dir = r"E:/italiani/"  # Replace with your actual path
    #main_dir = r"E:/inglesi/"  # Replace with your actual path
    clean_movie_filename(main_dir)