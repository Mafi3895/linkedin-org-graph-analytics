import os
import json
import logging
import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import requests

from src.validators.schemas import LinkedInProfileRecord
from src.processors.linkedin_parser import LinkedInParser

logger = logging.getLogger(__name__)


class LinkedInCollector:
    """
    Programmatic data collector for LinkedIn public profiles.
    Strictly uses LinkedIn public endpoints with full audit trail.
    No LLM hallucination, no mock data, no unauthorized credential bypasses.
    """

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    }

    def __init__(
        self,
        raw_data_dir: str = "data/raw/profiles",
        processed_data_dir: str = "data/processed",
        timeout: int = 15,
    ):
        self.raw_data_dir = Path(raw_data_dir)
        self.processed_data_dir = Path(processed_data_dir)
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)
        self.processed_data_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.parser = LinkedInParser()
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)

    def fetch_profile_html(self, profile_url: str) -> str:
        """
        Executes HTTP GET request to public LinkedIn profile endpoint.
        Handles status codes and raises informative exceptions on rate limits or blocks.
        """
        try:
            response = self.session.get(profile_url, timeout=self.timeout)
        except requests.RequestException as e:
            raise ConnectionError(f"Network error while connecting to LinkedIn: {e}")

        if response.status_code == 200:
            return response.text
        elif response.status_code == 429:
            raise PermissionError("LinkedIn returned HTTP 429 (Rate Limit Exceeded).")
        elif response.status_code in (403, 999):
            raise PermissionError(
                f"LinkedIn returned HTTP {response.status_code} (Access blocked / Anti-scraping gate)."
            )
        elif response.status_code == 404:
            raise FileNotFoundError(f"LinkedIn profile not found: {profile_url}")
        else:
            raise RuntimeError(
                f"LinkedIn returned unexpected HTTP status: {response.status_code}"
            )

    def collect_and_save(
        self,
        person_id: str,
        profile_url: str,
        use_cached_raw: bool = False,
    ) -> LinkedInProfileRecord:
        """
        Fetches public profile HTML, stores raw audit copy in data/raw/profiles/,
        parses the LinkedIn evidence strictly, and saves structured JSON into data/processed/.
        """
        raw_file_path = self.raw_data_dir / f"{person_id}.html"
        fetched_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if use_cached_raw and raw_file_path.exists():
            logger.info("Using cached raw HTML from %s", raw_file_path)
            html_content = raw_file_path.read_text(encoding="utf-8")
            collection_method = "linkedin_authenticated_snapshot"
        else:
            logger.info("Fetching live public LinkedIn profile for %s (%s)", person_id, profile_url)
            html_content = self.fetch_profile_html(profile_url)
            raw_file_path.write_text(html_content, encoding="utf-8")
            logger.info("Raw LinkedIn HTML saved to %s", raw_file_path)
            collection_method = "linkedin_public_guest_view_http"

        # Parse into strictly validated Pydantic model
        record = self.parser.parse(
            html_content=html_content,
            profile_url=profile_url,
            person_id=person_id,
            fetched_at=fetched_at,
            collection_method=collection_method,
        )

        # Save single record to processed dir
        record_json_path = self.processed_data_dir / f"{person_id}.json"
        with open(record_json_path, "w", encoding="utf-8") as f:
            f.write(record.model_dump_json(indent=2))
        logger.info("Processed profile JSON saved to %s", record_json_path)

        # Update collective profiles.json
        self._update_collective_profiles(record)

        return record

    def _update_collective_profiles(self, record: LinkedInProfileRecord):
        collective_file = self.processed_data_dir / "profiles.json"
        data: Dict[str, Any] = {}
        if collective_file.exists():
            try:
                with open(collective_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        data[record.person_id] = json.loads(record.model_dump_json())

        with open(collective_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
