from setuptools import setup, find_packages

setup(
    name="openmontage",
    version="0.1.0",
    description="AI-Orchestrated Video Production Platform",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "pyyaml>=6.0",
        "pydantic>=2.0",
        "jsonschema>=4.20",
        "python-dotenv>=1.0",
        "Pillow>=10.0",
        "requests>=2.31",
        "certifi>=2026.10.19",
        "google-genai>=1.0.0",
        "openai>=2.44.0",
        "yt-dlp>=2025.1.15",
        "youtube-transcript-api>=1.0.0",
        "numpy>=1.24",
        "google-auth>=2.0",
        "fastapi>=0.110",
        "uvicorn>=0.29",
        "watchfiles>=0.21",
        "websockets>=14.0",
        "pythainlp>=5.0",
    ],
)
