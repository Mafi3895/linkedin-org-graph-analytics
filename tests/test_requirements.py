from pathlib import Path


def test_requirements_file_exists_and_contains_core_dependencies():
    req_path = Path("requirements.txt")
    assert req_path.exists(), "requirements.txt must exist in project root."

    content = req_path.read_text(encoding="utf-8").lower()

    # The prompt explicitly required these packages:
    # pydantic, beautifulsoup4, networkx, scikit-learn, matplotlib, and pytest
    expected_packages = [
        "pydantic",
        "beautifulsoup4",
        "networkx",
        "scikit-learn",
        "matplotlib",
        "pytest",
        "requests",
        "numpy",
        "pandas",
    ]

    for pkg in expected_packages:
        assert pkg in content, f"Package '{pkg}' must be listed in requirements.txt"
