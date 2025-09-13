# ShortMax Scraper

A comprehensive web scraper for extracting all available work data from ShortMax (https://shortmax.app/tabbar/home).

## Features

- Extracts all work titles, synopses, tags, view counts, and other metrics
- Covers all sections: Premium Drama, Most Popular, Most Trending, etc.
- Handles all categories: Historical, Urban, High Fantasy, Elite Families, Werewolf, Modern Love
- Exports comprehensive data to CSV format
- Robust error handling and retry mechanisms
- Headless browser operation

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

The scraper will create a CSV file with all extracted data including:
- Title
- View count
- Synopsis/Description
- Section (Premium Drama, Most Popular, etc.)
- Category (Historical, Urban, etc.)
- Tags ([Dubbed], flash married, etc.)
- Episode count (when available)
- URL
- Scrape timestamp

## Data Fields Extracted

- **title**: Work title
- **view_count**: View count in K format (e.g., "44.89K")
- **synopsis**: Short description or synopsis
- **section**: Section classification (Premium Drama, Most Popular, etc.)
- **category**: Genre category (Historical, Urban, High Fantasy, etc.)
- **tags**: Special tags like [Dubbed], flash married, etc.
- **episode_count**: Number of episodes (when available)
- **detailed_description**: Full description from individual work pages
- **url**: Direct URL to the work
- **scrape_timestamp**: When the data was scraped
