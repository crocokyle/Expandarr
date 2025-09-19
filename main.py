import requests
import openai
import re
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
LIDARR_API_KEY = os.environ.get('LIDARR_API_KEY')
LIDARR_HOST = os.environ.get('LIDARR_HOST')
ROOT_FOLDER_PATH = os.environ.get('ROOT_FOLDER_PATH')
PROMPT = os.environ.get('PROMPT')

RED = '\033[31m'
GREEN = '\033[32m'
YELLOW = '\033[33m'
RESET = '\033[0m'


def get_artist_guid(artist: str) -> str:
    musicbrainz_uri = f"https://musicbrainz.org/search?query={artist}&type=artist&method=indexed"
    response = requests.get(musicbrainz_uri)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, 'html.parser')

    # Find the table containing the search results
    table = soup.find('table', class_='tbl')
    if not table:
        return None

    # Find the first row in the table body, which corresponds to the top result
    top_row = table.find('tbody').find('tr')
    if not top_row:
        return None

    # Find the <a> tag within the first cell of the top row
    link_tag = top_row.find('td').find('a')
    if not link_tag:
        return None

    # Extract the href attribute
    href = link_tag.get('href')
    if not href:
        return None

    # Use a regular expression to find the GUID after "/artist/"
    match = re.search(r'/artist/([a-f0-9-]+)', href)

    return match.group(1) if match else None

def get_artists_list():
    url = f"https://{LIDARR_HOST}/api/v1/artist"

    # Define the custom headers and cookies
    headers = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "X-Api-Key": LIDARR_API_KEY,
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://{LIDARR_HOST}/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "TE": "trailers"
    }

    try:
        # Make the GET request
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        # Extract the 'artistName' from each dictionary in the list
        artist_names = [artist.get('artistName') for artist in data if artist.get('artistName')]

        # Remove duplicates and sort the list
        unique_sorted_names = sorted(list(set(artist_names)))

        return artist_names

    except requests.exceptions.RequestException as e:
        # Handle exceptions related to the request (e.g., network errors, bad status codes)
        print(f"Error: A request exception occurred. {e}")
        if 'response' in locals():
            print(f"Status Code: {response.status_code}")
            print(f"Response Content: {response.text[:200]}...")

    except Exception as e:
        # Handle any other exceptions
        print(f"Error: An unexpected error occurred. {e}")


def get_recommended_artists(artists: list[str]) -> list[str]:
    """
    Requests a list of recommended artists from the OpenAI API.

    Args:
    artists: A list of artist names to base recommendations on.

    Returns:
    A set of recommended artist names.
    """
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    existing_artists = '\n'.join(artists)
    full_prompt = f"{PROMPT}\n{existing_artists}"

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.5,
            max_tokens=150,
        )
        recommended_artists_text = response.choices[0].message.content
        recommended_artists = list(set(recommended_artists_text.strip().split('\n')))

        return recommended_artists
    except Exception as e:
        print(f"Error: An error occurred during the OpenAI API request. {e}\n{recommended_artists_text}")
        return list()

def add_artist_to_lidarr(guid: str, artist: str):
    search_str = f"lidarr:{guid}"
    payload = {
        "artistName": artist,
        "foreignArtistId": guid,
        "qualityProfileId": 1,
        "metadataProfileId": 1,
        "addOptions": {
            "monitor": "all",
            "searchForMissingAlbums": True
        },
        "rootFolderPath": ROOT_FOLDER_PATH,
    }
    url = f"https://{LIDARR_HOST}/api/v1/artist?apikey={LIDARR_API_KEY}"

    # Define the custom headers and cookies
    headers = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://{LIDARR_HOST}/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "TE": "trailers"
    }

    # Make the GET request
    response = requests.post(url, headers=headers, json=payload)

    if response.status_code == 201:
        print(f"{GREEN}Added! ✅{RESET}")
    else:
        if (js := response.json()) and isinstance(js, list) and (error := js[0].get('errorMessage')):
            print(f"{RED}{error}{RESET}")
        else:
            print(f"\n{RED}Error adding artist to Lidarr:\n{response.content}{RESET}")



if __name__ == "__main__":
    existing_artists = get_artists_list()
    print(f"Found {len(existing_artists)} existing artists in Lidarr")
    if existing_artists:
        recommended_artists = get_recommended_artists(existing_artists)
        # recommended_artists = ['Alt-J', 'Arctic Monkeys', 'Iron & Wine', 'Sufjan Stevens', 'Milky Chance', 'First Aid Kit', 'Hozier', 'Angus & Julia Stone', 'The War on Drugs', 'Cage the Elephant', 'Jose Gonzalez', 'The Paper Kites', 'The Neighbourhood', 'The Head and the Heart', 'Bon Iver', 'The Lumineers', 'The Tallest Man on Earth', 'Two Door Cinema Club', 'Billie Eilish', 'Ben Howard', 'Vampire Weekend', 'Of Monsters and Men', 'Lord Huron', 'The National', 'Fleet Foxes', 'James Bay', 'Foster the People', 'City and Colour', 'Nick Mul', 'The xx', 'Mumford & Sons', 'The 1975', 'Glass Animals', 'Young the Giant']
        if recommended_artists:
            print(f"{GREEN}Got {len(recommended_artists)} new recommended artists from OpenAI{RESET}")
            for artist in recommended_artists:
                if artist in existing_artists:
                    print(f"{YELLOW}Warning: {artist} is already in Lidarr...dumbass OpenAI 😑{RESET}")
                    continue
                if guid := get_artist_guid(artist):
                    print(f"Adding artist {artist} ({guid}) to Lidarr...", end='')
                    add_artist_to_lidarr(guid, artist)
                else:
                    print(f"{YELLOW}Warning: Could not find guid for artist {artist}{RESET}")
