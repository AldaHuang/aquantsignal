from setuptools import setup, find_packages

setup(
    name="aquant",
    version="0.2.0",
    description="A-share quantitative trading system",
    packages=find_packages(exclude=["tests", "tests.*"]),
    python_requires=">=3.9",
    install_requires=[
        "akshare>=1.12.0",
        "pandas>=1.3.0",
        "numpy>=1.21.0",
        "matplotlib>=3.5.0",
        "pyyaml>=5.4",
        "certifi",
    ],
    entry_points={
        "console_scripts": ["aquant=aquant.cli:main"],
    },
)
