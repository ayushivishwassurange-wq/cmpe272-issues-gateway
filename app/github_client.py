import os
import requests
from dotenv import load_dotenv

load_dotenv()

OWNER = os.getenv("GITHUB_OWNER")
REPO = os.getenv("GITHUB_REPO")
TOKEN = os.getenv("GITHUB_TOKEN")

BASE_URL = f"https://api.github.com/repos/{OWNER}/{REPO}"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json"
}