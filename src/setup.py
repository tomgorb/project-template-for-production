from setuptools import setup, find_packages

with open('requirements.txt') as f:
    REQUIREMENTS = f.read()

with open('version.txt') as version_file:
    version = version_file.read().strip()

setup(
    name='mymodel',
    version=version,
    install_requires=REQUIREMENTS,
    packages=find_packages(),
    package_data = {"mymodel": ["queries/*.yaml"]},
    include_package_data=True)
