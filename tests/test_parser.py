import pytest
from pathlib import Path
from src.processors.linkedin_parser import LinkedInParser
from src.validators.schemas import FieldStatus


@pytest.fixture
def parser():
    return LinkedInParser()


@pytest.fixture
def raw_html():
    path = Path("data/raw/profiles/hf_001.html")
    assert path.exists(), "Raw test HTML file must exist"
    return path.read_text(encoding="utf-8")


def test_parser_basic_info(parser, raw_html):
    record = parser.parse(
        html_content=raw_html,
        profile_url="https://fr.linkedin.com/in/anton-lozhkov",
        person_id="hf_001",
        fetched_at="2026-11-11T12:00:00Z",
    )

    assert record.person_id == "hf_001"
    assert record.basic_info.full_name == "Anton Lozhkov"
    assert record.basic_info.current_company == "Hugging Face"
    assert "Paris" in record.basic_info.location

    # Authenticated snapshot has real headline
    assert record.basic_info.headline == "Machine Learning Engineer – Hugging Face"
    assert record.field_level_availability["basic_info.headline"].status == FieldStatus.FETCHED

    # About is genuinely present
    assert record.basic_info.about is not None
    assert "ML Engineer" in record.basic_info.about
    assert record.field_level_availability["basic_info.about"].status == FieldStatus.FETCHED


def test_parser_work_experience(parser, raw_html):
    record = parser.parse(
        html_content=raw_html,
        profile_url="https://fr.linkedin.com/in/anton-lozhkov",
        person_id="hf_001",
        fetched_at="2026-11-11T12:00:00Z",
    )

    # 4 distinct companies extracted
    assert len(record.work_experience) == 4

    current = record.work_experience[0]
    assert current.company == "Hugging Face"
    assert current.job_title == "Machine Learning Engineer"
    assert current.is_current is True
    assert current.start_date == "Aug 2021"
    assert current.end_date == "Present"

    past_embedika = record.work_experience[1]
    assert past_embedika.company == "Embedika"
    assert past_embedika.is_current is False

    past_naumen = record.work_experience[2]
    assert past_naumen.company == "NAUMEN"

    past_kaspersky = record.work_experience[3]
    assert past_kaspersky.company == "Kaspersky Lab"


def test_parser_education(parser, raw_html):
    record = parser.parse(
        html_content=raw_html,
        profile_url="https://fr.linkedin.com/in/anton-lozhkov",
        person_id="hf_001",
        fetched_at="2026-11-11T12:00:00Z",
    )

    assert len(record.education) == 2
    bachelor = record.education[0]
    assert bachelor.institution == "Higher School of Economics"
    assert bachelor.degree == "Bachelor's degree"
    assert bachelor.start_date == "2013"
    assert bachelor.end_date == "2017"

    master = record.education[1]
    assert master.institution == "Higher School of Economics"
    assert "Master" in master.degree
    assert master.start_date == "2017"
    assert master.end_date == "2018"


def test_parser_skills_and_interests(parser, raw_html):
    record = parser.parse(
        html_content=raw_html,
        profile_url="https://fr.linkedin.com/in/anton-lozhkov",
        person_id="hf_001",
        fetched_at="2026-11-11T12:00:00Z",
    )

    assert len(record.skills) >= 2
    skill_names = [s.skill_name for s in record.skills]
    assert "Python" in skill_names
    assert "Data Science" in skill_names

    assert len(record.interests) >= 1
    assert record.interests[0].name == "Hugging Face"


def test_parser_activity(parser, raw_html):
    record = parser.parse(
        html_content=raw_html,
        profile_url="https://fr.linkedin.com/in/anton-lozhkov",
        person_id="hf_001",
        fetched_at="2026-11-11T12:00:00Z",
    )

    assert len(record.activity) >= 1
    for act in record.activity:
        assert act.content is not None
