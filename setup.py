from setuptools import setup, find_packages

setup(
    name="spotidal",
    version="2.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    include_package_data=True,
    install_requires=[
        "spotipy>=2.21.0",
        "tidalapi>=0.7.6",
        "sqlalchemy>=2.0.31",
        "tqdm>=4.66.2",
        "requests>=2.32.3",
        "pyyaml>=6.0.1",
        "InquirerPy>=0.3.4",
    ],
    entry_points={
        "console_scripts": [
            "spotidal = spotidal.view.view:main",
        ],
    },
    description="Spotify playlists to tidal: sync and download masters.",
    url="https://github.com/ritapatacas/spotidal",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
)
