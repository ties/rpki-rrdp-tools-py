""" Set up script """
import os

from setuptools import find_packages, setup

here = os.path.abspath(os.path.dirname(__file__))


with open(os.path.join(here, "README.md"), "rb") as f:
    long_descr = f.read().decode("utf-8")


setup(
    name="rrdp-tools",
    version="0.0.1",
    author="Ties de Kock",
    author_email="ties@tiesdekock.nl",
    description="A collection of RRDP tools",
    long_description_content_type="text/markdown",
    long_description=long_descr,
    url="https://github.com/ties/rrdp-tools",
    entry_points={"console_scripts": ["reconstruct_snapshot = rrrdp_tools.reconstruct.main"]},
    install_requires=[],
    include_package_data=True,
    python_requires=">=3.8",
    license="MIT",
    keywords="rpki rrdp",
    packages=find_packages(exclude=["tests", "tests.*"]),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Topic :: Software Development :: Libraries",
        "License :: OSI Approved :: MIT License",
    ],
)
