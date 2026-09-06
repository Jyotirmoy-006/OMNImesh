from setuptools import setup, find_packages

setup(
    name="omnimesh",
    version="0.1.0",
    description="A Decentralized, Two-Tiered Multi-Agent System for Traffic Optimization and Edge-Based Security",
    author="Jyotirmoy",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "numpy",
        "pyyaml",
        "msgpack",
        "paho-mqtt",
        "traci",
        "sumolib",
        "loguru",
    ],
)
