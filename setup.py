from setuptools import setup, find_packages

setup(
    name="visibilitycam",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "streamlit",
        "opencv-python",
        "numpy",
        "pandas",
        "plotly",
        "requests",
    ],
    python_requires=">=3.8",
    author="Your Name",
    author_email="your.email@example.com",
    description="A camera monitoring system for visibility analysis",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/VisibilityCam",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
) 