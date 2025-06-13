import os.path

from setuptools import find_packages, setup

with open(os.path.join(os.path.dirname(__file__), 'README.md')) as f:
    LONG_DESCRIPTION = f.read()
    DESCRIPTION = LONG_DESCRIPTION.splitlines()[0].lstrip('#').strip()

PROJECT_URLS = {
    'Bug Tracker': 'https://github.com/nolar/looptime/issues',
    'Source Code': 'https://github.com/nolar/looptime',
}

setup(
    name='looptime',
    use_scm_version=True,

    url=PROJECT_URLS['Source Code'],
    project_urls=PROJECT_URLS,
    description=DESCRIPTION,
    long_description=LONG_DESCRIPTION,
    long_description_content_type='text/markdown',
    author='Sergey Vasilyev',
    author_email='nolar@nolar.info',
    maintainer='Sergey Vasilyev',
    maintainer_email='nolar@nolar.info',
    keywords=['asyncio', 'event loop', 'time', 'python', 'pytest'],
    license='MIT',

    zip_safe=True,
    packages=find_packages(),
    include_package_data=True,
    entry_points={
        'pytest11': [
            'looptime_plugin = looptime.plugin',
            'looptime_timeproxies = looptime.timeproxies',
            'looptime_chronometers = looptime.chronometers',
        ]
    },

    python_requires='>=3.9',
    setup_requires=[
        'setuptools_scm',
    ],
    install_requires=[
        # 'pytest',
    ],
    package_data={"looptime": ["py.typed"]},
)
