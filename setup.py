from setuptools import setup, find_packages

setup(
    name="spotidal",
    version="2.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        # dependencies
    ],
    entry_points={
        "console_scripts": [
            "spotidal2 = spotidal.src.view.view:main",
        ],
    },
)
