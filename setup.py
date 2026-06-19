from setuptools import setup, find_packages

setup(
    name="rekord2spotify",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "click>=8.0",
        "spotipy>=2.23",
        "python-dotenv>=1.0",
    ],
    entry_points={
        "console_scripts": [
            "rekord2spotify = rekord2spotify.cli:main",
        ],
    },
)