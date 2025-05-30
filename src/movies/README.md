## rename_movies.py
This Python script, `rename_movies.py`, is designed to clean up and standardize movie filenames within a nested directory structure.

**Core Functionality:**

The script has two primary functions:

1.  **`remove_unwanted_files(directory, target_patterns=None)`:**
    *   **Purpose:** To delete specific, unwanted files from a given directory.
    *   **How it works:**
        *   It takes a `directory` path and an optional list of `target_patterns` (filename patterns with wildcard support, e.g., `*.jpg`, `specific_file.txt`).
        *   If `target_patterns` is not provided, it uses a default list of patterns, primarily targeting common files bundled with YTS movie downloads (like `www.YTS.MX.jpg`, `YTSProxies.com.txt`).
        *   It iterates through all files in the specified `directory`.
        *   For each file, it checks if the filename matches any of the `target_patterns` using `fnmatch.fnmatch`.
        *   If a match is found, the file is deleted using `os.remove()`.
        *   It prints a message for each file removed and returns the total count of files removed.

2.  **`clean_movie_filename(main_directory, target_patterns=None)`:**
    *   **Purpose:** To iterate through subdirectories of a `main_directory`, clean unwanted files within them, and rename movie files to a standard format: `Movie Title (YYYY).ext`.
    *   **How it works:**
        *   It first identifies all immediate subdirectories within the `main_directory`.
        *   For each `subdir` found:
            *   It prints the path of the directory being processed.
            *   It calls `remove_unwanted_files()` to clean up that specific subdirectory using the provided or default `target_patterns`.
            *   It then lists all files within the `subdir_path`.
            *   For each `filename` that ends with `.mp4`, `.avi`, or `.mkv` (common video extensions):
                *   **Pattern Matching:** It uses regular expressions to check the filename against two patterns:
                    1.  `correct_pattern = r'^(.*?) \((\d{4})\)\.(mp4|avi|mkv)$'`: This checks if the filename is *already* in the desired format, e.g., "Movie Title (2023).mp4". If it matches, it prints a message and skips to the next file.
                    2.  `original_pattern = r'(.*?)\.(\d{4})\..*\.(mp4|avi|mkv)'`: This attempts to match filenames that often come from downloads, where parts of the name are separated by dots, and the year is present, e.g., "Movie.Title.With.Dots.2023.1080p.BluRay.x264.mp4".
                *   **Renaming Logic:**
                    *   If the `original_pattern` matches:
                        *   It extracts the movie title (replacing all dots `.` with spaces ` `).
                        *   It extracts the four-digit year.
                        *   It constructs a `new_filename` in the format: `"{title} ({year}).mp4"`. **Note:** The script currently hardcodes the new extension to `.mp4` regardless of the original file's extension if it matched the `original_pattern`.
                        *   It renames the file using `os.rename()`.
                        *   It prints a message indicating the old and new filenames.
                    *   If the filename is a video file but doesn't match either the `correct_pattern` or the `original_pattern`, it prints an error message indicating it couldn't process that file.

**Execution:**

*   The `if __name__ == "__main__":` block demonstrates how to use the script.
*   It sets a `main_dir` variable (e.g., `r"E:/italiani/"`) which should be the root directory containing subdirectories, where each subdirectory holds a movie and its associated files.
*   It then calls `clean_movie_filename(main_dir)` to start the cleaning and renaming process.

**In Summary:**

The script automates the process of tidying up movie collections by:
1.  Deleting common clutter files (like promotional images or text files from download sources).
2.  Renaming movie video files from a dot-separated format (e.g., `Some.Movie.Title.2023. calitate.stuff.mkv`) to a more readable and standardized format (e.g., `Some Movie Title (2023).mp4`).
