import setuptools

setuptools.setup(
    name="streamer",
    version="0.0.1",
    author="Crowdbreaks",
    author_email="info@crowdbreaks.org",
    description="Twitter API v1.1 streamer",
    url="https://github.com/crowdbreaks/streamer",
    packages=setuptools.find_packages(),
    install_requires=[
        'python-dotenv', 'aenum', 'dacite', 'tweepy',
        'boto3', 'elasticsearch', 'requests_aws4auth',
        'twiprocess @ git+https://github.com/crowdbreaks/twiprocess.git',
        'awstools @ git+https://github.com/crowdbreaks/streamer.git#egg=awstools&subdirectory=awstools'],
    entry_points={'console_scripts': [
        'run-stream=streamer.run:main']},
    package_data={'streamer': ['streamer.env']},
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent"],
    python_requires='>=3.8')
